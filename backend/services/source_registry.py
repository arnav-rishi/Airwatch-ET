"""
Access layer for the registered emission source registry
(data/emission_sources.json, seeded by scripts/fetch_emission_sources.py).

The registry is read once at import and indexed by city, because it's static
between seed runs and small enough to hold in memory — re-reading it per
request would add I/O to the enforcement path for no benefit.

If the registry file is absent or unreadable, every lookup returns empty rather
than raising. The Enforcement Agent degrades to its previous AQI-only behaviour
and says so in the response, which is a worse answer but still an answer — a
missing data file shouldn't take down the endpoint.
"""
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

REGISTRY_PATH = Path(__file__).parent.parent / "data" / "emission_sources.json"

_by_city: dict[str, list[dict]] = {}
_meta: dict = {}


def _load() -> None:
    global _by_city, _meta
    try:
        with open(REGISTRY_PATH, encoding="utf-8") as f:
            payload = json.load(f)
    except FileNotFoundError:
        logger.warning(
            "Emission source registry not found at %s — enforcement will fall back "
            "to AQI-only reasoning. Run scripts/fetch_emission_sources.py to seed it.",
            REGISTRY_PATH,
        )
        return
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Emission source registry unreadable (%s) — falling back to AQI-only.", exc)
        return

    _meta = payload.get("_meta", {})
    index: dict[str, list[dict]] = {}
    for source in payload.get("sources", []):
        index.setdefault(source["city"], []).append(source)
    _by_city = index
    logger.info(
        "Loaded %d emission sources across %d cities",
        sum(len(v) for v in index.values()), len(index),
    )


_load()


def get_sources_for_city(city: str) -> list[dict]:
    """Registered emission sources for a city; empty list if none are on file."""
    return _by_city.get(city, [])


def has_registry() -> bool:
    return bool(_by_city)


def registry_meta() -> dict:
    """
    Provenance for the registry — upstream, licence, and the caveat about OSM
    standing in for an official register. Surfaced through the API so the
    frontend can attribute the data instead of presenting it as authoritative.
    """
    return dict(_meta)


def registry_stats() -> dict:
    by_category: dict[str, int] = {}
    for sources in _by_city.values():
        for s in sources:
            by_category[s["category"]] = by_category.get(s["category"], 0) + 1
    return {
        "total_sources": sum(len(v) for v in _by_city.values()),
        "cities_covered": len(_by_city),
        "by_category": by_category,
    }
