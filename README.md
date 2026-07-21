# 🌫️ AirWatch India

**Urban Air Quality Intelligence Platform** — real-time air quality across India with
AI-powered pollution analysis and a multilingual citizen health advisory chatbot.

> Built for the ET AI Hackathon 2026 · Problem Statement 5

---

## ✨ Features

- **🗺️ Live AQI Map** — Interactive map of India showing real-time air quality from live
  CPCB monitoring stations, colour-coded by severity.
- **📊 City Deep-Dive** — Click any city for full pollutant breakdown (PM2.5, PM10, NO₂, O₃, CO),
  live weather, and a 24-hour AQI trend.
- **🔬 AI Source Attribution** — Estimates what's polluting each city (traffic, industry,
  construction, biomass), anchored to published CPCB/ARAI source-apportionment studies and
  adjusted for live weather and time of day.
- **⚖️ Enforcement Intelligence & Prioritisation** *(primary focus)* — Correlates live
  pollution hotspots against a registry of **registered emission sources** (industries,
  construction sites, waste sites, diesel fleet depots) with real coordinates, ranks them
  by a deterministic evidence score — distance, **upwind alignment** against live wind
  direction, and category match to the attributed dominant source — and issues dispatchable,
  facility-level enforcement actions with supporting geospatial documentation.
- **💬 Multilingual Health Advisory** — A chatbot that answers citizen air-quality questions
  in **any Indian language** (English, हिंदी, தமிழ், ಕನ್ನಡ, …), auto-detecting the language
  and replying in the same script.

---

## 🏗️ Tech Stack

| Layer | Tech |
|-------|------|
| Frontend | React, Vite, Tailwind CSS v4, Leaflet.js |
| Backend | FastAPI (Python 3.11), httpx, tenacity |
| AI | Azure OpenAI `gpt-5-nano` (reasoning model) |
| Data | WAQI (primary), OpenAQ (backup), OpenWeatherMap |

**Resilience:** layered AQI fallback (WAQI → OpenAQ → static dataset) with per-city fallback
(one bad reading doesn't drop a city off the map), 10-minute station cache warmed at startup,
retry-with-backoff on all external API calls, and rate limiting on the LLM-backed endpoints.

**Concurrency:** all LLM calls go through the *async* Azure client (`services/llm.py`,
`acall_llm` / `acall_llm_json`). This matters for enforcement: the attribution stage fans out
one call per hotspot with `asyncio.gather`, and under the synchronous client those coroutines
ran strictly back to back *and* blocked the event loop for the whole round trip — so the
fan-out delivered neither parallelism nor concurrency, and froze every other request while it
worked. A timing test (`tests/test_enforcement_route.py`) asserts the fan-out actually overlaps.

## ⚖️ Enforcement Intelligence — how the correlation works

The problem statement asks for an agent that *"correlates pollution hotspot data with
registered emission sources … and generates prioritised, evidence-backed enforcement action
recommendations … with supporting geospatial documentation."* That correlation is done with
arithmetic, not by asking a language model to guess a plausible zone name.

**1. The registry.** `backend/data/emission_sources.json` holds registered emission sources
with real coordinates, seeded from OpenStreetMap via the Overpass API
(`backend/scripts/fetch_emission_sources.py`) across the four emitter types named in the
problem statement:

| Category | OSM proxy |
|---|---|
| Industry | `landuse=industrial`, `man_made=works` |
| Construction | `landuse=construction`, `building=construction` |
| Waste burning | `landuse=landfill`, `amenity=waste_transfer_station`, `waste_disposal` |
| Diesel fleet | `amenity=bus_station`, `landuse=depot`, `building=transportation` |

Seeded once and committed, so a demo never depends on Overpass being up — and so a free
shared community endpoint isn't hammered per request. These are honest proxies, not an
official register; open waste burning is unmapped by nature (it's illegal and unregistered),
so landfills and transfer stations stand in for it. That caveat ships inside the registry's
own `_meta` block and is surfaced through the API rather than hidden. A production
deployment would swap in CPCB consent-to-operate and state PCB registers.

**1b. Satellite fire detection.** Open waste and biomass burning is the one major emitter
that *cannot* appear in any ground register — it's illegal and unregistered by definition,
so OSM has no entry for it. NASA FIRMS (VIIRS, 375 m) fills that gap: active-fire detections
are fetched live per hotspot (`backend/services/firms.py`) and ranked in the same candidate
list as ground facilities, weighted by the satellite's own detection confidence so a marginal
thermal anomaly counts for less than a strong one. They're drawn dashed on the map and
labelled *"Satellite-detected fire 3.2 km NW of Delhi centre"*, and the LLM is instructed to
word these as *"verify and interdict active burning at these coordinates"* rather than as an
inspection of a registered premises — a thermal anomaly is a lead to confirm on the ground,
not a proven violation, and industrial flares and agricultural fires also register.

Needs a free `FIRMS_MAP_KEY` (see `.env.example`). Purely additive: without one, enforcement
falls back to the ground registry alone and still works.

**2. The correlation** (`backend/utils/enforcement_scoring.py` — deterministic, no LLM).
For each hotspot, every registered source in that city is scored on:

| Component | Weight | Why |
|---|---|---|
| Proximity | 0.35 | Linear falloff to zero at 25 km |
| **Upwind alignment** | 0.28 | A source *downwind* of the station cannot be causing the reading |
| Category match | 0.18 | Corroboration from the upstream Attribution Agent |
| Dispatchability | 0.12 | ~half of OSM sites are unnamed; a named facility can actually be served notice |
| Hotspot severity | 0.07 | Only discriminates when ranking across cities |

The upwind test is the strongest single discriminator and comes free: OpenWeatherMap's
`wind.deg` (the direction wind blows *from*) was already being fetched and discarded.
Sources more than ~102° off the wind axis are **excluded outright**, not ranked low — they
are eliminated on physical grounds, and padding a shortlist with them would overstate how
much evidence exists. Unnamed sites still have exact coordinates, so they get a navigable
positional label (*"Unregistered industry site 2.1 km NW of Kolkata centre"*) instead of a
useless one.

**3. The narration.** Only now is the LLM called — with a ranked shortlist of real
facilities it must choose from by exact ID, citing the distance and upwind evidence it was
handed. It no longer decides *where* to inspect; it writes the dispatch order.

Every recommendation carries its component scores, coordinates, and an OpenStreetMap link,
so a reviewer can audit exactly why a facility ranked where it did. `GET /api/intel/sources`
exposes the registry directly. The endpoint also reports `response_time_seconds` — measured
signal-to-dispatch latency, which the evaluation criteria ask to see demonstrated.

This is what the Enforcement Agent actually receives — real facilities, real geometry,
nothing for it to invent:

```
CITY: Kolkata - AQI 340 (Very Poor), PM2.5 180.0 μg/m³
  Attribution Agent dominant_source: Industry
  Live wind: from 315° at 12.0 km/h
  Ranked registered emission sources near this hotspot:
    - [way/101750901] Unregistered industry site 2.1 km NW of Kolkata centre |
      category: industry | 2.05 km NW of station | directly UPWIND (alignment 0.999) |
      evidence score 0.8288 | coords 22.586089,88.350254
```

**4. Geospatial documentation.** The Enforcement tab renders the correlation on a map:
the monitoring station, every candidate source coloured by category and sized by evidence
score, the wind axis, the 25 km screening radius, and evidence lines from each candidate
to the station. Selecting a priority focuses its facility. Each recommendation shows the
component-score breakdown that produced it, the exact coordinates, and a link to the
facility on OpenStreetMap — so the evidence is checkable in the UI, not just in the API.

---

**Data integrity — one AQI scale, end to end:** WAQI serves **US EPA** AQI *index* values
(both `aqi` and `iaqi.pm25.v`), not μg/m³ concentrations — a live Delhi feed returning
`iaqi.pm25: 25` means "EPA sub-index 25" (≈6 μg/m³), not "25 μg/m³". India's CPCB scale is
stricter, so the two are not interchangeable. Every WAQI reading is therefore inverted back
to a concentration (`epa_aqi_to_pm25`, `backend/utils/aqi_calculator.py`) and re-expressed
on the CPCB scale before use. This matters most for **enforcement**: the hotspot ranking
sorts live stations against static fallback ones, so mixing EPA and CPCB values silently
mis-ranked the cities feeding the Enforcement Agent. Mid-range readings were the worst
affected — an EPA index of 100 (truly "Satisfactory", 35.4 μg/m³) previously rendered as CPCB
234 "Poor". The original EPA value is retained as `aqi_epa_raw` so the conversion stays
auditable. Pollutants other than PM2.5 need their own EPA breakpoint tables to invert, so
they are surfaced honestly as `*_index` (EPA sub-index) rather than mislabelled as μg/m³.

**Beyond a pure LLM wrapper:** the 24h forecast is a hybrid — a deterministic statistical
baseline (`backend/utils/forecast_baseline.py`, no LLM call, backtested against real history
for a reportable MAE) that the LLM must explain or justify diverging from, not invent from
scratch. Source attribution carries a deterministic confidence score
(`backend/utils/attribution_confidence.py`) measuring how far the LLM actually strayed from
the cited CPCB baseline. Enforcement priorities are generated by a small multi-agent chain —
the Attribution Agent's findings for each top city feed directly into the Enforcement Agent's
reasoning, not two independent guesses.

---

## 🚀 Quick Start

### Prerequisites
- Python 3.11+, Node.js 18+
- API keys: [Azure OpenAI](https://azure.microsoft.com/products/ai-services/openai-service),
  [WAQI](https://aqicn.org/data-platform/token/),
  [OpenWeatherMap](https://openweathermap.org/api)

### Backend
```bash
cd backend
python -m venv venv
venv\Scripts\activate           # Windows  (source venv/bin/activate on macOS/Linux)
pip install -r requirements.txt

cp .env.example .env            # then fill in your API keys
uvicorn main:app --reload --port 8001
```

### Frontend
```bash
cd frontend
npm install
npm run dev                     # http://localhost:5173
```

### Verify
```bash
cd backend
python test_endpoints.py        # expects: 14/14 passed
```

---

## 📡 API Endpoints

| Method | Route | Description |
|--------|-------|-------------|
| `GET`  | `/api/aqi/live` | All live India stations (cached) |
| `GET`  | `/api/aqi/city/{name}?lat=&lon=` | City feed + weather + 24h history |
| `POST` | `/api/intel/attribution` | Pollution source breakdown |
| `POST` | `/api/intel/enforcement` | Enforcement priorities for given cities |
| `GET`  | `/api/intel/enforcement/auto` | Registry-correlated enforcement priorities for top-5 live hotspots |
| `GET`  | `/api/intel/sources` | Emission source registry — coverage + provenance (`?city=Delhi` for one city) |
| `POST` | `/api/intel/forecast` | 24h AQI forecast |
| `POST` | `/api/intel/advisory` | Multilingual citizen health advisory |

---

## 📁 Project Structure

```
airwatch/
├── backend/     FastAPI — routes, services (waqi/openaq/openweather/llm/cache), prompts, tests
└── frontend/    React — MapView, CityPanel, EnforcementSidebar, AdvisoryGenerator
```

See **[HANDOFF.md](HANDOFF.md)** for architecture details, key technical decisions, and known
gotchas (reasoning-model token budgets, the IPv4 proxy requirement, etc.).

---

## 🔑 Configuration

All secrets live in `backend/.env` (gitignored — never committed). Copy `backend/.env.example`
and fill in your keys. Note: `gpt-5-nano` requires API version `2025-04-01-preview` and
`reasoning_effort="low"` — see HANDOFF.md for why.

---

## 📝 License

Built for a hackathon — no license specified. Contact the author before reuse.
