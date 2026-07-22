"""
OpenAQ v3 — the primary AQI source.

Why this replaces WAQI as primary
---------------------------------
WAQI's named city feeds return whatever a station last reported, however old,
with no staleness signal in the part of the payload the app was reading. Audited
across 84 curated cities, only **4** had a reading under 6 hours old. The rest
ranged from days to *years*: Pune's feed was serving a reading 1,710 days old,
Jodhpur's 2,440 days. Those readings were driving the enforcement hotspot
ranking, which meant inspectors were being pointed at cities on the strength of
observations from 2021.

OpenAQ v3 carries a per-reading UTC timestamp, so staleness is detectable rather
than invisible, and its Indian coverage is far better: 2,059 readings inside the
India bounding box, 1,303 of them under 24 hours old.

It also returns **real PM2.5 concentrations in ug/m3**, not the US EPA sub-index
WAQI serves. That removes an entire class of bug — the concentration goes
straight into pm25_to_aqi() with no EPA inversion step, so there is no scale to
get wrong.

Fetch strategy
--------------
/parameters/2/latest returns the latest PM2.5 reading globally, and — despite
accepting them — ignores the `iso`, `bbox` and `coordinates` filters entirely
(all three return the same 20,200 global rows). So the only workable approach is
to page the global set and filter to India client-side: 21 pages, ~40 seconds,
cached for CACHE_TTL_MINUTES. Verified, not assumed.
"""
import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from math import cos, radians
from pathlib import Path

import httpx

from utils.aqi_calculator import aqi_category, circle_radius, pm25_to_aqi

logger = logging.getLogger(__name__)

OPENAQ_BASE = "https://api.openaq.org/v3"
PM25_PARAMETER_ID = 2
FALLBACK_PATH = Path(__file__).parent.parent / "data" / "cities_fallback.json"

# India bounding box, matching services/waqi.py.
LAT_MIN, LON_MIN, LAT_MAX, LON_MAX = 8.07, 68.20, 37.08, 97.40

# A reading older than this is not "current air quality" and must not drive an
# enforcement recommendation. 24h is deliberately generous — many CPCB stations
# report a few times a day — but it is two orders of magnitude tighter than the
# years-old data that motivated this rewrite.
MAX_READING_AGE_HOURS = 24

# How far from a city centre a station can be and still represent that city.
CITY_RADIUS_KM = 25.0

# PM2.5 above this is treated as a sensor fault, not a reading. India's worst
# recorded hourly city averages sit around 900-1000 ug/m3 in peak Delhi winter
# smog, but that is a whole-city average during a severe episode; a lone station
# reporting past this in isolation (especially outside the Oct-Jan season) is far
# more likely a stuck or miscalibrated sensor. Left in, one such value would top
# the national enforcement ranking on its own — Aurangabad surfaced at a flat 520
# from a single industrial-estate monitor during monsoon, which is not credible.
# Readings above the cap are dropped from the city's set rather than clamped, so
# a genuine high stays represented by its plausible neighbours.
MAX_PLAUSIBLE_PM25 = 500.0

MAX_PAGES = 25
PAGE_SIZE = 1000

_cache: dict = {"readings": None, "fetched_at": None}
CACHE_TTL_MINUTES = 10


def _api_key() -> str | None:
    return os.getenv("OPENAQ_API_KEY")


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    from math import asin, sin, sqrt
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * 6371.0 * asin(sqrt(a))


def _parse_reading(row: dict, now: datetime) -> dict | None:
    coords = row.get("coordinates") or {}
    lat, lon = coords.get("latitude"), coords.get("longitude")
    if lat is None or lon is None:
        return None
    if not (LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX):
        return None

    value = row.get("value")
    # Negative values are sensor faults; OpenAQ passes them through unfiltered.
    # Implausibly high values are almost always stuck sensors — see the constant.
    if not isinstance(value, (int, float)) or value < 0 or value > MAX_PLAUSIBLE_PM25:
        return None

    stamp = (row.get("datetime") or {}).get("utc")
    if not stamp:
        return None
    try:
        observed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None

    return {
        "lat": lat,
        "lon": lon,
        "pm25": round(float(value), 1),
        "observed_at": observed.isoformat(timespec="seconds"),
        "age_hours": round((now - observed).total_seconds() / 3600, 1),
        "location_id": row.get("locationsId"),
    }


async def fetch_india_readings(force: bool = False) -> list[dict]:
    """
    Every recent PM2.5 reading inside the India bounding box, newest first.

    Cached: a full sweep is 21 sequential pages and takes ~40 s, which is far too
    slow to sit in a request path.
    """
    key = _api_key()
    if not key:
        logger.warning("OPENAQ_API_KEY not set — OpenAQ unavailable, falling back to WAQI")
        return []

    cached, fetched = _cache["readings"], _cache["fetched_at"]
    if not force and cached is not None and fetched:
        if datetime.utcnow() - fetched < timedelta(minutes=CACHE_TTL_MINUTES):
            return cached

    now = datetime.now(timezone.utc)
    readings: list[dict] = []
    try:
        async with httpx.AsyncClient(headers={"X-API-Key": key}, timeout=30.0) as client:
            for page in range(1, MAX_PAGES + 1):
                resp = await client.get(
                    f"{OPENAQ_BASE}/parameters/{PM25_PARAMETER_ID}/latest",
                    params={"limit": PAGE_SIZE, "page": page},
                )
                resp.raise_for_status()
                rows = resp.json().get("results", [])
                for row in rows:
                    parsed = _parse_reading(row, now)
                    if parsed:
                        readings.append(parsed)
                if len(rows) < PAGE_SIZE:
                    break
    except Exception as exc:
        logger.error("OpenAQ fetch failed (%s) — falling back", exc)
        # Serve a stale cache rather than nothing; it is still better than WAQI's
        # years-old feeds, and the age is reported either way.
        return cached or []

    readings.sort(key=lambda r: r["age_hours"])
    _cache["readings"] = readings
    _cache["fetched_at"] = datetime.utcnow()
    logger.info(
        "OpenAQ: %d India readings, %d fresh (<=%dh)",
        len(readings),
        sum(1 for r in readings if r["age_hours"] <= MAX_READING_AGE_HOURS),
        MAX_READING_AGE_HOURS,
    )
    return readings


def _median(values: list[float]) -> float:
    s = sorted(values)
    mid = len(s) // 2
    return s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2


def _city_station(city: dict, readings: list[dict]) -> dict | None:
    """
    Build one city-level station from the fresh readings around it.

    Uses the **median** of nearby stations rather than the maximum. The maximum
    is what CPCB reports for a city, but this registry mixes reference-grade
    monitors with low-cost sensors, and a single faulty unit reading 400 ug/m3
    would put that city at the top of the enforcement ranking on its own. The
    worst station is reported alongside as `pm25_max` so the signal isn't lost.
    """
    nearby = [
        r for r in readings
        if r["age_hours"] <= MAX_READING_AGE_HOURS
        and _haversine_km(city["lat"], city["lon"], r["lat"], r["lon"]) <= CITY_RADIUS_KM
    ]
    if not nearby:
        return None

    values = [r["pm25"] for r in nearby]
    pm25 = round(_median(values), 1)
    aqi = pm25_to_aqi(pm25)
    freshest = min(nearby, key=lambda r: r["age_hours"])

    return {
        "city": city["city"],
        "state": city["state"],
        "lat": city["lat"],
        "lon": city["lon"],
        "aqi": aqi,
        "pm25": pm25,
        "pm25_max": round(max(values), 1),
        "aqi_scale": "CPCB",
        "primary_pollutant": "PM2.5",
        "station_count": len(nearby),
        "observed_at": freshest["observed_at"],
        "age_hours": freshest["age_hours"],
        "source": "openaq_live",
        **aqi_category(aqi),
        "radius": circle_radius(aqi),
    }


def load_fallback() -> list[dict]:
    with open(FALLBACK_PATH, encoding="utf-8") as f:
        data = json.load(f)
    for city in data:
        city.update(aqi_category(city["aqi"]))
        city["radius"] = circle_radius(city["aqi"])
        city["source"] = "fallback"
        city.setdefault("age_hours", None)
    return data


async def fetch_live_aqi() -> list[dict]:
    """
    Live city-level AQI from OpenAQ, on the CPCB scale.

    Returns only cities with a genuinely fresh reading. Cities without one are
    left out so the caller (services/waqi.py) can fill them from its own source
    or from the static dataset — the point is that a city is never presented as
    live on the strength of an old reading.
    """
    readings = await fetch_india_readings()
    if not readings:
        return []

    with open(FALLBACK_PATH, encoding="utf-8") as f:
        cities = json.load(f)

    stations = [s for s in (_city_station(c, readings) for c in cities) if s]
    logger.info("OpenAQ produced %d/%d cities with fresh readings", len(stations), len(cities))
    return stations


async def fetch_city_history(city_name: str, lat: float, lon: float) -> dict:
    """
    Last 24 hourly PM2.5 readings near a point.

    Uses the sensor behind the closest fresh station, since /sensors/{id}/hours
    is the v3 endpoint that returns an actual time series. Falls back to a
    modelled diurnal curve when no sensor has usable history — tagged as such,
    so the frontend can disclose it rather than passing off a synthetic line as
    measurement.
    """
    key = _api_key()
    if not key:
        return {"points": _generate_synthetic_history(city_name), "source": "synthetic_diurnal"}

    try:
        async with httpx.AsyncClient(headers={"X-API-Key": key}, timeout=20.0) as client:
            loc_resp = await client.get(
                f"{OPENAQ_BASE}/locations",
                params={
                    "coordinates": f"{lat},{lon}",
                    "radius": int(CITY_RADIUS_KM * 1000),
                    "parameters_id": PM25_PARAMETER_ID,
                    "limit": 5,
                },
            )
            loc_resp.raise_for_status()
            locations = loc_resp.json().get("results", [])

            sensor_id = None
            for loc in locations:
                for sensor in loc.get("sensors", []):
                    if (sensor.get("parameter") or {}).get("id") == PM25_PARAMETER_ID:
                        sensor_id = sensor["id"]
                        break
                if sensor_id:
                    break
            if not sensor_id:
                raise ValueError("no PM2.5 sensor nearby")

            hist_resp = await client.get(
                f"{OPENAQ_BASE}/sensors/{sensor_id}/hours",
                params={"limit": 24},
            )
            hist_resp.raise_for_status()
            rows = hist_resp.json().get("results", [])

        points = []
        for row in rows:
            value = row.get("value")
            if not isinstance(value, (int, float)) or value < 0:
                continue
            period = (row.get("period") or {}).get("datetimeFrom") or {}
            stamp = period.get("local") or period.get("utc") or ""
            points.append({
                "hour": stamp[11:16] if len(stamp) >= 16 else stamp,
                "aqi": pm25_to_aqi(value),
                "pm25": round(float(value), 1),
            })

        if len(points) < 4:
            raise ValueError("insufficient history")
        return {"points": list(reversed(points)), "source": "openaq_measurements"}

    except Exception as exc:
        logger.info("OpenAQ history unavailable for %s (%s) — using modelled curve", city_name, exc)
        return {"points": _generate_synthetic_history(city_name), "source": "synthetic_diurnal"}


def _generate_synthetic_history(city_name: str) -> list[dict]:
    """
    Plausible 24h AQI history when no real series is available.

    Uses a diurnal pattern (higher at rush hours, lower at night). Always tagged
    "synthetic_diurnal" so the UI can label it as a modelled estimate.
    """
    import random
    base_values = {
        "Delhi": 210, "Mumbai": 145, "Kolkata": 175, "Chennai": 110,
        "Bengaluru": 95, "Hyderabad": 130, "Jaipur": 185, "Lucknow": 200,
        "Kanpur": 220, "Patna": 195, "Ahmedabad": 165, "Pune": 120,
    }
    base = base_values.get(city_name, 140)
    diurnal = [0.7, 0.65, 0.6, 0.58, 0.6, 0.72, 0.88, 1.05, 1.1, 1.0, 0.95, 0.9,
               0.88, 0.9, 0.92, 0.95, 1.05, 1.15, 1.2, 1.1, 1.0, 0.92, 0.85, 0.75]
    now = datetime.now(timezone.utc)
    history = []
    for i, factor in enumerate(diurnal):
        t = now + timedelta(hours=i - 23)
        pm25 = (base * factor * 0.38) + random.uniform(-3, 3)
        history.append({
            "hour": t.strftime("%H:%M"),
            "aqi": pm25_to_aqi(max(0, pm25)),
            "pm25": round(max(0, pm25), 1),
        })
    return history
