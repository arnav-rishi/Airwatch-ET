import asyncio
import httpx
import os
import json
from pathlib import Path
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from utils.aqi_calculator import pm25_to_aqi, epa_aqi_to_pm25, aqi_category, circle_radius

WAQI_BASE = "https://api.waqi.info"
FALLBACK_PATH = Path(__file__).parent.parent / "data" / "cities_fallback.json"

# India bounding box: SW corner (8.07, 68.20) → NE corner (37.08, 97.40)
INDIA_BOUNDS = "8.07,68.20,37.08,97.40"
_INDIA_MIN_LAT, _INDIA_MIN_LON, _INDIA_MAX_LAT, _INDIA_MAX_LON = (
    float(v) for v in INDIA_BOUNDS.split(",")
)


def _in_india(lat: float, lon: float) -> bool:
    return _INDIA_MIN_LAT <= lat <= _INDIA_MAX_LAT and _INDIA_MIN_LON <= lon <= _INDIA_MAX_LON


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

        # WAQI's `aqi` and `iaqi.pm25.v` are both US EPA AQI *index* values, not
        # μg/m³ concentrations. Recover the concentration, then re-express it on
        # India's CPCB scale — otherwise live cities would sit on the EPA scale
        # while fallback cities (cities_fallback.json) sit on CPCB, and the two
        # would be silently mixed in every comparison downstream, most damagingly
        # the enforcement hotspot ranking in routes/intelligence.py.
        pm25_index = d.get("iaqi", {}).get("pm25", {}).get("v")
        pm25 = epa_aqi_to_pm25(pm25_index) if pm25_index is not None else None
        cpcb_aqi = pm25_to_aqi(pm25) if pm25 is not None else pm25_to_aqi(epa_aqi_to_pm25(raw_aqi))

        # Prefer the station's own coordinates so the pin sits on the real station.
        geo = d.get("city", {}).get("geo") or [city["lat"], city["lon"]]
        lat, lon = float(geo[0]), float(geo[1])

        # Some city-name slugs collide with a same-named place abroad (e.g.
        # "kochi" also resolves to Kōchi, Japan on WAQI). If the station WAQI
        # actually returned isn't in India, this isn't our curated city's data
        # at all — fall back rather than mislabel a foreign reading as CPCB/India.
        if not _in_india(lat, lon):
            return _fallback_station(city)

        cat = aqi_category(cpcb_aqi)
        return {
            "city": city["city"],
            "state": city["state"],
            "lat": lat,
            "lon": lon,
            "aqi": cpcb_aqi,
            "pm25": pm25,
            # The original US EPA index WAQI served, kept alongside the converted
            # CPCB value so the conversion stays auditable rather than opaque.
            "aqi_epa_raw": raw_aqi,
            "aqi_scale": "CPCB",
            "primary_pollutant": d.get("dominentpol", "pm25").upper(),
            "station_raw": d.get("city", {}).get("name", city["city"]),
            "updated_at": d.get("time", {}).get("s", ""),
            "source": "waqi_live",
            **cat,
            "radius": circle_radius(cpcb_aqi),
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

        # Every iaqi.*.v here is a US EPA AQI sub-index, NOT a μg/m³ concentration.
        # PM2.5 we can invert exactly (epa_aqi_to_pm25), so it's reported as a real
        # concentration. PM10/NO2/O3/CO each need their own EPA breakpoint table to
        # invert; rather than fabricate a conversion, they stay as sub-indices and
        # are named *_index so the frontend can label them honestly instead of
        # printing an index value under a "μg/m³" heading.
        pm25_index = iaqi.get("pm25", {}).get("v")
        pm10_index = iaqi.get("pm10", {}).get("v")
        no2_index  = iaqi.get("no2",  {}).get("v")
        o3_index   = iaqi.get("o3",   {}).get("v")
        co_index   = iaqi.get("co",   {}).get("v")

        pm25 = epa_aqi_to_pm25(pm25_index) if pm25_index is not None else None
        cpcb_aqi = (
            pm25_to_aqi(pm25) if pm25 is not None
            else pm25_to_aqi(epa_aqi_to_pm25(d.get("aqi", 0)))
        )

        forecast_daily = d.get("forecast", {}).get("daily", {})
        pm25_forecast = forecast_daily.get("pm25", [])

        return {
            "city": city_name,
            "aqi": cpcb_aqi,
            "aqi_scale": "CPCB",
            "pm25": pm25,
            "pm10_index": pm10_index,
            "no2_index": no2_index,
            "o3_index": o3_index,
            "co_index": co_index,
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
