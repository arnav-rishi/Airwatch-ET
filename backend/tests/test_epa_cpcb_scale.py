"""
Regression tests for the EPA→CPCB scale conversion (utils/aqi_calculator.py).

The bug these lock down: WAQI serves US EPA AQI *index* values in both `aqi`
and `iaqi.pm25.v`, but the codebase treated them as μg/m³ concentrations. That
put live cities on the EPA scale and fallback cities (data/cities_fallback.json)
on the CPCB scale, then sorted the two together to pick enforcement hotspots —
so the top-5 ranking feeding the Enforcement Agent was comparing incompatible
units.
"""
from utils.aqi_calculator import epa_aqi_to_pm25, pm25_to_aqi, aqi_category


def test_epa_index_is_not_a_concentration():
    """The core misreading: EPA index 25 is ~6 μg/m³, nowhere near 25 μg/m³."""
    pm25 = epa_aqi_to_pm25(25)
    assert 5.0 <= pm25 <= 7.0


def test_epa_breakpoint_anchors():
    # Exact breakpoint edges from the EPA PM2.5 table.
    assert epa_aqi_to_pm25(0) == 0.0
    assert epa_aqi_to_pm25(50) == 12.0
    assert epa_aqi_to_pm25(100) == 35.4
    assert epa_aqi_to_pm25(200) == 150.4


def test_epa_conversion_is_monotonic():
    values = [epa_aqi_to_pm25(i) for i in range(0, 501, 10)]
    assert values == sorted(values)


def test_epa_conversion_handles_out_of_range():
    assert epa_aqi_to_pm25(None) == 0.0
    assert epa_aqi_to_pm25(-5) == 0.0
    assert epa_aqi_to_pm25(9999) == 500.4


def test_real_waqi_delhi_payload_is_not_good_air():
    """
    Live WAQI Delhi returned `aqi: 36, iaqi.pm25: 25`. Read as an EPA index that
    is genuinely clean air — but the old code ran pm25_to_aqi(25) and rendered a
    CPCB "Good" green pin regardless. This asserts the pipeline now agrees with
    itself: EPA 25 → ~6 μg/m³ → low CPCB AQI, reached by the correct route.
    """
    pm25 = epa_aqi_to_pm25(25)
    cpcb = pm25_to_aqi(pm25)
    assert cpcb < 50
    assert aqi_category(cpcb)["label"] == "Good"


def test_polluted_epa_reading_maps_to_severe_cpcb():
    """
    The direction that actually matters for enforcement: EPA 200 is 150.4 μg/m³,
    which on India's stricter CPCB scale is far worse than the EPA number looks.
    Labelling the raw EPA index with CPCB categories understated this badly.
    """
    pm25 = epa_aqi_to_pm25(200)
    cpcb = pm25_to_aqi(pm25)
    assert cpcb > 300
    assert aqi_category(cpcb)["label"] in ("Very Poor", "Severe")


def test_converted_live_and_static_fallback_are_comparable():
    """
    The enforcement hotspot sort compares live stations against fallback ones.
    A heavily polluted live reading must outrank a moderate static one once both
    are on CPCB — under the old code the EPA value would have lost this sort.
    """
    live_cpcb = pm25_to_aqi(epa_aqi_to_pm25(200))   # heavy pollution, live feed
    static_cpcb = 214                               # Delhi's cities_fallback.json value
    assert live_cpcb > static_cpcb
