"""
Tests for NASA FIRMS satellite fire detection (services/firms.py) and its
integration into hotspot correlation.

The CSV fixture below matches the real VIIRS_SNPP_NRT response format.
"""
import pytest

from services.firms import _confidence_to_score, _parse_csv, firms_enabled
from utils.enforcement_scoring import score_sources

# Real VIIRS column layout; coordinates are just north-west of Delhi.
VIIRS_CSV = """latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight
28.7041,77.1025,330.5,0.42,0.38,2026-07-21,0812,N,VIIRS,h,2.0NRT,295.1,12.4,D
28.7500,77.0500,310.2,0.45,0.40,2026-07-21,0812,N,VIIRS,n,2.0NRT,288.7,4.1,D
28.6800,77.1500,301.0,0.50,0.44,2026-07-21,0812,N,VIIRS,l,2.0NRT,285.2,1.2,D
"""


# ─── Parsing ──────────────────────────────────────────────────────────────────

def test_parses_viirs_csv_into_source_records():
    fires = _parse_csv(VIIRS_CSV)
    assert len(fires) == 3

    top = fires[0]
    assert top["lat"] == 28.7041
    assert top["lon"] == 77.1025
    assert top["category"] == "waste_burning"
    assert top["source_type"] == "satellite"
    assert top["frp_mw"] == 12.4
    assert top["detection_confidence"] == 1.0  # 'h'
    assert "2026-07-21 08:12" in top["observed_at"]


def test_viirs_letter_confidence_grades():
    assert _confidence_to_score("h") == 1.0
    assert _confidence_to_score("n") == 0.65
    assert _confidence_to_score("l") == 0.3


def test_modis_numeric_confidence_is_also_supported():
    """MODIS reports 0-100 instead of letters; switching FIRMS_SOURCE must not break scoring."""
    assert _confidence_to_score("100") == 1.0
    assert _confidence_to_score("50") == 0.5
    assert _confidence_to_score("0") == 0.0


def test_unparseable_confidence_falls_back_to_neutral():
    assert _confidence_to_score("") == 0.5
    assert _confidence_to_score("garbage") == 0.5


def test_malformed_rows_are_skipped_not_fatal():
    bad = VIIRS_CSV + "not_a_number,also_bad,,,,2026-07-21,0812,N,VIIRS,h,2.0NRT,,,\n"
    assert len(_parse_csv(bad)) == 3


def test_empty_csv_returns_empty():
    assert _parse_csv("latitude,longitude,acq_date,acq_time,confidence,frp\n") == []


# ─── Integration with scoring ─────────────────────────────────────────────────

def test_satellite_fire_ranks_alongside_ground_sources():
    """A fire must compete in the same ranking as OSM facilities, not a separate list."""
    hotspot = {"city": "Delhi", "lat": 28.6139, "lon": 77.2090, "aqi": 380}
    fires = [dict(f, city="Delhi") for f in _parse_csv(VIIRS_CSV)]
    ground = {
        "id": "way/1", "city": "Delhi", "category": "industry",
        "name": "Some Works", "lat": 28.62, "lon": 77.19, "osm_url": "",
    }

    ranked = score_sources(hotspot, fires + [ground], wind_direction_deg=315)
    assert any(r.get("source_type") == "satellite" for r in ranked)


def test_low_confidence_detection_scores_below_high_confidence_one():
    """
    Two fires at effectively the same place, differing only in detection
    confidence — a marginal thermal anomaly is a weaker lead and must rank lower.
    """
    hotspot = {"lat": 0.0, "lon": 0.0, "aqi": 300}
    base = {"category": "waste_burning", "source_type": "satellite",
            "city": "Test", "lat": 0.0, "lon": -0.05, "osm_url": None}
    high = {**base, "id": "firms/high", "name": "fire-h", "detection_confidence": 1.0}
    low = {**base, "id": "firms/low", "name": "fire-l", "detection_confidence": 0.3}

    ranked = score_sources(hotspot, [low, high], wind_direction_deg=270)
    assert ranked[0]["id"] == "firms/high"
    assert ranked[0]["evidence_score"] > ranked[1]["evidence_score"]


def test_satellite_detection_gets_observational_dispatch_label():
    """A fire has no register entry — its label must say it was located by observation."""
    hotspot = {"lat": 0.0, "lon": 0.0, "aqi": 300}
    fire = {"id": "firms/x", "category": "waste_burning", "source_type": "satellite",
            "city": "Delhi", "name": "Active fire detection", "lat": 0.05, "lon": -0.05,
            "detection_confidence": 1.0, "osm_url": None}

    ranked = score_sources(hotspot, [fire], wind_direction_deg=315)
    label = ranked[0]["dispatch_label"]
    assert "Satellite-detected fire" in label
    assert "NW" in label


def test_downwind_fire_is_excluded_like_any_other_source():
    """Satellite provenance doesn't exempt a detection from the upwind constraint."""
    hotspot = {"lat": 0.0, "lon": 0.0, "aqi": 300}
    downwind = {"id": "firms/d", "category": "waste_burning", "source_type": "satellite",
                "city": "Delhi", "name": "fire", "lat": 0.0, "lon": 0.05,
                "detection_confidence": 1.0, "osm_url": None}

    assert score_sources(hotspot, [downwind], wind_direction_deg=270) == []


# ─── Degradation ──────────────────────────────────────────────────────────────

def test_no_map_key_returns_empty_not_error(monkeypatch):
    """
    FIRMS is additive evidence — without a key enforcement must still work.

    Driven with asyncio.run rather than @pytest.mark.asyncio: pytest-asyncio
    isn't a dependency, and the marker without it silently *skips* the test
    instead of failing, which is worse than not having it.
    """
    import asyncio

    from services import firms
    monkeypatch.delenv("FIRMS_MAP_KEY", raising=False)
    assert asyncio.run(firms.fetch_fires_near(28.6, 77.2)) == []
    assert firms_enabled() is False


def test_non_csv_error_body_is_rejected(monkeypatch):
    """
    FIRMS answers a bad key with HTTP 200 and a plain-text body, so a failure
    looks like a successful empty result unless the payload is inspected.
    """
    import asyncio

    import httpx

    from services import firms

    monkeypatch.setenv("FIRMS_MAP_KEY", "bogus")
    firms._cache.clear()

    class FakeResponse:
        text = "Invalid MAP_KEY."
        def raise_for_status(self): pass

    class FakeClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url): return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: FakeClient())
    assert asyncio.run(firms.fetch_fires_near(28.6, 77.2)) == []
