"""
Integration tests for the enforcement chain in routes/intelligence.py.

These cover the wiring between the three stages — attribution, deterministic
geospatial correlation, and LLM narration — with the two LLM calls stubbed. The
point is to prove the correlation stage actually reaches the prompt and the
response, which unit tests of the scorer alone can't show.
"""
import json

import pytest
from fastapi.testclient import TestClient

import routes.intelligence as intel
from main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def fake_stations():
    """Two hotspots: Kolkata (in the seeded registry) and a city that isn't."""
    return [
        {"city": "Kolkata", "state": "West Bengal", "lat": 22.5726, "lon": 88.3639,
         "aqi": 340, "pm25": 180.0, "label": "Very Poor", "source": "waqi_live"},
        {"city": "Nowhere", "state": "Test", "lat": 20.0, "lon": 80.0,
         "aqi": 320, "pm25": 170.0, "label": "Very Poor", "source": "fallback"},
    ]


@pytest.fixture(autouse=True)
def stub_firms(monkeypatch):
    """
    Keep the satellite layer out of every test in this module.

    Applied automatically because it guards correctness, not convenience: once
    a real FIRMS_MAP_KEY is present in the environment, _enrich_city_with_candidates
    makes a live HTTPS call per hotspot. That made the suite depend on ambient
    config and on NASA's uptime, and it broke the concurrency timing test
    outright by adding seconds of real network latency inside the measured window.
    """
    async def no_fires(lat, lon, half_deg=0.25):
        return []
    monkeypatch.setattr(intel, "fetch_fires_near", no_fires)


@pytest.fixture
def stub_chain(monkeypatch, fake_stations):
    """Stub the network + LLM boundaries, leaving the correlation logic real."""
    # get_auto_enforcement imports get_cached_stations *inside* the function body,
    # so it resolves from services.cache at call time — patching the name on
    # routes.intelligence would be silently ignored.
    import services.cache
    monkeypatch.setattr(services.cache, "get_cached_stations", lambda: fake_stations)

    async def fake_weather(lat, lon):
        return {"wind_direction": 315, "wind_speed_kmh": 12.0, "humidity_pct": 60,
                "description": "haze", "temp_c": 28, "visibility_km": 3}
    monkeypatch.setattr(intel, "fetch_weather", fake_weather)

    captured = {}

    async def fake_llm_json(system, user, max_tokens=8000, **kwargs):
        # Discriminate on each system prompt's opening role line. Matching on
        # "source attribution" would misfire: ENFORCEMENT_SYSTEM describes the
        # Attribution Agent's output as part of explaining its own inputs.
        if system.lstrip().startswith("You are an air quality analyst"):
            return {"traffic": 20, "industrial": 45, "construction": 15,
                    "biomass_burning": 10, "other": 10, "dominant_source": "Industry",
                    "cpcb_baseline_used": True, "reasoning": "stub"}
        captured["enforcement_prompt"] = user
        return {
            "generated_at": "2026-07-21",
            "priorities": [
                {"rank": 1, "city": "Kolkata", "source_id": "STUB_ID",
                 "target_facility": "stub", "action": "Inspect stack",
                 "violation_type": "Industrial emissions", "inspector_count": 4,
                 "aqi_at_decision": 340, "rationale": "stub"},
            ],
        }

    monkeypatch.setattr(intel, "acall_llm_json", fake_llm_json)
    return captured


def test_enforcement_returns_correlated_hotspots(client, stub_chain):
    resp = client.get("/api/intel/enforcement/auto")
    assert resp.status_code == 200
    body = resp.json()

    assert "hotspots" in body
    kolkata = next(h for h in body["hotspots"] if h["city"] == "Kolkata")
    assert kolkata["candidate_sources"], "registry-backed city should have candidates"
    assert body["registry_backed"] is True


def test_candidates_carry_auditable_geospatial_evidence(client, stub_chain):
    body = client.get("/api/intel/enforcement/auto").json()
    top = next(h for h in body["hotspots"] if h["city"] == "Kolkata")["candidate_sources"][0]

    for field in ("lat", "lon", "distance_km", "upwind_alignment",
                  "evidence_score", "score_components", "osm_url", "dispatch_label"):
        assert field in top, f"missing {field}"
    assert top["distance_km"] <= 25
    # Wind is from 315 deg, so every surviving candidate must be upwind-ish.
    assert top["upwind_alignment"] >= -0.2


def test_correlation_evidence_reaches_the_llm_prompt(client, stub_chain):
    client.get("/api/intel/enforcement/auto")
    prompt = stub_chain["enforcement_prompt"]

    assert "Ranked registered emission sources" in prompt
    assert "km" in prompt and "evidence score" in prompt
    # The upwind finding must be stated in words, not left as a raw number.
    assert "UPWIND" in prompt or "upwind" in prompt


def test_city_without_registry_entries_is_flagged_not_fabricated(client, stub_chain):
    body = client.get("/api/intel/enforcement/auto").json()
    nowhere = next(h for h in body["hotspots"] if h["city"] == "Nowhere")
    assert nowhere["candidate_sources"] == []

    prompt = stub_chain["enforcement_prompt"]
    assert "No registered emission sources on file" in prompt
    assert "do NOT fabricate" in prompt


def test_response_time_is_measured(client, stub_chain):
    body = client.get("/api/intel/enforcement/auto").json()
    assert "response_time_seconds" in body
    assert isinstance(body["response_time_seconds"], (int, float))
    assert "signal_at" in body


def test_registry_provenance_is_surfaced(client, stub_chain):
    body = client.get("/api/intel/enforcement/auto").json()
    meta = body.get("registry_meta") or {}
    assert "OpenStreetMap" in meta.get("upstream", "")
    # The OSM-is-a-proxy caveat must travel with the data, not be hidden.
    assert "caveat" in meta


def test_bracketed_source_ids_are_reconciled(client, stub_chain):
    """
    The prompt lists candidates as "[way/123] Name" and the LLM copies the
    brackets into source_id. A live run returned "[way/202301146]", which fails
    exact-match lookup in the frontend so the evidence block silently vanishes.
    """
    from routes.intelligence import _normalise_source_ids

    candidate = {"id": "way/202301146", "name": "ARAI",
                 "dispatch_label": "Automotive Research Association of India"}
    cities = [{"candidate_sources": [candidate]}]
    result = {"priorities": [{"source_id": "[way/202301146]", "target_facility": "ARAI"}]}

    _normalise_source_ids(result, cities)
    assert result["priorities"][0]["source_id"] == "way/202301146"
    assert result["priorities"][0]["source_matched"] is True


def test_source_id_falls_back_to_name_match():
    """If the id is unusable, match on the facility name before giving up."""
    from routes.intelligence import _normalise_source_ids

    candidate = {"id": "way/999", "name": "Jaya Shri Textiles",
                 "dispatch_label": "Jaya Shri Textiles"}
    cities = [{"candidate_sources": [candidate]}]
    result = {"priorities": [{"source_id": "garbage",
                              "target_facility": "Jaya Shri Textiles"}]}

    _normalise_source_ids(result, cities)
    assert result["priorities"][0]["source_id"] == "way/999"
    assert result["priorities"][0]["source_matched"] is True


def test_unmatched_facility_is_flagged_not_silently_passed():
    """A facility the model invented must be marked, not presented as evidenced."""
    from routes.intelligence import _normalise_source_ids

    cities = [{"candidate_sources": [{"id": "way/1", "name": "Real Works",
                                      "dispatch_label": "Real Works"}]}]
    result = {"priorities": [{"source_id": "way/nonexistent",
                              "target_facility": "Imaginary Factory"}]}

    _normalise_source_ids(result, cities)
    assert result["priorities"][0]["source_matched"] is False


def test_hotspot_without_registry_still_reports_wind(client, stub_chain):
    """
    Returning early for uncovered cities left wind_direction null on exactly the
    hotspots that most need explaining — the ones with no candidates to show.
    """
    body = client.get("/api/intel/enforcement/auto").json()
    nowhere = next(h for h in body["hotspots"] if h["city"] == "Nowhere")
    assert nowhere["candidate_sources"] == []
    assert nowhere["in_registry"] is False
    assert nowhere["wind_direction"] == 315
    assert nowhere["satellite_fire_count"] == 0


def test_attribution_fanout_runs_concurrently(client, monkeypatch, fake_stations):
    """
    The attribution stage fans out one LLM call per hotspot via asyncio.gather.
    With the *sync* Azure client those coroutines ran strictly back to back and
    blocked the event loop throughout, so the fan-out bought nothing. With the
    async client they overlap.

    Five hotspots at 0.2s of simulated latency: concurrent is ~0.2s, serial is
    ~1.0s. The 0.6s bound distinguishes them without being flaky.
    """
    import asyncio as _asyncio
    import time

    import services.cache

    five = [
        {**fake_stations[0], "city": f"City{i}", "lat": 22.5 + i * 0.01, "lon": 88.3}
        for i in range(5)
    ]
    monkeypatch.setattr(services.cache, "get_cached_stations", lambda: five)
    monkeypatch.setattr(services.cache, "get_cached_attribution", lambda city: None)

    async def fake_weather(lat, lon):
        return {"wind_direction": 315, "wind_speed_kmh": 12.0, "humidity_pct": 60,
                "description": "haze", "temp_c": 28, "visibility_km": 3}
    monkeypatch.setattr(intel, "fetch_weather", fake_weather)

    async def slow_llm(system, user, max_tokens=8000, **kwargs):
        await _asyncio.sleep(0.2)
        if system.lstrip().startswith("You are an air quality analyst"):
            return {"traffic": 20, "industrial": 45, "construction": 15,
                    "biomass_burning": 10, "other": 10, "dominant_source": "Industry"}
        return {"generated_at": "2026-07-21", "priorities": []}
    monkeypatch.setattr(intel, "acall_llm_json", slow_llm)

    started = time.perf_counter()
    resp = client.get("/api/intel/enforcement/auto")
    elapsed = time.perf_counter() - started

    assert resp.status_code == 200
    # 5 attribution calls + 1 enforcement call. Serial would be >= 1.2s.
    assert elapsed < 0.6, f"attribution fan-out appears serial ({elapsed:.2f}s)"


def test_sources_endpoint_exposes_registry(client):
    resp = client.get("/api/intel/sources")
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is True
    assert body["stats"]["total_sources"] > 0

    city = client.get("/api/intel/sources", params={"city": "Kolkata"}).json()
    assert city["count"] > 0
    assert all(s["city"] == "Kolkata" for s in city["sources"])
