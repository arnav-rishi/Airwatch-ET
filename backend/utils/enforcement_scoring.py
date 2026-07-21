"""
Deterministic correlation of pollution hotspots against the registered emission
source registry (data/emission_sources.json).

Why this exists: the Enforcement Agent previously asked an LLM to name a
"target_zone" from a city name and an AQI number. Nothing in the system held a
list of actual emitters, so there was nothing to correlate against and no way
to check the answer — the model picked a plausible-sounding area type from the
menu in its own prompt.

This module does the correlation with arithmetic instead. For a hotspot it
scores every registered source in that city on four independent, individually
inspectable components, ranks them, and hands the top candidates to the LLM to
write the dispatch narrative. The LLM stops inventing *where* to inspect and is
left doing what it's good at: explaining a ranked, evidence-backed shortlist.

This mirrors the pattern already used by utils/forecast_baseline.py (statistical
forecast the LLM must reconcile with) and utils/attribution_confidence.py
(divergence score over LLM output) — a deterministic core the LLM narrates
rather than replaces.

Scope, stated honestly: proximity + upwind geometry is a screening heuristic,
not a dispersion model. It answers "which registered sources are physically
capable of contributing to this hotspot right now, ranked by plausibility",
which is what an inspector allocating a shift actually needs. It does not
estimate emission mass or prove causation, and every returned candidate carries
its component scores so a reviewer can see exactly why it ranked where it did.
"""
from math import atan2, cos, degrees, radians, sin, sqrt

EARTH_RADIUS_KM = 6371.0

# Beyond this, a source is treated as unable to contribute meaningfully to a
# city-centre hotspot reading. Roughly the radius within which a ground-level
# urban source still measurably affects a monitoring station on a typical day.
MAX_RELEVANT_KM = 25.0

# Component weights. Proximity and upwind geometry dominate because they are
# physical constraints; category match is corroborating evidence from the
# upstream Attribution Agent. Severity is deliberately small — it's constant
# across every source within a hotspot, so it only discriminates when ranking
# candidates from different cities against each other.
#
# Identifiability is weighted last and lightly, but it is not cosmetic: roughly
# half of OSM-derived sites are unnamed polygons, and an inspector cannot be
# dispatched to — or serve a notice on — an unnamed polygon. A named facility is
# materially more actionable, so it should win a close call. The weight is kept
# small enough that a markedly closer or better-aligned unnamed site still
# outranks a named one; dispatchability breaks ties, it doesn't overrule physics.
_W_PROXIMITY = 0.35
_W_UPWIND = 0.28
_W_CATEGORY = 0.18
_W_IDENTIFIABILITY = 0.12
_W_SEVERITY = 0.07

# The Attribution Agent's dominant_source vocabulary (from the CPCB baseline
# table in prompts.py) mapped onto the registry's category vocabulary. Both
# sides are free text from different sources, so this mapping is explicit
# rather than inferred.
_SOURCE_TO_CATEGORY = {
    "industry": "industry",
    "industrial": "industry",
    "vehicles": "diesel_fleet",
    "transport": "diesel_fleet",
    "traffic": "diesel_fleet",
    "construction": "construction",
    "biomass burning": "waste_burning",
    "biomass_burning": "waste_burning",
    "waste burning": "waste_burning",
    "road dust": "construction",
}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km."""
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = (
        sin(dlat / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * atan2(sqrt(a), sqrt(1 - a))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial compass bearing from point 1 to point 2, in degrees from north."""
    dlon = radians(lon2 - lon1)
    y = sin(dlon) * cos(radians(lat2))
    x = cos(radians(lat1)) * sin(radians(lat2)) - sin(radians(lat1)) * cos(
        radians(lat2)
    ) * cos(dlon)
    return (degrees(atan2(y, x)) + 360) % 360


def upwind_alignment(
    hotspot_lat: float, hotspot_lon: float,
    source_lat: float, source_lon: float,
    wind_direction_deg: float,
) -> float:
    """
    How well a source sits upwind of the hotspot, in [-1, 1].

    OpenWeatherMap's `wind.deg` follows the meteorological convention: it is the
    direction the wind blows *from*. So a source can only be carried onto the
    hotspot if the source lies in roughly that same direction as seen from the
    hotspot — i.e. bearing(hotspot -> source) should be close to wind.deg.

    Returns 1.0 for a source directly upwind, 0.0 for crosswind, and -1.0 for
    one directly downwind. A downwind source is physically incapable of causing
    the reading, which is the single most useful discriminator here and the
    reason the wind direction is worth fetching at all.
    """
    b = bearing_deg(hotspot_lat, hotspot_lon, source_lat, source_lon)
    return cos(radians(b - wind_direction_deg))


def _proximity_score(distance_km: float) -> float:
    """Linear falloff to zero at MAX_RELEVANT_KM — simple and legible."""
    if distance_km >= MAX_RELEVANT_KM:
        return 0.0
    return 1.0 - (distance_km / MAX_RELEVANT_KM)


def _severity_score(aqi: float) -> float:
    """Normalise CPCB AQI onto [0, 1], saturating at the top of the scale (500)."""
    return max(0.0, min(1.0, aqi / 500.0))


_COMPASS_16 = [
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
]


def compass_point(bearing: float) -> str:
    """Bearing in degrees to a 16-point compass abbreviation."""
    return _COMPASS_16[int((bearing % 360) / 22.5 + 0.5) % 16]


def dispatch_label(source: dict, distance_km: float, bearing: float) -> str:
    """
    A label an inspector can actually navigate to.

    Roughly half of OSM-derived sites are unnamed polygons, and "Unnamed
    industry site" is useless on a dispatch sheet. But an unnamed site still has
    exact coordinates, so it can be described positionally — "Industrial site
    2.0 km NW of Kolkata city centre" — which, with the coordinates and OSM link
    that travel alongside it, is genuinely actionable. Named sites keep their
    real name.
    """
    # A satellite detection has no register entry by nature — it's located
    # purely by observation, so describe it that way.
    if source.get("source_type") == "satellite":
        return (
            f"Satellite-detected fire {distance_km:.1f} km "
            f"{compass_point(bearing)} of {source.get('city', 'city')} centre"
        )
    if is_identifiable(source):
        return source["name"]
    kind = source.get("category", "emission").replace("_", " ")
    return (
        f"Unregistered {kind} site {distance_km:.1f} km "
        f"{compass_point(bearing)} of {source.get('city', 'city')} centre"
    )


def is_identifiable(source: dict) -> bool:
    """
    Whether the source carries a real name (vs. an unnamed OSM polygon).

    scripts/fetch_emission_sources.py synthesises "Unnamed <category> site" when
    OSM has neither a name nor an operator tag.
    """
    name = (source.get("name") or "").strip()
    return bool(name) and not name.startswith("Unnamed ")


def _identifiability_score(source: dict) -> float:
    return 1.0 if is_identifiable(source) else 0.0


def _category_score(category: str, dominant_source: str | None) -> float:
    """
    1.0 when the source category matches what the Attribution Agent blamed,
    0.5 when there's no attribution to corroborate against (absence of evidence
    shouldn't penalise a source), 0.0 on an explicit mismatch.
    """
    if not dominant_source:
        return 0.5
    expected = _SOURCE_TO_CATEGORY.get(dominant_source.strip().lower())
    if expected is None:
        return 0.5
    return 1.0 if expected == category else 0.0


def score_sources(
    hotspot: dict,
    sources: list[dict],
    wind_direction_deg: float | None = None,
    dominant_source: str | None = None,
    limit: int = 5,
) -> list[dict]:
    """
    Rank registered sources by their plausibility as contributors to a hotspot.

    `hotspot` needs lat/lon/aqi. `sources` is the registry slice for that city.
    Returns up to `limit` candidates, each carrying its distance, bearing,
    upwind alignment and the four component scores that produced its total — so
    a recommendation can be audited rather than taken on faith.

    Sources beyond MAX_RELEVANT_KM, and those clearly downwind when a wind
    direction is known, are dropped rather than ranked low: they are excluded on
    physical grounds, and padding a shortlist with them would misrepresent how
    much real evidence exists.
    """
    hs_lat, hs_lon = hotspot["lat"], hotspot["lon"]
    severity = _severity_score(hotspot.get("aqi", 0))

    scored = []
    for src in sources:
        distance = haversine_km(hs_lat, hs_lon, src["lat"], src["lon"])
        if distance > MAX_RELEVANT_KM:
            continue

        if wind_direction_deg is None:
            alignment = None
            # No wind data: score the geometry we do have and say so, rather
            # than inventing a neutral wind and hiding the gap.
            upwind_component = 0.5
        else:
            alignment = upwind_alignment(
                hs_lat, hs_lon, src["lat"], src["lon"], wind_direction_deg
            )
            # Physically downwind - it cannot be feeding this reading.
            if alignment < -0.2:
                continue
            upwind_component = (alignment + 1) / 2  # [-1,1] -> [0,1]

        bearing = bearing_deg(hs_lat, hs_lon, src["lat"], src["lon"])
        proximity = _proximity_score(distance)
        category = _category_score(src["category"], dominant_source)
        identifiability = _identifiability_score(src)

        total = (
            _W_PROXIMITY * proximity
            + _W_UPWIND * upwind_component
            + _W_CATEGORY * category
            + _W_IDENTIFIABILITY * identifiability
            + _W_SEVERITY * severity
        )

        # Satellite fire detections carry their own observation confidence.
        # A low-confidence thermal anomaly is a weaker lead than a high-confidence
        # one, and unlike a mapped facility it may not be a real fire at all — so
        # the score is scaled by it rather than treating every detection alike.
        if src.get("source_type") == "satellite":
            total *= 0.5 + 0.5 * src.get("detection_confidence", 0.5)

        scored.append({
            **src,
            "dispatch_label": dispatch_label(src, distance, bearing),
            "distance_km": round(distance, 2),
            "bearing_from_hotspot_deg": round(bearing, 1),
            "compass_from_hotspot": compass_point(bearing),
            "upwind_alignment": round(alignment, 3) if alignment is not None else None,
            "identifiable": bool(identifiability),
            "evidence_score": round(total, 4),
            "score_components": {
                "proximity": round(proximity, 3),
                "upwind": round(upwind_component, 3),
                "category_match": round(category, 3),
                "identifiability": round(identifiability, 3),
                "severity": round(severity, 3),
            },
        })

    scored.sort(key=lambda s: s["evidence_score"], reverse=True)
    return scored[:limit]
