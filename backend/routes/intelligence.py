import asyncio
from datetime import datetime
from statistics import mean
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services.llm import acall_llm, acall_llm_json
from services.openweather import fetch_weather, fetch_forecast
from services.cache import get_cached_attribution, set_cached_attribution
from services.source_registry import (
    get_sources_for_city, has_registry, registry_meta, registry_stats,
)
from services.firms import fetch_fires_near, firms_enabled
from utils.aqi_calculator import aqi_category
from utils.attribution_confidence import score_attribution_confidence
from utils.dispersion import is_cloudy
from utils.enforcement_scoring import score_sources
from utils.impact_metrics import enforcement_impact
from utils.forecast_baseline import compute_baseline_forecast, backtest_baseline
from prompts import (
    ATTRIBUTION_SYSTEM, attribution_user, get_baseline_citation,
    ENFORCEMENT_SYSTEM, enforcement_user,
    FORECAST_SYSTEM, forecast_user,
    ADVISORY_SYSTEM, advisory_user,
)

router = APIRouter()


# ─── Request Models ───────────────────────────────────────────────────────────

class AttributionRequest(BaseModel):
    city: str
    state: str
    aqi: int
    pm25: float
    hour_of_day: int
    day_of_week: str
    weather_desc: str
    wind_speed_kmh: float
    humidity_pct: float


class EnforcementRequest(BaseModel):
    top_cities: list[dict]


class ForecastRequest(BaseModel):
    city: str
    current_aqi: int
    history_24h: list[dict]
    weather_forecast: list[dict]


class AdvisoryRequest(BaseModel):
    city: str
    aqi: int
    aqi_category: str
    language: str
    user_query: str = ""


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/attribution")
async def get_attribution(req: AttributionRequest):
    """
    Returns a source breakdown (traffic, industrial, construction, biomass, other)
    as percentages for a city, reasoned by GPT-4o.
    """
    cached = get_cached_attribution(req.city)
    if cached:
        return cached

    result = await acall_llm_json(
        system=ATTRIBUTION_SYSTEM,
        user=attribution_user(req),
        max_tokens=8000,
    )
    # Attach the actual CPCB study citation server-side (not left to the LLM to
    # echo back faithfully) so the frontend can show a checkable source, not just
    # a percentage the model asserted.
    citation = get_baseline_citation(req.city)
    if citation:
        result["baseline_citation"] = citation
    # Deterministic confidence check: how far did the LLM actually stray from
    # the baseline it was anchored to? See utils/attribution_confidence.py.
    result.update(score_attribution_confidence(req.city, result))
    set_cached_attribution(req.city, result)
    return result


@router.post("/enforcement")
async def get_enforcement(req: EnforcementRequest):
    """
    Enforcement priorities for a caller-supplied set of cities.

    Runs the same geospatial correlation as /enforcement/auto — cities that
    carry lat/lon get their registered sources ranked before the LLM is called.
    Without this the endpoint would hand the LLM the correlation-aware prompt
    with no candidates attached, and every recommendation would come back
    flagged as AQI-only.
    """
    cities = [
        await _enrich_city_with_candidates(c) if c.get("lat") and c.get("lon") else c
        for c in req.top_cities
    ]
    enriched = EnforcementRequest(top_cities=cities)

    result = await acall_llm_json(
        system=ENFORCEMENT_SYSTEM,
        user=enforcement_user(enriched),
        max_tokens=8000,
    )
    result["registry_backed"] = any(c.get("candidate_sources") for c in cities)
    return result


def _forecast_divergence(llm_forecast, baseline: list[dict]) -> dict:
    """
    Mean and max absolute gap between the LLM's forecast and the statistical
    baseline it was told to start from, matched hour by hour.

    This is the honesty check on the accuracy numbers above: the backtest
    measures the *baseline's* skill, and that only carries over to the forecast
    actually shown to the user to the extent the LLM stayed close to it. A large
    divergence means the delivered forecast is substantially the model's own
    invention and the baseline's RMSE no longer describes it.
    """
    if not llm_forecast or not baseline:
        return {"mean_abs": None, "max_abs": None, "matched_hours": 0}

    by_hour = {b["hour"]: b["predicted_aqi"] for b in baseline}
    deltas = [
        abs(f["predicted_aqi"] - by_hour[f["hour"]])
        for f in llm_forecast
        if isinstance(f, dict)
        and f.get("hour") in by_hour
        and isinstance(f.get("predicted_aqi"), (int, float))
    ]
    if not deltas:
        return {"mean_abs": None, "max_abs": None, "matched_hours": 0}
    return {
        "mean_abs": round(mean(deltas), 1),
        "max_abs": round(max(deltas), 1),
        "matched_hours": len(deltas),
    }


@router.post("/forecast")
async def get_forecast(req: ForecastRequest):
    """
    Returns a hybrid 24hr AQI forecast: a deterministic statistical baseline
    (utils/forecast_baseline.py — always computed, free, independently testable)
    plus an LLM narrative that must reconcile with that baseline rather than
    inventing numbers from a blank page.

    Accuracy is reported against persistence — "it will stay as it is now" —
    which is the naive benchmark the evaluation criteria name and the one any
    forecast must beat to have demonstrated skill. Both the statistical
    baseline's RMSE and persistence's own RMSE are returned, so the comparison
    can be checked rather than asserted.
    """
    baseline = compute_baseline_forecast(req.history_24h, req.current_aqi, req.weather_forecast)
    backtest = backtest_baseline(req.history_24h)

    result = await acall_llm_json(
        system=FORECAST_SYSTEM,
        user=forecast_user(req, baseline),
        max_tokens=8000,
    )
    result["baseline_forecast"] = baseline
    result["baseline_backtest_mae"] = backtest["mae"]
    result["baseline_backtest_n"] = backtest["n"]
    result["accuracy"] = {
        "holdout_points": backtest["n"],
        "baseline_rmse": backtest["rmse"],
        "persistence_rmse": backtest["persistence_rmse"],
        "persistence_mae": backtest["persistence_mae"],
        "skill_vs_persistence": backtest["skill_vs_persistence"],
    }

    # How far the LLM moved off the baseline it was anchored to. The baseline's
    # accuracy only transfers to the delivered forecast insofar as the two agree,
    # so quoting the backtest without this would overstate what was verified.
    result["llm_divergence_from_baseline"] = _forecast_divergence(
        result.get("forecast"), baseline
    )
    return result


@router.post("/advisory")
async def get_advisory(req: AdvisoryRequest):
    """Returns a citizen health advisory in the requested language."""
    result = await acall_llm(
        system=ADVISORY_SYSTEM,
        user=advisory_user(req),
        max_tokens=8000,
    )
    return {"advisory": result, "language": req.language, "city": req.city}


@router.get("/sources")
async def get_source_registry(city: str | None = None):
    """
    The registered emission source registry backing enforcement recommendations.

    Exposed so the evidence is inspectable rather than only visible inside a
    prompt: `?city=Delhi` returns that city's mapped facilities with their OSM
    links, and the bare endpoint returns coverage stats and provenance.
    """
    if city:
        sources = get_sources_for_city(city)
        return {"city": city, "count": len(sources), "sources": sources}
    return {
        "available": has_registry(),
        "meta": registry_meta(),
        "stats": registry_stats(),
    }


def _normalise_source_ids(result: dict, cities: list[dict]) -> None:
    """
    Reconcile each priority's source_id with the candidate it actually refers to.

    The prompt lists candidates as "[way/12345] Name", and the LLM frequently
    copies the surrounding brackets into source_id — "[way/12345]" — which then
    fails an exact-match lookup in the frontend, so the evidence block silently
    doesn't render. Strip the brackets, and if that still doesn't match, fall
    back to matching on the facility name before giving up.

    Mutates `result` in place, marking whether each priority resolved so the UI
    can distinguish "matched" from "the model named something not on the list".
    """
    by_id = {}
    by_label = {}
    for c in cities:
        for s in c.get("candidate_sources", []):
            by_id[s["id"]] = s["id"]
            for key in (s.get("dispatch_label"), s.get("name")):
                if key:
                    by_label[key.strip().lower()] = s["id"]

    for p in result.get("priorities", []) or []:
        raw = (p.get("source_id") or "").strip().strip("[]").strip()
        if raw in by_id:
            p["source_id"] = raw
            p["source_matched"] = True
            continue

        label = (p.get("target_facility") or "").strip().lower()
        if label in by_label:
            p["source_id"] = by_label[label]
            p["source_matched"] = True
            continue

        p["source_id"] = raw or None
        p["source_matched"] = False


async def _enrich_city_with_candidates(city: dict) -> dict:
    """
    Run the geospatial correlation for one hotspot: fetch its live wind, pull the
    registered emission sources on file for that city, and rank them with the
    deterministic scorer (utils/enforcement_scoring.py).

    This is the step that turns "Delhi has AQI 380" into "these five mapped
    facilities are within 25 km, upwind, and of the category the Attribution
    Agent blamed" — the correlation the Enforcement Agent then narrates.

    Best-effort per city: no wind reading just means the sources are ranked on
    geometry alone, and no registry entry means this city goes to the LLM
    flagged as AQI-only evidence rather than failing the whole endpoint.
    """
    sources = list(get_sources_for_city(city["city"]))

    # Layer satellite-detected active fires on top of the ground register.
    # Open waste burning is unregistered by definition, so this is the only way
    # it enters the candidate set at all. Additive: no FIRMS key, or no fires
    # today, just means the ground registry stands alone.
    try:
        fires = await fetch_fires_near(city["lat"], city["lon"])
        for f in fires:
            f["city"] = city["city"]
        sources.extend(fires)
        city["satellite_fire_count"] = len(fires)
    except Exception:
        city["satellite_fire_count"] = 0

    # Fetch wind regardless of registry coverage: a city with no mapped sources
    # still reports its conditions to the Enforcement Agent, and returning early
    # here left wind_direction null on exactly the hotspots that most need
    # explaining (the ones with no candidates to show).
    wind_direction = None
    wind_speed = None
    cloudy = False
    try:
        weather = await fetch_weather(city["lat"], city["lon"])
        wind_direction = weather.get("wind_direction")
        wind_speed = weather.get("wind_speed_kmh")
        cloudy = is_cloudy(weather.get("description"))
        city["wind_direction"] = wind_direction
        city["wind_speed_kmh"] = wind_speed
        city["weather_description"] = weather.get("description")
    except Exception:
        pass

    if not sources:
        city["candidate_sources"] = []
        return city

    # Atmospheric stability depends on solar heating, so the plume model needs to
    # know whether the sun is up. Indian cities all sit in IST, and the station's
    # own local time is what governs its boundary layer.
    hour = datetime.now().hour
    is_daytime = 7 <= hour < 18

    city["candidate_sources"] = score_sources(
        hotspot=city,
        sources=sources,
        wind_direction_deg=wind_direction,
        dominant_source=city.get("dominant_source"),
        limit=5,
        wind_speed_kmh=wind_speed,
        is_daytime=is_daytime,
        cloudy=cloudy,
    )
    return city


async def _attribute_city(city: dict) -> str | None:
    """
    Run the Source Attribution Agent for one city so the Enforcement Agent can
    reason from *why* a city is polluted, not just its raw AQI number. Best-effort:
    a failure here (LLM timeout, missing weather) just means that one city goes
    into enforcement without a dominant_source hint, not that the whole endpoint fails.
    """
    try:
        cached = get_cached_attribution(city["city"])
        if cached:
            return cached.get("dominant_source")

        weather = await fetch_weather(city["lat"], city["lon"])
        now = datetime.now()
        attr_req = AttributionRequest(
            city=city["city"], state=city.get("state", ""),
            aqi=city["aqi"], pm25=city.get("pm25") or 0,
            hour_of_day=now.hour, day_of_week=now.strftime("%A"),
            weather_desc=weather.get("description", "clear"),
            wind_speed_kmh=weather.get("wind_speed_kmh", 0),
            humidity_pct=weather.get("humidity_pct", 50),
        )
        result = await acall_llm_json(
            system=ATTRIBUTION_SYSTEM, user=attribution_user(attr_req), max_tokens=8000,
        )
        set_cached_attribution(city["city"], result)
        return result.get("dominant_source")
    except Exception:
        return None


@router.get("/enforcement/auto")
async def get_auto_enforcement():
    """
    Convenience endpoint: fetches live data internally and returns enforcement reco
    without requiring the frontend to pass city data.

    Three-stage chain, deterministic where it can be:

      1. Source Attribution Agent (LLM) — why is each hotspot polluted?
      2. Geospatial correlation (arithmetic, utils/enforcement_scoring.py) —
         which *registered* emission sources are near, upwind of, and
         category-matched to each hotspot? This is the stage that grounds the
         recommendation in a real mapped facility instead of an invented zone.
      3. Enforcement Agent (LLM) — turn that ranked shortlist into dispatchable
         actions, citing the distance/upwind evidence it was handed.

    Also reports `response_time_seconds`: elapsed time from reading the hotspot
    signal to having a dispatch-ready recommendation. The problem statement's
    evaluation focus asks for demonstrated reduction in signal-to-intervention
    time, so it's measured rather than asserted.
    """
    signal_at = datetime.now()
    try:
        from services.cache import get_cached_stations
        from services.waqi import fetch_india_stations

        stations = get_cached_stations()
        if not stations:
            stations = await fetch_india_stations()

        # Guard against None/non-numeric aqi values from any data source
        valid = [s for s in stations if isinstance(s.get("aqi"), (int, float))]
        top5 = sorted(valid, key=lambda x: x["aqi"], reverse=True)[:5]
        if not top5:
            raise HTTPException(status_code=503, detail="No valid station data available")

        dominant_sources = await asyncio.gather(*[_attribute_city(c) for c in top5])
        attributed_sources = {}
        for city, source in zip(top5, dominant_sources):
            if source:
                city["dominant_source"] = source
                attributed_sources[city["city"]] = source

        # Stage 2: correlate each hotspot against the registered source registry.
        # Runs after attribution so the category match can use dominant_source.
        top5 = list(await asyncio.gather(*[_enrich_city_with_candidates(c) for c in top5]))

        req = EnforcementRequest(top_cities=top5)
        result = await acall_llm_json(
            system=ENFORCEMENT_SYSTEM,
            user=enforcement_user(req),
            max_tokens=8000,
        )
        # Only claim the multi-agent chain actually ran if at least one city
        # got a real attribution result — otherwise this silently degrades to
        # AQI-only enforcement and callers shouldn't be told otherwise.
        result["multi_agent"] = bool(attributed_sources)

        # Echo the correlation evidence back so the frontend can map it and a
        # reviewer can audit why each facility was chosen — the LLM's prose is
        # the narration, this is the underlying record.
        result["hotspots"] = [
            {
                "city": c["city"],
                "lat": c["lat"],
                "lon": c["lon"],
                "aqi": c["aqi"],
                "label": c.get("label"),
                "dominant_source": c.get("dominant_source"),
                "wind_direction": c.get("wind_direction"),
                "wind_speed_kmh": c.get("wind_speed_kmh"),
                "satellite_fire_count": c.get("satellite_fire_count", 0),
                "in_registry": bool(c.get("candidate_sources")),
                "candidate_sources": c.get("candidate_sources", []),
            }
            for c in top5
        ]
        _normalise_source_ids(result, top5)
        result["registry_backed"] = any(c.get("candidate_sources") for c in top5)
        result["registry_meta"] = registry_meta()

        # Report the satellite layer's state explicitly. "Enabled but zero
        # detections" and "not configured" look identical in the output
        # otherwise, and they mean very different things: the first is a real
        # finding (nothing is burning near these hotspots — expected outside
        # the Oct-Jan burning season), the second is a missing capability.
        result["satellite"] = {
            "enabled": firms_enabled(),
            "total_detections": sum(c.get("satellite_fire_count", 0) for c in top5),
        }
        result["attributed_sources"] = attributed_sources
        result["signal_at"] = signal_at.isoformat(timespec="seconds")
        result["response_time_seconds"] = round(
            (datetime.now() - signal_at).total_seconds(), 1
        )
        # Impact figures computed from this run's own data, so the numbers a
        # deck quotes stay tied to what the system actually did rather than
        # being typed into a slide once and left to rot.
        result["impact"] = enforcement_impact(result)
        return result
    except HTTPException:
        raise
    except Exception as exc:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
