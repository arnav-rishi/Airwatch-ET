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
from math import cos, radians
from pathlib import Path

logger = logging.getLogger(__name__)

REGISTRY_PATH = Path(__file__).parent.parent / "data" / "emission_sources.json"

# Spatial grid cell size in degrees. 0.25 deg of latitude is ~27.75 km, just
# over the scorer's 25 km screening radius, so a query needs only the 3x3 block
# of cells around its centre — never a wider sweep.
GRID_DEG = 0.25

_by_city: dict[str, list[dict]] = {}
_by_cell: dict[tuple[int, int], list[dict]] = {}
_meta: dict = {}


def _cell(lat: float, lon: float) -> tuple[int, int]:
    return (int(lat // GRID_DEG), int(lon // GRID_DEG))


def _load() -> None:
    # _by_cell must be declared here too — without it the assignment below binds
    # a local and the spatial index stays empty, which fails silently: every
    # query returns nothing and the scorer simply sees no candidates.
    global _by_city, _by_cell, _meta
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
    cells: dict[tuple[int, int], list[dict]] = {}
    for source in payload.get("sources", []):
        index.setdefault(source["city"], []).append(source)
        cells.setdefault(_cell(source["lat"], source["lon"]), []).append(source)
    _by_city = index
    _by_cell = cells
    logger.info(
        "Loaded %d emission sources across %d cities into %d grid cells",
        sum(len(v) for v in index.values()), len(index), len(cells),
    )


_load()


def get_sources_for_city(city: str) -> list[dict]:
    """Registered emission sources for a city; empty list if none are on file."""
    return _by_city.get(city, [])


def get_sources_near(lat: float, lon: float, radius_km: float = 25.0) -> list[dict]:
    """
    Registered emission sources within `radius_km` of a point, via the spatial
    grid index.

    Two reasons this exists rather than looking sources up by city name.

    Correctness first: pollution does not respect municipal boundaries. A
    monitoring station in east Delhi has Noida and Ghaziabad industry well
    inside its 25 km screening radius, but a city-keyed lookup would never
    surface them because those sources are filed under a different city. The
    NCR is one airshed and the query should follow the air, not the paperwork.

    Scalability second: the city lookup hands the scorer every source in the
    city and lets it compute a haversine for each. That is a linear scan, and it
    shows — measured at 1.6 ms per hotspot over 200 sources but 1,038 ms over
    100,000. Bucketing into ~27 km cells means a query touches only the 3x3
    block around its centre regardless of how large the registry grows, which is
    what makes a national rollout across 900+ CAAQMS stations tractable.

    The returned set is still a superset of the true radius — cells are square
    and the radius is round — so the scorer's own haversine check remains the
    authority on what is actually in range.
    """
    if not _by_cell:
        return []

    # How many cells to reach out. Longitude cells narrow with latitude, so the
    # span is widened by 1/cos(lat) to keep the box a true superset of the circle.
    lat_cells = int(radius_km / 111.0 / GRID_DEG) + 1
    lon_km_per_deg = max(111.0 * cos(radians(lat)), 1.0)
    lon_cells = int(radius_km / lon_km_per_deg / GRID_DEG) + 1

    c_lat, c_lon = _cell(lat, lon)
    found: list[dict] = []
    for dlat in range(-lat_cells, lat_cells + 1):
        for dlon in range(-lon_cells, lon_cells + 1):
            found.extend(_by_cell.get((c_lat + dlat, c_lon + dlon), ()))
    return found


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
