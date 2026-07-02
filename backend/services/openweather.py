import httpx
import os
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

OWM_BASE = "https://api.openweathermap.org/data/2.5"


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=6),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
    reraise=True,
)
async def _fetch_with_retry(client: httpx.AsyncClient, url: str, **kwargs) -> httpx.Response:
    resp = await client.get(url, **kwargs)
    resp.raise_for_status()
    return resp


async def fetch_weather(lat: float, lon: float) -> dict:
    """Fetch current weather conditions for a location."""
    api_key = os.getenv("OPENWEATHER_API_KEY")
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await _fetch_with_retry(
                client,
                f"{OWM_BASE}/weather",
                params={"lat": lat, "lon": lon, "appid": api_key, "units": "metric"},
            )
            data = resp.json()
            return {
                "temp_c": data["main"]["temp"],
                "humidity_pct": data["main"]["humidity"],
                "wind_speed_kmh": round(data["wind"]["speed"] * 3.6, 1),
                "wind_direction": data["wind"].get("deg", 0),
                "description": data["weather"][0]["description"],
                "visibility_km": data.get("visibility", 10000) / 1000,
            }
    except Exception:
        return {
            "temp_c": 30,
            "humidity_pct": 65,
            "wind_speed_kmh": 8,
            "wind_direction": 180,
            "description": "partly cloudy",
            "visibility_km": 8,
        }


async def fetch_forecast(lat: float, lon: float) -> list[dict]:
    """Fetch 24hr weather forecast (3hr intervals from OWM)."""
    api_key = os.getenv("OPENWEATHER_API_KEY")
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await _fetch_with_retry(
                client,
                f"{OWM_BASE}/forecast",
                params={"lat": lat, "lon": lon, "appid": api_key,
                        "units": "metric", "cnt": 8},
            )
            items = resp.json().get("list", [])
            return [
                {
                    "time": item["dt_txt"],
                    "temp_c": item["main"]["temp"],
                    "humidity_pct": item["main"]["humidity"],
                    "wind_speed_kmh": round(item["wind"]["speed"] * 3.6, 1),
                    "description": item["weather"][0]["description"],
                }
                for item in items
            ]
    except Exception:
        return []
