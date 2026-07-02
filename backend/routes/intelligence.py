from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services.llm import call_llm, call_llm_json
from services.openweather import fetch_weather, fetch_forecast
from utils.aqi_calculator import aqi_category
from prompts import (
    ATTRIBUTION_SYSTEM, attribution_user,
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
        max_tokens=6000,
    )
    return result


@router.post("/enforcement")
async def get_enforcement(req: EnforcementRequest):
    """Returns today's top 3 enforcement priorities across the submitted cities."""
    result = call_llm_json(
        system=ENFORCEMENT_SYSTEM,
        user=enforcement_user(req),
        max_tokens=6000,
    )
    return result


@router.post("/forecast")
async def get_forecast(req: ForecastRequest):
    """Returns a 24hr AQI forecast as hourly values + narrative."""
    result = call_llm_json(
        system=FORECAST_SYSTEM,
        user=forecast_user(req),
        max_tokens=6000,
    )
    return result


@router.post("/advisory")
async def get_advisory(req: AdvisoryRequest):
    """Returns a citizen health advisory in the requested language."""
    result = call_llm(
        system=ADVISORY_SYSTEM,
        user=advisory_user(req),
        max_tokens=6000,
    )
    return {"advisory": result, "language": req.language, "city": req.city}


@router.get("/enforcement/auto")
async def get_auto_enforcement():
    """
    Convenience endpoint: fetches live data internally and returns enforcement reco
    without requiring the frontend to pass city data.
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

        req = EnforcementRequest(top_cities=top5)
        result = call_llm_json(
            system=ENFORCEMENT_SYSTEM,
            user=enforcement_user(req),
            max_tokens=8000,
        )
        return result
    except HTTPException:
        raise
    except Exception as exc:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
