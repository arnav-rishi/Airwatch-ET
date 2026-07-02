import httpx
import os
import json
from pathlib import Path
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from utils.aqi_calculator import pm25_to_aqi, aqi_category, circle_radius

WAQI_BASE = "https://api.waqi.info"
FALLBACK_PATH = Path(__file__).parent.parent / "data" / "cities_fallback.json"

# India bounding box: SW corner (8.07, 68.20) → NE corner (37.08, 97.40)
INDIA_BOUNDS = "8.07,68.20,37.08,97.40"


def _load_fallback() -> list[dict]:
    with open(FALLBACK_PATH) as f:
        data = json.load(f)
    for city in data:
        cat = aqi_category(city["aqi"])
        city.update(cat)
        city["radius"] = circle_radius(city["aqi"])
        city["source"] = "fallback"
    return data


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


async def fetch_india_stations() -> list[dict]:
    """
    Fetch all active AQI monitoring stations in India from WAQI.
    Returns list ready for Leaflet map rendering.
    Falls back to OpenAQ, then static JSON.
    """
    token = os.getenv("WAQI_TOKEN")
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await _fetch_with_retry(
                client,
                f"{WAQI_BASE}/map/bounds/",
                params={"latlng": INDIA_BOUNDS, "token": token},
            )
            data = resp.json()

        if data.get("status") != "ok":
            raise ValueError(f"WAQI status: {data.get('status')}")

        stations = []
        for s in data.get("data", []):
            raw_aqi = s.get("aqi")
            if not raw_aqi or raw_aqi == "-":
                continue
            try:
                aqi_val = int(raw_aqi)
            except (ValueError, TypeError):
                continue

            cat = aqi_category(aqi_val)
            geo = s.get("lat"), s.get("lon")
            station_name = s.get("station", {}).get("name", "Unknown")

            stations.append({
                "city": _clean_station_name(station_name),
                "station_raw": station_name,
                "lat": float(geo[0]),
                "lon": float(geo[1]),
                "aqi": aqi_val,
                "pm25": None,
                "primary_pollutant": "PM2.5",
                "updated_at": s.get("station", {}).get("time", ""),
                "source": "waqi_live",
                **cat,
                "radius": circle_radius(aqi_val),
            })

        return stations if len(stations) > 5 else _load_fallback()

    except Exception:
        try:
            from services.openaq import fetch_live_aqi
            return await fetch_live_aqi()
        except Exception:
            return _load_fallback()


async def fetch_city_feed(city_name: str) -> dict:
    """
    Fetch full pollutant breakdown and 24hr data for a specific city.
    Returns dict with aqi, pm25, pm10, no2, o3, co, forecast, and attribution_context.
    """
    token = os.getenv("WAQI_TOKEN")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await _fetch_with_retry(
                client,
                f"{WAQI_BASE}/feed/{city_name.lower()}/",
                params={"token": token},
            )
            data = resp.json()

        if data.get("status") != "ok":
            raise ValueError("WAQI feed status not ok")

        d = data["data"]
        iaqi = d.get("iaqi", {})

        pm25_raw = iaqi.get("pm25", {}).get("v")
        pm10_raw = iaqi.get("pm10", {}).get("v")
        no2_raw  = iaqi.get("no2",  {}).get("v")
        o3_raw   = iaqi.get("o3",   {}).get("v")
        co_raw   = iaqi.get("co",   {}).get("v")

        cpcb_aqi = pm25_to_aqi(pm25_raw) if pm25_raw else d.get("aqi", 0)

        forecast_daily = d.get("forecast", {}).get("daily", {})
        pm25_forecast = forecast_daily.get("pm25", [])

        return {
            "city": city_name,
            "aqi": cpcb_aqi,
            "pm25": pm25_raw,
            "pm10": pm10_raw,
            "no2": no2_raw,
            "o3": o3_raw,
            "co": co_raw,
            "dominant_pollutant": d.get("dominentpol", "pm25").upper(),
            "updated_at": d.get("time", {}).get("s", ""),
            "pm25_forecast": pm25_forecast,
            "source": "waqi_feed",
        }

    except Exception:
        return {}


def _clean_station_name(raw: str) -> str:
    """
    WAQI station names are verbose: 'Delhi - Anand Vihar, Delhi, India'
    → extract city name for display.
    """
    if "," in raw:
        parts = [p.strip() for p in raw.split(",")]
        return parts[-2] if len(parts) >= 2 else parts[0]
    return raw.split("-")[0].strip() if "-" in raw else raw
