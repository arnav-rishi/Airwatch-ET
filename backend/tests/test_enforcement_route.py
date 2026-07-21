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

    def fake_llm_json(system, user, max_tokens=8000, **kwargs):
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

    monkeypatch.setattr(intel, "call_llm_json", fake_llm_json)
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


def test_sources_endpoint_exposes_registry(client):
    resp = client.get("/api/intel/sources")
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is True
    assert body["stats"]["total_sources"] > 0

    city = client.get("/api/intel/sources", params={"city": "Kolkata"}).json()
    assert city["count"] > 0
    assert all(s["city"] == "Kolkata" for s in city["sources"])
