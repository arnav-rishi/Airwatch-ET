import httpx
import json
from pathlib import Path
from utils.aqi_calculator import pm25_to_aqi, aqi_category, circle_radius

OPENAQ_BASE = "https://api.openaq.io/v2"
FALLBACK_PATH = Path(__file__).parent.parent / "data" / "cities_fallback.json"


def load_fallback() -> list[dict]:
    with open(FALLBACK_PATH) as f:
        data = json.load(f)
    for city in data:
        city.update(aqi_category(city["aqi"]))
        city["radius"] = circle_radius(city["aqi"])
        city["source"] = "fallback"
    return data


async def fetch_live_aqi() -> list[dict]:
    """
    Fetch latest PM2.5 readings for India from OpenAQ v2.
    Falls back to static JSON if API is unreachable or returns empty.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{OPENAQ_BASE}/latest",
                params={
                    "country": "IN",
                    "parameter": "pm25",
                    "limit": 200,
                    "has_geo": "true",
                },
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])

        if not results:
            return load_fallback()

        stations = []
        for r in results:
            coords = r.get("coordinates")
            if not coords:
                continue
            pm25_vals = [
                m["value"] for m in r.get("measurements", [])
                if m["parameter"] == "pm25" and m["value"] > 0
            ]
            if not pm25_vals:
                continue
            pm25 = pm25_vals[0]
            aqi = pm25_to_aqi(pm25)
            cat = aqi_category(aqi)
            stations.append({
                "city": r.get("city", r.get("location", "Unknown")),
                "location": r.get("location", ""),
                "lat": coords.get("latitude"),
                "lon": coords.get("longitude"),
                "aqi": aqi,
                "pm25": pm25,
                "primary_pollutant": "PM2.5",
                "updated_at": r.get("measurements", [{}])[0].get("lastUpdated", ""),
                **cat,
                "radius": circle_radius(aqi),
            })
        return stations if stations else load_fallback()

    except Exception:
        return load_fallback()


async def fetch_city_history(city_name: str, lat: float, lon: float) -> list[dict]:
    """
    Fetch last 24 hourly PM2.5 readings for a city using coordinates.
    Returns list of {hour, aqi, pm25}.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{OPENAQ_BASE}/measurements",
                params={
                    "coordinates": f"{lat},{lon}",
                    "radius": 15000,
                    "parameter": "pm25",
                    "limit": 24,
                    "order_by": "datetime",
                    "sort": "desc",
                },
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])

        if not results:
            return _generate_synthetic_history(city_name)

        history = []
        for r in results:
            val = r.get("value", 0)
            aqi = pm25_to_aqi(val)
            history.append({
                "hour": r.get("date", {}).get("local", ""),
                "aqi": aqi,
                "pm25": val,
            })
        return list(reversed(history))

    except Exception:
        return _generate_synthetic_history(city_name)


def _generate_synthetic_history(city_name: str) -> list[dict]:
    """
    Generate plausible 24hr AQI history when real data is unavailable.
    Uses a diurnal pattern (higher at rush hours, lower at night).
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
    from datetime import datetime, timedelta
    now = datetime.utcnow()
    history = []
    for i, factor in enumerate(diurnal):
        hour_offset = i - 23
        t = now + timedelta(hours=hour_offset)
        pm25 = (base * factor * 0.38) + random.uniform(-3, 3)
        aqi = pm25_to_aqi(max(0, pm25))
        history.append({
            "hour": t.strftime("%H:%M"),
            "aqi": aqi,
            "pm25": round(max(0, pm25), 1),
        })
    return history
