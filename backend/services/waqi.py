import asyncio
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


def _curated_cities() -> list[dict]:
    """The canonical list of major Indian cities (name, state, coords) to display.

    Sourced from cities_fallback.json so the map is always well-distributed across
    India and identical on every machine. We fetch LIVE AQI for each of these below.
    """
    with open(FALLBACK_PATH) as f:
        return json.load(f)


async def _fetch_city_live(client: httpx.AsyncClient, city: dict) -> dict | None:
    """
    Fetch live AQI for one curated city via WAQI's named city feed (/feed/{slug}/).
    Returns a station dict ONLY if the feed has a real live AQI reading; otherwise
    returns None (the city is skipped — we never pad the map with stale values).
    """
    token = os.getenv("WAQI_TOKEN")
    try:
        resp = await _fetch_with_retry(
            client,
            f"{WAQI_BASE}/feed/{city['slug']}/",
            params={"token": token},
        )
        data = resp.json()
        if data.get("status") != "ok":
            return None

        d = data["data"]
        raw_aqi = d.get("aqi")
        # WAQI reports "-" when a station has no current reading — skip those.
        if not isinstance(raw_aqi, int):
            return None

        pm25 = d.get("iaqi", {}).get("pm25", {}).get("v")
        # Prefer the station's own coordinates so the pin sits on the real station.
        geo = d.get("city", {}).get("geo") or [city["lat"], city["lon"]]

        cat = aqi_category(raw_aqi)
        return {
            "city": city["city"],
            "state": city["state"],
            "lat": float(geo[0]),
            "lon": float(geo[1]),
            "aqi": raw_aqi,
            "pm25": pm25,
            "primary_pollutant": d.get("dominentpol", "pm25").upper(),
            "station_raw": d.get("city", {}).get("name", city["city"]),
            "updated_at": d.get("time", {}).get("s", ""),
            "source": "waqi_live",
            **cat,
            "radius": circle_radius(raw_aqi),
        }
    except Exception:
        return None


async def fetch_india_stations() -> list[dict]:
    """
    Fetch live AQI for a curated list of major Indian cities from WAQI (named feeds,
    in parallel). Returns ONLY cities that have a real live reading right now.

    If WAQI is entirely unreachable (network/token failure → zero live cities), the
    full static dataset is returned so the app is never blank. When live data exists,
    no static cities are mixed in.
    """
    cities = _curated_cities()
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            results = await asyncio.gather(
                *[_fetch_city_live(client, c) for c in cities],
                return_exceptions=True,
            )
        stations = [r for r in results if isinstance(r, dict)]
        if stations:
            return stations
        # Total WAQI failure — try OpenAQ, then static.
        try:
            from services.openaq import fetch_live_aqi
            live = await fetch_live_aqi()
            if live:
                return live
        except Exception:
            pass
        return _load_fallback()
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
