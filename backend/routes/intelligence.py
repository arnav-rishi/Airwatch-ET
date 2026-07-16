import asyncio
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services.llm import call_llm, call_llm_json
from services.openweather import fetch_weather, fetch_forecast
from utils.aqi_calculator import aqi_category
from utils.attribution_confidence import score_attribution_confidence
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
    result = call_llm_json(
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
    return result


@router.post("/enforcement")
async def get_enforcement(req: EnforcementRequest):
    """Returns today's top 3 enforcement priorities across the submitted cities."""
    result = call_llm_json(
        system=ENFORCEMENT_SYSTEM,
        user=enforcement_user(req),
        max_tokens=8000,
    )
    return result


@router.post("/forecast")
async def get_forecast(req: ForecastRequest):
    """
    Returns a hybrid 24hr AQI forecast: a deterministic statistical baseline
    (utils/forecast_baseline.py — always computed, free, independently testable)
    plus an LLM narrative that must reconcile with that baseline rather than
    inventing numbers from a blank page. Also reports the baseline's own
    backtested MAE against real held-out history, so the forecast carries an
    actual accuracy number instead of an unverifiable claim.
    """
    baseline = compute_baseline_forecast(req.history_24h, req.current_aqi, req.weather_forecast)
    backtest = backtest_baseline(req.history_24h)

    result = call_llm_json(
        system=FORECAST_SYSTEM,
        user=forecast_user(req, baseline),
        max_tokens=8000,
    )
    result["baseline_forecast"] = baseline
    result["baseline_backtest_mae"] = backtest["mae"]
    result["baseline_backtest_n"] = backtest["n"]
    return result


@router.post("/advisory")
async def get_advisory(req: AdvisoryRequest):
    """Returns a citizen health advisory in the requested language."""
    result = call_llm(
        system=ADVISORY_SYSTEM,
        user=advisory_user(req),
        max_tokens=8000,
    )
    return {"advisory": result, "language": req.language, "city": req.city}


async def _attribute_city(city: dict) -> str | None:
    """
    Run the Source Attribution Agent for one city so the Enforcement Agent can
    reason from *why* a city is polluted, not just its raw AQI number. Best-effort:
    a failure here (LLM timeout, missing weather) just means that one city goes
    into enforcement without a dominant_source hint, not that the whole endpoint fails.
    """
    try:
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
        result = call_llm_json(
            system=ATTRIBUTION_SYSTEM, user=attribution_user(attr_req), max_tokens=8000,
        )
        return result.get("dominant_source")
    except Exception:
        return None


@router.get("/enforcement/auto")
async def get_auto_enforcement():
    """
    Convenience endpoint: fetches live data internally and returns enforcement reco
    without requiring the frontend to pass city data.

    Multi-agent chain: the Source Attribution Agent runs first (in parallel) for
    each of the top-5 cities, and its dominant_source finding is handed to the
    Enforcement Agent as evidence — enforcement recommendations are grounded in
    an upstream agent's reasoning, not independently re-guessed from AQI alone.
    """
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

        req = EnforcementRequest(top_cities=top5)
        result = call_llm_json(
            system=ENFORCEMENT_SYSTEM,
            user=enforcement_user(req),
            max_tokens=8000,
        )
        result["multi_agent"] = True
        result["attributed_sources"] = attributed_sources
        return result
    except HTTPException:
        raise
    except Exception as exc:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
