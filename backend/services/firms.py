"""
NASA FIRMS active-fire detections — satellite-observed thermal anomalies.

Why this belongs in the enforcement path: the problem statement names "waste
burning locations" as an emitter category to correlate against, and separately
lists satellite remote sensing (MODIS/VIIRS) as a suggested technology. Open
waste and biomass burning is the one major emitter that is *unmappable* in a
ground register — it is illegal and by definition unregistered, so OSM has no
entry for it. Satellite thermal detection is the only practical way to locate
it, which makes FIRMS the natural complement to the OSM-derived registry in
services/source_registry.py.

Unlike that registry, this data is fetched live: a fire detected six hours ago
is evidence, a fire from last month is not. Detections are cached briefly
because the satellites only pass a few times a day, so re-querying per request
would add latency for data that cannot have changed.

Requires a free MAP_KEY from https://firms.modaps.eosdis.nasa.gov/api/area/.
Without one, every lookup returns empty and enforcement falls back to the OSM
registry alone — the feature is additive, never load-bearing.

Honest scope: FIRMS detects thermal anomalies, not "illegal waste burning"
specifically. Industrial flares, brick kilns and agricultural residue fires all
register. Near a city boundary, open burning is the most common explanation,
but a detection is a lead for an inspector to verify, not a proven violation —
which is exactly how it is labelled downstream.
"""
import csv
import io
import logging
import os
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)

FIRMS_BASE = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"

# VIIRS at 375 m resolves small fires far better than MODIS at 1 km, which
# matters for urban waste burning — these are dumpster- and plot-scale fires,
# not wildfires.
DEFAULT_SOURCE = "VIIRS_SNPP_NRT"

# FIRMS accepts 1-10 days, but measured against the full India bbox the larger
# windows silently return an EMPTY body rather than an error — 1 day yielded 15
# detections, 3 days yielded 138, and 7 and 10 days both returned nothing at
# all. That is a server-side transaction limit, not an absence of fires, so
# anything above 3 is actively worse than useless here. 3 days also keeps
# detections recent enough to bear on today's reading.
DEFAULT_DAY_RANGE = 3

# Satellites revisit only a few times daily, so a short cache costs no freshness.
CACHE_TTL_SECONDS = 1800

_cache: dict[str, tuple[datetime, list[dict]]] = {}

# VIIRS reports confidence as low/nominal/high rather than a percentage.
_CONFIDENCE_SCORE = {"l": 0.3, "n": 0.65, "h": 1.0}


def _confidence_to_score(raw: str) -> float:
    """
    Normalise FIRMS confidence to [0, 1].

    VIIRS uses letter grades; MODIS uses a 0-100 integer. Support both so the
    source can be switched via FIRMS_SOURCE without breaking scoring.
    """
    raw = (raw or "").strip().lower()
    if raw in _CONFIDENCE_SCORE:
        return _CONFIDENCE_SCORE[raw]
    try:
        return max(0.0, min(1.0, float(raw) / 100.0))
    except (TypeError, ValueError):
        return 0.5


def _parse_csv(text: str) -> list[dict]:
    """
    Parse a FIRMS CSV response into fire-source records shaped like registry
    entries, so utils/enforcement_scoring.py can rank them alongside OSM sources
    without special-casing.
    """
    detections = []
    for row in csv.DictReader(io.StringIO(text)):
        try:
            lat = float(row["latitude"])
            lon = float(row["longitude"])
        except (KeyError, TypeError, ValueError):
            continue

        acq_date = (row.get("acq_date") or "").strip()
        acq_time = (row.get("acq_time") or "").strip().zfill(4)
        observed = f"{acq_date} {acq_time[:2]}:{acq_time[2:]}" if acq_date else ""

        # Fire Radiative Power in megawatts — a proxy for how large the burn is.
        try:
            frp = float(row.get("frp") or 0)
        except (TypeError, ValueError):
            frp = 0.0

        confidence = _confidence_to_score(row.get("confidence", ""))
        detections.append({
            "id": f"firms/{lat:.5f},{lon:.5f}@{acq_date}{acq_time}",
            "category": "waste_burning",
            "name": f"Active fire detection ({observed} UTC)" if observed
                    else "Active fire detection",
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "source_type": "satellite",
            "satellite": (row.get("satellite") or "").strip(),
            "observed_at": observed,
            "frp_mw": round(frp, 1),
            "detection_confidence": round(confidence, 2),
            "osm_url": None,
        })
    return detections


async def fetch_fires_near(
    lat: float, lon: float, half_deg: float = 0.25
) -> list[dict]:
    """
    Active fire detections in a bounding box around a point, newest data first.

    Returns [] when no MAP_KEY is configured or the request fails — enforcement
    treats satellite fires as additional evidence layered on top of the ground
    registry, so their absence degrades the recommendation rather than breaking it.
    """
    map_key = os.getenv("FIRMS_MAP_KEY")
    if not map_key:
        return []

    west, south = lon - half_deg, lat - half_deg
    east, north = lon + half_deg, lat + half_deg
    bbox = f"{west:.4f},{south:.4f},{east:.4f},{north:.4f}"

    cached = _cache.get(bbox)
    if cached and (datetime.utcnow() - cached[0]).total_seconds() < CACHE_TTL_SECONDS:
        return cached[1]

    source = os.getenv("FIRMS_SOURCE", DEFAULT_SOURCE)
    day_range = os.getenv("FIRMS_DAY_RANGE", str(DEFAULT_DAY_RANGE))
    url = f"{FIRMS_BASE}/{map_key}/{source}/{bbox}/{day_range}"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            text = resp.text
    except Exception as exc:
        logger.warning("FIRMS fetch failed for bbox %s: %s", bbox, exc)
        return []

    # FIRMS signals auth/quota problems with a 200 and a plain-text body rather
    # than an error status, so a bad key looks like a successful empty response
    # unless the payload is checked.
    if "Invalid" in text[:200] or "," not in text[:200]:
        logger.warning("FIRMS returned a non-CSV body (check FIRMS_MAP_KEY): %s", text[:120])
        return []

    detections = _parse_csv(text)
    _cache[bbox] = (datetime.utcnow(), detections)
    return detections


def firms_enabled() -> bool:
    return bool(os.getenv("FIRMS_MAP_KEY"))
