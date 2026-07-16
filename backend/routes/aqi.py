import asyncio
from fastapi import APIRouter
from services.waqi import fetch_india_stations, fetch_city_feed
from services.openaq import fetch_city_history
from services.openweather import fetch_weather, fetch_forecast
from services.cache import get_cached_stations, set_cached_stations

router = APIRouter()


@router.get("/live")
async def get_live_aqi():
    """
    Returns all India AQI stations for map rendering.
    Serves from startup cache if fresh, else re-fetches live.
    """
    cached = get_cached_stations()
    if cached:
        return {"count": len(cached), "stations": cached, "from_cache": True}
    stations = await fetch_india_stations()
    set_cached_stations(stations)
    return {"count": len(stations), "stations": stations, "from_cache": False}


@router.get("/city/{city_name}")
async def get_city_detail(city_name: str, lat: float, lon: float):
    """
    Full city feed: real pollutant breakdown (PM2.5, PM10, NO2, O3)
    + 24hr history + real weather + weather forecast for LLM attribution/forecast context.
    """
    feed, weather, weather_forecast, history_result = await asyncio.gather(
        fetch_city_feed(city_name),
        fetch_weather(lat, lon),
        fetch_forecast(lat, lon),
        fetch_city_history(city_name, lat, lon),
    )
    return {
        "city": city_name,
        "lat": lat,
        "lon": lon,
        "feed": feed,
        "weather": weather,
        "weather_forecast": weather_forecast,
        "history": history_result["points"],
        "history_source": history_result["source"],
    }
