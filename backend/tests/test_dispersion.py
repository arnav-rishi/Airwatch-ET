"""
Tests for the Gaussian plume dispersion model (utils/dispersion.py).

These pin down the physics the enforcement scorer now relies on. The failure
mode they guard against is subtle: a sign error or a swapped sigma would still
produce plausible-looking numbers and a ranked list that reads fine, while
systematically pointing inspectors at the wrong facilities.
"""
import pytest

from utils.dispersion import (
    describe_stability,
    dispersion_factor,
    downwind_crosswind,
    is_cloudy,
    plume_concentration,
    stability_class,
)


# ─── Geometry ─────────────────────────────────────────────────────────────────

def test_source_directly_upwind_is_all_downwind_distance():
    """
    Wind from the west (270). A source due west of the station is upwind, so the
    full separation is downwind distance and there is no crosswind offset.
    Bearing source->receptor is 90 (the receptor lies east of the source).
    """
    x, y = downwind_crosswind(1000.0, bearing_source_to_receptor=90, wind_direction_deg=270)
    assert x == pytest.approx(1000.0, abs=1.0)
    assert y == pytest.approx(0.0, abs=1.0)


def test_source_downwind_gives_negative_x():
    """A source east of the station under a westerly: plume blows away from it."""
    x, _ = downwind_crosswind(1000.0, bearing_source_to_receptor=270, wind_direction_deg=270)
    assert x < 0


def test_crosswind_source_is_all_offset():
    """A source due north under a westerly is perpendicular to the plume axis."""
    x, y = downwind_crosswind(1000.0, bearing_source_to_receptor=180, wind_direction_deg=270)
    assert x == pytest.approx(0.0, abs=1.0)
    assert abs(y) == pytest.approx(1000.0, abs=1.0)


# ─── Stability classification ─────────────────────────────────────────────────

def test_light_wind_sunny_day_is_unstable():
    assert stability_class(1.0, is_daytime=True, cloudy=False) == "A"


def test_strong_wind_is_neutral_regardless_of_time():
    assert stability_class(8.0, is_daytime=True, cloudy=False) == "D"
    assert stability_class(8.0, is_daytime=False, cloudy=False) == "D"


def test_calm_clear_night_is_most_stable():
    """The classic winter-inversion case that traps pollutants over Indian cities."""
    assert stability_class(1.0, is_daytime=False, cloudy=False) == "F"


def test_cloud_cover_moderates_night_stability():
    """Clouds trap outgoing radiation, so a cloudy night is less stable than a clear one."""
    clear = stability_class(1.0, is_daytime=False, cloudy=False)
    cloudy_night = stability_class(1.0, is_daytime=False, cloudy=True)
    assert clear == "F" and cloudy_night == "E"


@pytest.mark.parametrize("desc,expected", [
    ("clear sky", False), ("haze", True), ("overcast clouds", True),
    ("light rain", True), ("mist", True), ("smoke", False), (None, False),
])
def test_cloud_parsing_from_weather_text(desc, expected):
    assert is_cloudy(desc) is expected


# ─── Plume behaviour ──────────────────────────────────────────────────────────

def test_downwind_source_contributes_nothing():
    """The single most important property: the plume blows away from the station."""
    c = plume_concentration(1000.0, bearing_source_to_receptor=270,
                            wind_direction_deg=270, wind_speed_ms=3.0)
    assert c == 0.0


def test_concentration_falls_with_distance():
    near = plume_concentration(500.0, 90, 270, 3.0)
    far = plume_concentration(5000.0, 90, 270, 3.0)
    assert near > far > 0


def test_concentration_falls_with_crosswind_offset():
    """Off the plume centreline, concentration drops on a Gaussian curve."""
    on_axis = plume_concentration(2000.0, 90, 270, 3.0)
    off_axis = plume_concentration(2000.0, 110, 270, 3.0)
    assert on_axis > off_axis > 0


def test_higher_wind_dilutes():
    """The 1/u term — the same physics the forecast baseline already assumes."""
    calm = plume_concentration(2000.0, 90, 270, 2.0)
    windy = plume_concentration(2000.0, 90, 270, 10.0)
    assert calm > windy


def test_stable_air_concentrates_more_than_unstable():
    """
    A stable night inversion keeps a plume tight; unstable daytime air mixes it
    away. This is why the same factory matters more at 6am than at 2pm.
    """
    stable = plume_concentration(3000.0, 90, 270, 2.0, stability="F")
    unstable = plume_concentration(3000.0, 90, 270, 2.0, stability="A")
    assert stable > unstable


def test_calm_wind_does_not_blow_up():
    """Below ~1 m/s the 1/u term diverges; it must be clamped, not infinite."""
    c = plume_concentration(1000.0, 90, 270, wind_speed_ms=0.0)
    assert c > 0 and c < float("inf")


# ─── Normalised factor used by the scorer ─────────────────────────────────────

def test_factor_is_bounded():
    for distance in (0.1, 1.0, 5.0, 25.0):
        f = dispersion_factor(distance, 90, 270, 12.0)
        assert 0.0 <= f["factor"] <= 1.0


def test_factor_zero_when_downwind():
    f = dispersion_factor(2.0, 270, 270, 12.0)
    assert f["factor"] == 0.0
    assert f["downwind_km"] < 0


def test_factor_reports_auditable_physics():
    f = dispersion_factor(3.0, 90, 270, 10.0, is_daytime=True, cloudy=False)
    assert f["stability"] in "ABCDEF"
    assert f["downwind_km"] == pytest.approx(3.0, abs=0.1)
    assert f["crosswind_km"] == pytest.approx(0.0, abs=0.1)
    assert f["sigma_y_m"] > 0
    assert describe_stability(f["stability"])


def test_plume_widens_with_distance():
    """sigma_y grows downwind — a distant source needs less precise alignment."""
    near = dispersion_factor(1.0, 90, 270, 10.0)
    far = dispersion_factor(10.0, 90, 270, 10.0)
    assert far["sigma_y_m"] > near["sigma_y_m"]


def test_distant_aligned_source_can_beat_near_offset_one():
    """
    The whole reason for replacing the cosine. A source 2 km dead on the plume
    axis can matter more than one 1 km away but well off it — geometry the old
    alignment score handled only crudely, because it ignored how far the plume
    had spread by the time it arrived.
    """
    aligned_far = dispersion_factor(2.0, 90, 270, 8.0)
    offset_near = dispersion_factor(1.0, 150, 270, 8.0)
    assert aligned_far["factor"] > offset_near["factor"]
