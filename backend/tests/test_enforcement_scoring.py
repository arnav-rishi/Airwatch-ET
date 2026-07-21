"""
Tests for the deterministic hotspot-to-source correlation
(utils/enforcement_scoring.py).

The geometry here is easy to get backwards — OpenWeatherMap reports the
direction wind blows *from*, not the direction it travels — and getting it
backwards would invert every enforcement recommendation while still looking
plausible. These tests pin the convention down explicitly.
"""
import pytest

from utils.enforcement_scoring import (
    MAX_RELEVANT_KM,
    bearing_deg,
    compass_point,
    haversine_km,
    score_sources,
    upwind_alignment,
)

DELHI_LAT, DELHI_LON = 28.6139, 77.2090


def _source(name, lat, lon, category="industry"):
    return {
        "id": f"node/{name}", "city": "Delhi", "category": category,
        "name": name, "lat": lat, "lon": lon, "osm_url": "",
    }


# ─── Geometry primitives ──────────────────────────────────────────────────────

def test_haversine_known_distance():
    # Delhi -> Mumbai is ~1150 km.
    d = haversine_km(DELHI_LAT, DELHI_LON, 19.0760, 72.8777)
    assert 1100 < d < 1200


def test_haversine_zero_for_same_point():
    assert haversine_km(DELHI_LAT, DELHI_LON, DELHI_LAT, DELHI_LON) == pytest.approx(0, abs=1e-6)


def test_bearing_cardinal_directions():
    assert bearing_deg(0, 0, 1, 0) == pytest.approx(0, abs=1)      # north
    assert bearing_deg(0, 0, 0, 1) == pytest.approx(90, abs=1)     # east
    assert bearing_deg(0, 0, -1, 0) == pytest.approx(180, abs=1)   # south
    assert bearing_deg(0, 0, 0, -1) == pytest.approx(270, abs=1)   # west


# ─── Upwind convention ────────────────────────────────────────────────────────

def test_source_directly_upwind_scores_one():
    """
    Wind from the west (270 deg). A source to the WEST of the hotspot is upwind
    and its emissions blow onto the hotspot -> alignment 1.0.
    """
    alignment = upwind_alignment(0, 0, 0, -1, wind_direction_deg=270)
    assert alignment == pytest.approx(1.0, abs=0.01)


def test_source_directly_downwind_scores_minus_one():
    """Same westerly wind, but the source is EAST — downwind, cannot contribute."""
    alignment = upwind_alignment(0, 0, 0, 1, wind_direction_deg=270)
    assert alignment == pytest.approx(-1.0, abs=0.01)


def test_crosswind_source_scores_zero():
    alignment = upwind_alignment(0, 0, 1, 0, wind_direction_deg=270)
    assert alignment == pytest.approx(0.0, abs=0.01)


# ─── Ranking behaviour ────────────────────────────────────────────────────────

def test_downwind_sources_are_excluded_not_just_ranked_low():
    """A physically-downwind source must not appear at all."""
    hotspot = {"lat": 0.0, "lon": 0.0, "aqi": 300}
    upwind = _source("upwind-plant", 0.0, -0.05)
    downwind = _source("downwind-plant", 0.0, 0.05)

    ranked = score_sources(hotspot, [upwind, downwind], wind_direction_deg=270)
    names = [r["name"] for r in ranked]
    assert "upwind-plant" in names
    assert "downwind-plant" not in names


def test_closer_source_outranks_distant_one_all_else_equal():
    hotspot = {"lat": 0.0, "lon": 0.0, "aqi": 300}
    near = _source("near", 0.0, -0.02)
    far = _source("far", 0.0, -0.15)

    ranked = score_sources(hotspot, [near, far], wind_direction_deg=270)
    assert ranked[0]["name"] == "near"
    assert ranked[0]["distance_km"] < ranked[1]["distance_km"]


def test_sources_beyond_max_radius_are_dropped():
    hotspot = {"lat": 0.0, "lon": 0.0, "aqi": 300}
    # ~1 degree of longitude at the equator is ~111 km, well past the cutoff.
    ranked = score_sources(hotspot, [_source("distant", 0.0, -1.0)], wind_direction_deg=270)
    assert ranked == []


def test_category_match_breaks_ties_toward_attributed_source():
    """
    Two equidistant, equally-upwind sources of different categories: the one
    matching the Attribution Agent's dominant_source must win.
    """
    hotspot = {"lat": 0.0, "lon": 0.0, "aqi": 300}
    industry = _source("plant", 0.0, -0.05, category="industry")
    construction = _source("site", 0.0, -0.05, category="construction")

    ranked = score_sources(
        hotspot, [industry, construction],
        wind_direction_deg=270, dominant_source="Industry",
    )
    assert ranked[0]["name"] == "plant"


def test_unknown_dominant_source_does_not_penalise_anything():
    """An unmappable attribution should stay neutral, not zero every candidate."""
    hotspot = {"lat": 0.0, "lon": 0.0, "aqi": 300}
    ranked = score_sources(
        hotspot, [_source("plant", 0.0, -0.05)],
        wind_direction_deg=270, dominant_source="Secondary aerosol",
    )
    assert ranked[0]["score_components"]["category_match"] == 0.5


def test_missing_wind_data_still_ranks_by_geometry():
    """No wind reading must degrade gracefully, not crash or drop everything."""
    hotspot = {"lat": 0.0, "lon": 0.0, "aqi": 300}
    ranked = score_sources(hotspot, [_source("a", 0.0, -0.02), _source("b", 0.0, -0.15)])
    assert [r["name"] for r in ranked] == ["a", "b"]
    assert ranked[0]["upwind_alignment"] is None


def test_result_carries_auditable_components():
    hotspot = {"lat": 0.0, "lon": 0.0, "aqi": 300}
    ranked = score_sources(hotspot, [_source("plant", 0.0, -0.05)], wind_direction_deg=270)
    top = ranked[0]
    assert set(top["score_components"]) == {
        "proximity", "upwind", "category_match", "identifiability", "severity",
    }
    assert 0 <= top["evidence_score"] <= 1
    assert top["distance_km"] > 0
    assert top["osm_url"] is not None


# ─── Dispatchability ──────────────────────────────────────────────────────────

def test_named_facility_outranks_unnamed_when_otherwise_equal():
    """An inspector can't be sent to an unnamed polygon — ties go to the named site."""
    hotspot = {"lat": 0.0, "lon": 0.0, "aqi": 300}
    named = _source("Shershah Cold Storage", 0.0, -0.05)
    unnamed = _source("Unnamed industry site", 0.0, -0.05)

    ranked = score_sources(hotspot, [named, unnamed], wind_direction_deg=270)
    assert ranked[0]["name"] == "Shershah Cold Storage"
    assert ranked[0]["identifiable"] is True
    assert ranked[1]["identifiable"] is False


def test_compass_point_cardinals():
    assert compass_point(0) == "N"
    assert compass_point(90) == "E"
    assert compass_point(180) == "S"
    assert compass_point(270) == "W"
    assert compass_point(315) == "NW"
    assert compass_point(360) == "N"


def test_unnamed_site_gets_navigable_positional_label():
    """
    "Unnamed industry site" is useless on a dispatch sheet. An unnamed polygon
    still has exact coordinates, so it must be described positionally instead.
    """
    hotspot = {"lat": 0.0, "lon": 0.0, "aqi": 300}
    unnamed = _source("Unnamed industry site", 0.05, -0.05)
    unnamed["city"] = "Kolkata"

    ranked = score_sources(hotspot, [unnamed], wind_direction_deg=315)
    label = ranked[0]["dispatch_label"]
    assert "Unnamed" not in label
    assert "km" in label and "Kolkata" in label
    assert ranked[0]["compass_from_hotspot"] == "NW"


def test_named_site_keeps_its_real_name_as_dispatch_label():
    hotspot = {"lat": 0.0, "lon": 0.0, "aqi": 300}
    ranked = score_sources(
        hotspot, [_source("Jaya Shri Textiles", 0.0, -0.05)], wind_direction_deg=270
    )
    assert ranked[0]["dispatch_label"] == "Jaya Shri Textiles"


def test_identifiability_does_not_override_physics():
    """
    A much closer, better-aligned unnamed site must still beat a distant named
    one — dispatchability breaks ties, it doesn't overrule the geometry.
    """
    hotspot = {"lat": 0.0, "lon": 0.0, "aqi": 300}
    close_unnamed = _source("Unnamed industry site", 0.0, -0.01)
    far_named = _source("Distant Works Ltd", 0.0, -0.20)

    ranked = score_sources(hotspot, [close_unnamed, far_named], wind_direction_deg=270)
    assert ranked[0]["name"] == "Unnamed industry site"


def test_limit_is_respected():
    hotspot = {"lat": 0.0, "lon": 0.0, "aqi": 300}
    sources = [_source(f"s{i}", 0.0, -0.01 * (i + 1)) for i in range(20)]
    assert len(score_sources(hotspot, sources, wind_direction_deg=270, limit=3)) == 3


def test_empty_registry_returns_empty():
    assert score_sources({"lat": 0.0, "lon": 0.0, "aqi": 300}, []) == []
