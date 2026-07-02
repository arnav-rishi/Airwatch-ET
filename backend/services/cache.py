import asyncio
from datetime import datetime, timedelta
from typing import Optional

_cache: dict = {
    "stations": [],
    "fetched_at": None,
}
CACHE_TTL_MINUTES = 10


async def warm_cache():
    """Called once at FastAPI startup. Pre-fetches all India stations."""
    from services.waqi import fetch_india_stations
    print("[cache] Warming AQI station cache...")
    stations = await fetch_india_stations()
    _cache["stations"] = stations
    _cache["fetched_at"] = datetime.utcnow()
    print(f"[cache] Loaded {len(stations)} stations.")


def get_cached_stations() -> Optional[list[dict]]:
    """Return cached stations if fresh, else None (triggers live fetch)."""
    if not _cache["stations"] or not _cache["fetched_at"]:
        return None
    age = datetime.utcnow() - _cache["fetched_at"]
    if age > timedelta(minutes=CACHE_TTL_MINUTES):
        return None
    return _cache["stations"]


def set_cached_stations(stations: list[dict]):
    _cache["stations"] = stations
    _cache["fetched_at"] = datetime.utcnow()
