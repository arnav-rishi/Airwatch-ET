"""
Screening-level Gaussian plume dispersion model.

Why this replaces a cosine: the enforcement scorer previously judged whether a
source could reach a monitoring station with cos(bearing - wind_direction) — a
crude proxy that says a source is "upwind" or not, but cannot distinguish a
small facility 500 m upwind from a large one 20 km upwind, and treats crosswind
offset and wind speed as if they were irrelevant. Atmospheric dispersion is a
solved problem with a standard closed-form solution, and using it costs about
as much arithmetic.

The steady-state Gaussian plume equation, for a ground-level receptor and a
ground-level release over flat terrain:

    C(x, y) = Q / (pi * u * sigma_y * sigma_z) * exp(-y^2 / (2 * sigma_y^2))

    x        downwind distance from source to receptor (m)
    y        crosswind offset (m)
    u        wind speed at release height (m/s)
    sigma_y  horizontal dispersion coefficient (m), grows with x
    sigma_z  vertical dispersion coefficient (m), grows with x
    Q        emission rate (g/s)

sigma_y and sigma_z come from the Briggs urban dispersion curves, selected by
Pasquill-Gifford stability class, which is itself derived from wind speed and
day/night insolation. Urban curves are the right family here: every receptor in
this system is a city monitoring station, and urban surface roughness and the
heat-island effect produce markedly more mixing than the rural curves assume.

WHAT THIS DOES NOT CLAIM
------------------------
Q is unknown. The registry records that a facility exists, not what it emits —
there is no public per-facility emission inventory for these sources — so every
source is modelled at unit emission rate. That makes the output a *relative
susceptibility*: "given equal emissions, how much more would this source affect
this station than that one". It is a targeting aid, not a concentration estimate,
and it must not be read as one.

Beyond that, this is a screening model, not a regulatory one. It assumes flat
terrain, steady-state uniform wind, no plume rise (ground-level release, so no
stack height or buoyancy), no chemical decay or deposition, and no building
downwash. AERMOD or CALPUFF would model all of those and need stack parameters,
hourly meteorology and terrain grids that this system does not have. What it
does buy over the cosine it replaces is real physics: crosswind spread that
widens with distance, faster dilution in unstable air, and the inverse wind-speed
relationship — the reasons a distant source can matter more than a near one.
"""
from math import cos, exp, pi, radians, sin

# Briggs urban dispersion coefficients, keyed by Pasquill-Gifford stability
# class. Each entry returns (sigma_y, sigma_z) in metres for a downwind
# distance x in metres. Classes A-B and E-F share curves in the Briggs
# formulation, which is why they are grouped.
def _sigma_urban(stability: str, x: float) -> tuple[float, float]:
    """Briggs urban sigma_y, sigma_z (metres) at downwind distance x (metres)."""
    x = max(x, 1.0)
    if stability in ("A", "B"):
        sy = 0.32 * x * (1 + 0.0004 * x) ** -0.5
        sz = 0.24 * x * (1 + 0.001 * x) ** 0.5
    elif stability == "C":
        sy = 0.22 * x * (1 + 0.0004 * x) ** -0.5
        sz = 0.20 * x
    elif stability == "D":
        sy = 0.16 * x * (1 + 0.0004 * x) ** -0.5
        sz = 0.14 * x * (1 + 0.0003 * x) ** -0.5
    else:  # E, F
        sy = 0.11 * x * (1 + 0.0004 * x) ** -0.5
        sz = 0.08 * x * (1 + 0.0015 * x) ** -0.5
    return max(sy, 0.1), max(sz, 0.1)


def stability_class(wind_speed_ms: float, is_daytime: bool, cloudy: bool) -> str:
    """
    Pasquill-Gifford stability class from the meteorology actually available.

    The full Pasquill table keys on incoming solar radiation, which needs solar
    elevation and cloud cover. OpenWeatherMap gives wind speed, local time and a
    text description, so insolation is approximated as day/night plus a cloud
    flag parsed from that description.

    A-B  unstable   light wind, strong daytime heating -> rapid mixing
    C-D  neutral    moderate/strong wind, or overcast
    E-F  stable     light wind at night -> pollutants stay concentrated

    Stability drives everything downstream: in stable night air a source 10 km
    away still reaches the station, while in unstable afternoon air the same
    plume has already dispersed.
    """
    u = max(wind_speed_ms, 0.0)
    if is_daytime:
        strong = not cloudy
        if u < 2:
            return "A" if strong else "B"
        if u < 3:
            return "B"
        if u < 5:
            return "B" if strong else "C"
        if u < 6:
            return "C"
        return "D"
    # Night. Clear skies radiate heat away and produce the strongest inversions.
    if u < 2:
        return "F" if not cloudy else "E"
    if u < 3:
        return "E" if not cloudy else "D"
    if u < 5:
        return "E" if not cloudy else "D"
    return "D"


def downwind_crosswind(
    distance_m: float, bearing_source_to_receptor: float, wind_direction_deg: float
) -> tuple[float, float]:
    """
    Resolve a source-receptor displacement into downwind (x) and crosswind (y)
    components, in metres.

    wind_direction_deg follows the meteorological convention used throughout
    this codebase and by OpenWeatherMap: the direction the wind blows *from*.
    The plume therefore travels toward (wind_direction + 180).

    A negative x means the receptor lies upwind of the source, so the plume is
    blowing away from the station and that source cannot be contributing.
    """
    travel_dir = (wind_direction_deg + 180.0) % 360.0
    theta = radians(bearing_source_to_receptor - travel_dir)
    return distance_m * cos(theta), distance_m * sin(theta)


def plume_concentration(
    distance_m: float,
    bearing_source_to_receptor: float,
    wind_direction_deg: float,
    wind_speed_ms: float,
    stability: str = "D",
) -> float:
    """
    Relative ground-level concentration at the receptor from a unit-emission
    source, in arbitrary units (Q = 1 g/s).

    Returns 0.0 when the receptor is upwind of the source — the plume is
    travelling away from it, so there is no contribution to model.
    """
    x, y = downwind_crosswind(distance_m, bearing_source_to_receptor, wind_direction_deg)
    if x <= 0:
        return 0.0

    # Below ~1 m/s the Gaussian plume model breaks down (the 1/u term diverges
    # and the steady-state assumption fails in calm air). Clamp rather than
    # return a spuriously enormous concentration.
    u = max(wind_speed_ms, 1.0)

    sigma_y, sigma_z = _sigma_urban(stability, x)
    return exp(-(y ** 2) / (2 * sigma_y ** 2)) / (pi * u * sigma_y * sigma_z)


# Reference case used to put concentrations on a comparable 0-1 scale: a source
# 2 km directly downwind under neutral stability and a 3 m/s wind. Anything
# closer or better aligned exceeds it and is clamped to 1.0. A fixed reference
# is used rather than normalising by the best candidate in each city, so scores
# mean the same thing across cities and a lone weak candidate cannot be
# flattered into looking like a strong one.
_REFERENCE_CONCENTRATION = plume_concentration(
    distance_m=2000.0,
    bearing_source_to_receptor=0.0,
    wind_direction_deg=180.0,  # wind from the south, so travel is due north
    wind_speed_ms=3.0,
    stability="D",
)


def dispersion_factor(
    distance_km: float,
    bearing_source_to_receptor: float,
    wind_direction_deg: float,
    wind_speed_kmh: float,
    is_daytime: bool = True,
    cloudy: bool = False,
) -> dict:
    """
    Score a source's plausible contribution to a receptor on [0, 1], with the
    intermediate physics returned alongside so a recommendation can be audited.

    Returns:
      factor          normalised relative contribution, 0-1
      stability       Pasquill-Gifford class used
      downwind_km     distance along the wind axis (negative = receptor upwind)
      crosswind_km    perpendicular offset from the plume centreline
      sigma_y_m       horizontal plume spread at that distance
      concentration   raw unit-emission concentration, before normalisation
    """
    wind_speed_ms = max(wind_speed_kmh, 0.0) / 3.6
    stability = stability_class(wind_speed_ms, is_daytime, cloudy)
    distance_m = max(distance_km, 0.0) * 1000.0

    x, y = downwind_crosswind(distance_m, bearing_source_to_receptor, wind_direction_deg)
    concentration = plume_concentration(
        distance_m, bearing_source_to_receptor, wind_direction_deg,
        wind_speed_ms, stability,
    )
    sigma_y, _ = _sigma_urban(stability, max(x, 1.0))

    factor = 0.0
    if _REFERENCE_CONCENTRATION > 0:
        factor = min(1.0, concentration / _REFERENCE_CONCENTRATION)

    return {
        "factor": round(factor, 4),
        "stability": stability,
        "downwind_km": round(x / 1000.0, 2),
        "crosswind_km": round(y / 1000.0, 2),
        "sigma_y_m": round(sigma_y, 1),
        "concentration": concentration,
    }


_STABILITY_DESCRIPTION = {
    "A": "very unstable (strong daytime heating, light wind) — rapid dispersion",
    "B": "unstable (daytime heating) — good dispersion",
    "C": "slightly unstable — moderate dispersion",
    "D": "neutral (windy or overcast) — moderate dispersion",
    "E": "stable (night, light wind) — poor dispersion, pollutants persist",
    "F": "very stable (clear calm night) — strong inversion, pollutants trapped",
}


def describe_stability(stability: str) -> str:
    return _STABILITY_DESCRIPTION.get(stability, "unknown stability")


def is_cloudy(weather_description: str | None) -> bool:
    """Parse OpenWeatherMap's text description into the cloud flag Pasquill needs."""
    if not weather_description:
        return False
    d = weather_description.lower()
    return any(w in d for w in ("cloud", "overcast", "rain", "storm", "drizzle", "shower", "mist", "fog", "haze"))
