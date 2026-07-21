"""
Tests for the spatial grid index (services/source_registry.py).

The index exists for two reasons and both are load-bearing: it keeps lookup cost
flat as the registry grows, and it makes queries follow the airshed rather than
municipal boundaries. A bug here fails silently — the scorer would simply never
see sources it should have considered, and the output would still look fine.
"""
import pytest

from services.source_registry import (
    GRID_DEG,
    get_sources_for_city,
    get_sources_near,
    registry_stats,
)
from utils.enforcement_scoring import haversine_km

DELHI = (28.6139, 77.2090)


def test_spatial_query_returns_sources():
    assert len(get_sources_near(*DELHI, radius_km=25)) > 0


def test_returned_set_covers_every_source_truly_in_radius():
    """
    The critical property. Cells are square and the radius is round, so the
    index returns a superset — but it must never MISS a source inside the
    radius, or the scorer silently ignores a real candidate.
    """
    lat, lon = DELHI
    radius = 25.0
    returned = {s["id"] for s in get_sources_near(lat, lon, radius)}

    # Brute-force ground truth over the entire registry.
    from services.source_registry import _by_city
    truth = {
        s["id"]
        for sources in _by_city.values()
        for s in sources
        if haversine_km(lat, lon, s["lat"], s["lon"]) <= radius
    }
    assert truth <= returned, f"index missed {len(truth - returned)} in-radius sources"


def test_query_crosses_city_boundaries():
    """
    Pollution doesn't respect municipal boundaries. A Delhi station has Noida and
    Ghaziabad sources well inside 25 km, and a city-keyed lookup would never
    surface them — the NCR is one airshed.
    """
    near = get_sources_near(*DELHI, radius_km=25)
    cities = {s["city"] for s in near}
    assert len(cities) > 1, "spatial query should span more than the one city"
    assert cities - {"Delhi"}, "expected neighbouring-city sources in range"


def test_spatial_query_finds_more_than_city_lookup():
    """The correctness win: strictly more candidates than the city-name lookup."""
    lat, lon = DELHI
    city_only = [
        s for s in get_sources_for_city("Delhi")
        if haversine_km(lat, lon, s["lat"], s["lon"]) <= 25
    ]
    spatial = [
        s for s in get_sources_near(lat, lon, 25)
        if haversine_km(lat, lon, s["lat"], s["lon"]) <= 25
    ]
    assert len(spatial) > len(city_only)


def test_small_radius_returns_fewer_than_large():
    small = get_sources_near(*DELHI, radius_km=5)
    large = get_sources_near(*DELHI, radius_km=25)
    assert len(small) <= len(large)


def test_empty_region_returns_empty_not_error():
    """Mid-ocean — no cells populated."""
    assert get_sources_near(0.0, 0.0, radius_km=25) == []


def test_longitude_cells_widen_near_the_poles():
    """
    Longitude degrees shrink with latitude, so a fixed-degree grid must reach
    further in cell-count at high latitude to still cover the radius. India sits
    at 8-37 deg N where this is a modest correction, but getting it backwards
    would truncate the search box in the north.
    """
    from services.source_registry import _by_cell
    if not _by_cell:
        pytest.skip("registry not loaded")
    # Srinagar (34 N) must still return its own sources at a 25 km radius.
    assert len(get_sources_near(34.0837, 74.7973, radius_km=25)) > 0


def test_grid_cell_is_larger_than_screening_radius():
    """
    0.25 deg is ~27.75 km, comfortably over the 25 km screening radius, which is
    what keeps a query to the 3x3 block around its centre.
    """
    assert GRID_DEG * 111.0 > 25.0


def test_registry_stats_still_report_full_coverage():
    stats = registry_stats()
    assert stats["total_sources"] > 5000
    assert stats["cities_covered"] == 43
