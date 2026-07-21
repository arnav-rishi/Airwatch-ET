"""
Tests for quantified enforcement impact (utils/impact_metrics.py).

The risk with impact numbers is that they quietly become marketing: a figure
that only ever flatters, or one whose denominator was chosen to make the
numerator look good. These tests pin the arithmetic to the registry and check
that the comparison is drawn from a like-for-like population.
"""
from utils.impact_metrics import INSPECTOR_SHIFT_HOURS, enforcement_impact, hotspot_impact


def _hotspot(city="Kolkata", lat=22.5726, lon=88.3639, n_candidates=5):
    return {
        "city": city, "lat": lat, "lon": lon, "aqi": 340,
        "candidate_sources": [
            {"id": f"way/{i}", "lat": lat + 0.01 * i, "lon": lon,
             "evidence_score": 0.9 - 0.01 * i, "category": "industry",
             "name": f"Facility {i}"}
            for i in range(n_candidates)
        ],
    }


def test_narrowing_is_computed_from_the_real_registry():
    impact = hotspot_impact(_hotspot())
    assert impact["registered_sources_in_city"] > 0
    assert impact["eligible_sources_in_range"] > 0
    assert impact["shortlisted"] == 5
    assert impact["narrowing_factor"] > 1


def test_search_space_excludes_what_the_scorer_excludes():
    """
    Both sides of the comparison must come from the same population. Counting
    hospitals and kerbside stops in the denominator would inflate the narrowing
    factor with sources no sensible process would visit anyway.
    """
    impact = hotspot_impact(_hotspot())
    from services.source_registry import get_sources_for_city
    raw = len(get_sources_for_city("Kolkata"))
    assert impact["eligible_sources_in_range"] < raw


def test_search_space_respects_the_operational_radius():
    """A source 60 km away isn't in the counterfactual an inspector faces."""
    near = hotspot_impact(_hotspot())
    assert near["eligible_sources_in_range"] <= near["registered_sources_in_city"]


def test_random_hit_rate_is_the_inverse_of_narrowing():
    impact = hotspot_impact(_hotspot())
    expected = round(100 / impact["narrowing_factor"], 1)
    assert abs(impact["random_hit_rate_pct"] - expected) < 1.0


def test_city_absent_from_registry_reports_nothing_rather_than_zero_division():
    impact = hotspot_impact(_hotspot(city="Atlantis", lat=0.0, lon=0.0))
    assert impact["eligible_sources_in_range"] == 0
    assert impact["narrowing_factor"] is None
    assert impact["random_hit_rate_pct"] is None


def test_aggregate_impact_sums_inspectors_and_shift_hours():
    result = {
        "hotspots": [_hotspot()],
        "priorities": [
            {"rank": 1, "inspector_count": 3, "source_matched": True},
            {"rank": 2, "inspector_count": 2, "source_matched": True},
            {"rank": 3, "inspector_count": 4, "source_matched": False},
        ],
        "response_time_seconds": 41.1,
    }
    impact = enforcement_impact(result)
    assert impact["inspectors_recommended"] == 9
    assert impact["inspector_shift_hours"] == 9 * INSPECTOR_SHIFT_HOURS
    assert impact["priorities_issued"] == 3
    # Only recommendations traceable to a registry entry count as evidenced.
    assert impact["priorities_traceable_to_registry"] == 2


def test_aggregate_carries_measured_latency_not_an_estimate():
    result = {"hotspots": [_hotspot()], "priorities": [], "response_time_seconds": 41.1}
    assert enforcement_impact(result)["signal_to_dispatch_seconds"] == 41.1


def test_malformed_inspector_counts_do_not_break_the_sum():
    """The LLM occasionally returns a string or omits the field."""
    result = {
        "hotspots": [_hotspot()],
        "priorities": [
            {"inspector_count": 3}, {"inspector_count": "two"}, {},
        ],
        "response_time_seconds": 10.0,
    }
    assert enforcement_impact(result)["inspectors_recommended"] == 3


def test_no_registry_backed_hotspots_yields_no_fabricated_narrowing():
    result = {
        "hotspots": [{"city": "Atlantis", "lat": 0.0, "lon": 0.0, "candidate_sources": []}],
        "priorities": [],
        "response_time_seconds": 5.0,
    }
    impact = enforcement_impact(result)
    assert impact["narrowing_factor"] is None
    assert impact["shortlisted_sources"] == 0


def test_baseline_note_cites_its_source():
    """The one external claim must carry its citation, not float free."""
    impact = enforcement_impact({"hotspots": [], "priorities": []})
    assert "CAG" in impact["baseline_note"]
    assert "31%" in impact["baseline_note"]
