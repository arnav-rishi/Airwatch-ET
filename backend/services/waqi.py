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


def _fallback_station(city: dict) -> dict:
    """Build a station dict from a curated city's static last-known reading.

    Used when that specific city's live WAQI feed fails or has no current
    reading, so a bad/stale slug or a single flaky request drops only that
    one city's freshness — never the city itself off the map.
    """
    cat = aqi_category(city["aqi"])
    return {
        "city": city["city"],
        "state": city["state"],
        "lat": city["lat"],
        "lon": city["lon"],
        "aqi": city["aqi"],
        "pm25": city.get("pm25"),
        "primary_pollutant": city.get("primary_pollutant", "PM2.5"),
        "station_raw": city["city"],
        "updated_at": city.get("updated_at", ""),
        "source": "fallback",
        **cat,
        "radius": circle_radius(city["aqi"]),
    }


async def _fetch_city_live(client: httpx.AsyncClient, city: dict) -> dict:
    """
    Fetch live AQI for one curated city via WAQI's named city feed (/feed/{slug}/).
    Returns a live station dict when the feed has a real current reading; otherwise
    falls back to that city's static last-known reading so it never disappears
    from the map — it just won't be tagged "waqi_live".
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
            return _fallback_station(city)

        d = data["data"]
        raw_aqi = d.get("aqi")
        # WAQI reports "-" when a station has no current reading — use fallback.
        if not isinstance(raw_aqi, int):
            return _fallback_station(city)

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
        return _fallback_station(city)


async def fetch_india_stations() -> list[dict]:
    """
    Fetch live AQI for a curated list of major Indian cities from WAQI (named feeds,
    in parallel). Every curated city is always returned — one whose live feed fails
    falls back to its own last-known static reading (source="fallback") rather than
    being dropped, so the map always shows the full curated set.

    If constructing the HTTP client itself fails (rare), falls back to OpenAQ, then
    the full static dataset, so the app is never blank.
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
