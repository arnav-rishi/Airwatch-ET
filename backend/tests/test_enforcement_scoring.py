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
        "proximity", "atmospheric_transport", "category_match",
        "identifiability", "severity",
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


# ─── Sensitive receptors ──────────────────────────────────────────────────────
# OSM names a bus terminal or car park at a hospital after that hospital, so it
# enters the registry as a diesel_fleet/construction source and can rank first
# on pure geometry. A live run did exactly that and produced a recommendation to
# send inspectors to Park Circus - Chittaranjan Hospital.

@pytest.mark.parametrize("name", [
    "Park Circus - Chittaranjan Hospital",
    "Mayo Hospital",
    "Medical College Kalamassery Bus Terminal",
    "KIMS Hospital (u/c)",
    "Sapthagiri NPS University (u/c)",
    "Central Medical Depot",
    "St. Xavier's School",
    "Kendriya Vidyalaya",
    # Places of worship — a live run put "Kamakhya Mandir", a major Hindu
    # temple, at rank 1 because the bus station outside it carries its name.
    "Kamakhya Mandir",
    "Gujarat State Road Transport Corporation | Bus Station | Gita Mandir",
    "Jama Masjid",
    "Kundrathur Temple MTC Terminus",
    "Belur Math Bus stop",
])
def test_sensitive_receptors_are_excluded_entirely(name):
    """These are receptors to protect, not premises to raid — never candidates."""
    hotspot = {"lat": 0.0, "lon": 0.0, "aqi": 400}
    # Placed as close and as perfectly upwind as possible, so only the exclusion
    # itself can keep them out of the results.
    src = _source(name, 0.0, -0.005, category="diesel_fleet")

    assert score_sources(hotspot, [src], wind_direction_deg=270) == []


@pytest.mark.parametrize("name", [
    "Jaya Shri Textiles",
    "Bharat Petroleum Depot",
    "Schooner Engineering Works",     # contains "school" as a substring
    "Collegiate Cement Ltd",          # contains "college" as a substring
    # "Vihar" is a residential locality suffix across north India far more often
    # than a Buddhist monastery. An earlier version of the filter matched it and
    # removed these real bus depots — exactly the diesel_fleet targets wanted.
    "Vasant Vihar Depot",
    "Sukdev Vihar Depot",
    "Mayur Vihar Phase - 3, Bus Stand",
    "Salt Lake Bus Depot",
])
def test_ordinary_targets_are_not_over_filtered(name):
    """The filter must not swallow legitimate enforcement targets."""
    hotspot = {"lat": 0.0, "lon": 0.0, "aqi": 400}
    ranked = score_sources(hotspot, [_source(name, 0.0, -0.02)], wind_direction_deg=270)
    assert ranked, f"{name} was wrongly excluded"


def test_sensitive_receptor_excluded_even_when_it_would_rank_first():
    """The exclusion must beat geometry, not merely tie-break against it."""
    hotspot = {"lat": 0.0, "lon": 0.0, "aqi": 400}
    hospital = _source("City Hospital", 0.0, -0.005)     # very close, dead upwind
    factory = _source("Distant Works", 0.0, -0.15)       # far, weakly aligned

    ranked = score_sources(hotspot, [hospital, factory], wind_direction_deg=270)
    assert [r["name"] for r in ranked] == ["Distant Works"]


# ─── Kerbside stops vs real fleet facilities ──────────────────────────────────
# OSM's amenity=bus_station spans a state transport depot and a numbered kerbside
# halt alike. Stops sit beside the monitoring station so they win on proximity,
# and a live run put "42A BUS STAND" at rank 3 — there is nothing to inspect at a
# pole with a timetable on it.

@pytest.mark.parametrize("osm_id,name", [
    ("node/1", "14 No Bus Stop"),
    ("node/2", "45 BUS STAND"),
    ("node/3", "42A BUS STAND"),
    ("node/4", "Parnasree Bus Stand"),
    ("node/5", "Unnamed diesel fleet site"),
])
def test_kerbside_stops_are_excluded(osm_id, name):
    hotspot = {"lat": 0.0, "lon": 0.0, "aqi": 400}
    src = _source(name, 0.0, -0.005, category="diesel_fleet")
    src["id"] = osm_id
    assert score_sources(hotspot, [src], wind_direction_deg=270) == []


@pytest.mark.parametrize("osm_id,name", [
    # Polygons have area — something is actually built there.
    ("way/10", "Salt Lake Bus Depot"),
    ("way/11", "Unnamed diesel fleet site"),
    # Nodes that name themselves a real facility are kept despite being points.
    ("node/12", "CSTC Bus Terminal"),
    ("node/13", "Serampore Court Bus Terminus"),
    ("node/14", "Howrah Bus Station"),
    ("node/15", "Rahara bazar bus depot"),
])
def test_real_fleet_facilities_are_kept(osm_id, name):
    hotspot = {"lat": 0.0, "lon": 0.0, "aqi": 400}
    src = _source(name, 0.0, -0.02, category="diesel_fleet")
    src["id"] = osm_id
    assert score_sources(hotspot, [src], wind_direction_deg=270), f"{name} wrongly excluded"


def test_stop_filter_only_applies_to_diesel_fleet():
    """An unnamed industrial or construction node must not be caught by it."""
    hotspot = {"lat": 0.0, "lon": 0.0, "aqi": 400}
    for category in ("industry", "construction", "waste_burning"):
        src = _source("Unnamed site", 0.0, -0.02, category=category)
        src["id"] = "node/99"
        assert score_sources(hotspot, [src], wind_direction_deg=270), category


def test_real_depot_outranks_nothing_when_only_stops_are_nearby():
    """With stops filtered out, a distant real depot should still surface."""
    hotspot = {"lat": 0.0, "lon": 0.0, "aqi": 400}
    stop = _source("42A BUS STAND", 0.0, -0.002, category="diesel_fleet")
    stop["id"] = "node/1"
    depot = _source("Salt Lake Bus Depot", 0.0, -0.10, category="diesel_fleet")
    depot["id"] = "way/2"

    ranked = score_sources(hotspot, [stop, depot], wind_direction_deg=270)
    assert [r["name"] for r in ranked] == ["Salt Lake Bus Depot"]


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
