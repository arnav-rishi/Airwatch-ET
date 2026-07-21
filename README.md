# 🌫️ AirWatch India

**Urban Air Quality Intelligence Platform** — real-time air quality across India, with an
enforcement intelligence agent that tells pollution-control authorities *which specific
facility to inspect today, and why*.

> Built for the ET AI Hackathon 2026 · Problem Statement 5
> **Primary focus: Enforcement Intelligence & Prioritisation**

---

## ✨ Features

- **⚖️ Enforcement Intelligence & Prioritisation** *(primary focus)* — Correlates live
  pollution hotspots against a registry of 5,154 **registered emission sources** (industries,
  construction sites, waste sites, diesel fleet depots) with real coordinates, ranks them by a
  deterministic evidence score — distance, **upwind alignment** against live wind direction,
  and category match to the attributed dominant source — and issues dispatchable,
  facility-level enforcement actions with supporting geospatial documentation.
  **[How it works ↓](#️-enforcement-intelligence--how-the-correlation-works)**
- **🗺️ Live AQI Map** — Interactive map of India showing real-time air quality from CPCB
  monitoring stations (via WAQI), colour-coded by severity on the Indian CPCB scale.
- **📊 City Deep-Dive** — Click any city for a pollutant breakdown, live weather, a 24-hour
  AQI trend, and a hybrid 24h forecast scored against a persistence benchmark.
- **🔬 AI Source Attribution** — Estimates what's polluting each city (traffic, industry,
  construction, biomass), anchored to published CPCB/ARAI source-apportionment studies and
  adjusted for live weather and time of day, with a deterministic confidence score.
- **💬 Multilingual Health Advisory** — A chatbot that answers citizen air-quality questions
  in **any Indian language** (English, हिंदी, தமிழ், ಕನ್ನಡ, …), auto-detecting the language
  and replying in the same script.

---

## 🏗️ Tech Stack

| Layer | Tech |
|-------|------|
| Frontend | React, Vite, Tailwind CSS v4, Leaflet.js (+ marker clustering) |
| Backend | FastAPI (Python 3.11), httpx, tenacity |
| AI | Azure OpenAI `gpt-5-nano` (reasoning model), async client |
| AQI data | WAQI (live CPCB feeds) → static fallback dataset |
| Geospatial | OpenStreetMap / Overpass API (emission source registry) |
| Satellite | NASA FIRMS (VIIRS 375 m active-fire detection) |
| Weather | OpenWeatherMap (incl. wind direction, which drives upwind scoring) |

**Resilience.** Per-city AQI fallback — one bad reading downgrades that city's freshness
rather than dropping it off the map — plus a 10-minute station cache warmed at startup,
retry-with-backoff on all external calls, and rate limiting on the LLM-backed endpoints
(`X-Forwarded-For` aware, so a proxy doesn't collapse every caller into one bucket).

**Concurrency.** All LLM calls go through the *async* Azure client (`services/llm.py`,
`acall_llm` / `acall_llm_json`). This matters for enforcement: the attribution stage fans out
one call per hotspot with `asyncio.gather`, and under the synchronous client those coroutines
ran strictly back to back *and* blocked the event loop for the whole round trip — so the
fan-out delivered neither parallelism nor concurrency, and froze every other request while it
worked. A timing test asserts the fan-out actually overlaps.

---

## ⚖️ Enforcement Intelligence — how the correlation works

The problem statement asks for an agent that *"correlates pollution hotspot data with
registered emission sources … and generates prioritised, evidence-backed enforcement action
recommendations … with supporting geospatial documentation."*

That correlation is done with arithmetic, not by asking a language model to guess a plausible
zone name. The LLM is called **last**, and only to narrate a shortlist it cannot alter.

### 1. The source registry

`backend/data/emission_sources.json` holds registered emission sources with real coordinates,
seeded from OpenStreetMap via the Overpass API (`backend/scripts/fetch_emission_sources.py`)
across the four emitter types named in the problem statement:

| Category | OSM proxy | Count |
|---|---|---|
| Industry | `landuse=industrial`, `man_made=works` | 2,215 |
| Diesel fleet | `amenity=bus_station`, `landuse=depot`, `building=transportation` | 1,182 |
| Construction | `landuse=construction`, `building=construction` | 1,175 |
| Waste burning | `landuse=landfill`, `amenity=waste_transfer_station`, `waste_disposal` | 582 |

**5,154 sources across all 43 cities.** Seeded once and committed, so a demo never depends on
Overpass being up — and so a free shared community endpoint isn't hammered per request.

These are honest proxies, not an official register. Open waste burning is unmapped by nature
(it's illegal and therefore unregistered), so landfills and transfer stations stand in for it.
That caveat ships inside the registry's own `_meta` block and is surfaced through the API
rather than hidden. A production deployment would swap in CPCB consent-to-operate and state
PCB registers, which are not openly available.

### 2. Satellite fire detection

Open waste and biomass burning is the one major emitter that *cannot* appear in any ground
register. NASA FIRMS (VIIRS, 375 m) fills that gap: active-fire detections are fetched live
per hotspot (`backend/services/firms.py`) and ranked in the same candidate list as ground
facilities, weighted by the satellite's own detection confidence so a marginal thermal anomaly
counts for less than a strong one. They're drawn dashed on the map and labelled
*"Satellite-detected fire 3.2 km NW of Delhi centre"*.

The LLM is instructed to word these as *"verify and interdict active burning at these
coordinates"* rather than as an inspection of a registered premises — a thermal anomaly is a
lead to confirm on the ground, not a proven violation, and industrial flares and agricultural
fires also register.

Needs a free `FIRMS_MAP_KEY` (see `.env.example`). Purely additive: without one, enforcement
falls back to the ground registry alone and still works.

> **Seasonality, measured not assumed.** Verified live against the FIRMS API in late July:
> 138 active-fire detections across India over 3 days, **none within 25 km of any of the 43
> curated cities**. That is monsoon season doing what monsoon season does, not a broken
> integration — the pipeline was confirmed end to end by running the scorer against the real
> Tamil Nadu detections, which it ranked, upwind-filtered and labelled correctly. The layer
> carries real weight from October to January, when stubble and waste burning drive the
> northern air crisis. Because "enabled but found nothing" and "not configured" look identical
> in a response, the API reports `satellite: {enabled, total_detections}` and the UI says which.
>
> One API quirk: `FIRMS_DAY_RANGE` accepts 1–10, but over a large bounding box the longer
> windows silently return an **empty body** rather than an error — 1 day gave 15 detections,
> 3 gave 138, and 7 and 10 both gave nothing. That's a server-side transaction limit, so the
> default is 3 and it should not be raised.

### 3. Who must never be a target

Not every OSM entry is a usable enforcement target. Two filters run **before** scoring, so
geometry can never promote an excluded entry back.

**Hospitals, schools and places of worship.** OSM names transport infrastructure after
whatever it serves, so a bus terminal outside a hospital or temple inherits that place's name.
Two live runs surfaced this the hard way: the system recommended sending inspectors to
*"Park Circus - Chittaranjan Hospital"*, and then to *"Kamakhya Mandir"* — one of the most
significant Hindu temples in India. The underlying depots may well be real diesel sources, but
an enforcement order *named after* a hospital, school or place of worship is indefensible in
front of the authority meant to act on it, and in the religious case actively inflammatory.
Hospitals and schools are also receptors to protect from poor air, not premises to raid.

The filter matches on **name** rather than tag, precisely because the OSM *tag* says
`bus_station` while the *name* says temple — the tag is what admitted it, the name is what
would reach a dispatch order. It is deliberately tuned against over-matching too: an earlier
version caught `vihar` and removed several genuine bus depots, since across north India
"Vihar" is a residential locality suffix (Vasant Vihar, Mayur Vihar) far more often than a
Buddhist monastery. Both directions are covered by tests.

**Kerbside bus stops.** `amenity=bus_station` spans a state transport depot and a numbered
kerbside halt alike, so the registry fills with entries like "42A BUS STAND". These are
systematically advantaged — a bus stop sits in the middle of the city right beside the
monitoring station, so it beats a real depot on the outskirts on proximity — while offering
nothing to inspect. Geometry and name together decide it: a way or relation has area, so
something is actually built there; and a node naming itself a depot, terminal or garage is
kept even though it's a point. That leaves 743 of 1,182 fleet entries. The filter errs toward
exclusion deliberately, because putting "42A BUS STAND" at rank 1 would discredit every other
recommendation on the sheet.

### 4. The correlation

`backend/utils/enforcement_scoring.py` — deterministic, no LLM. For each hotspot, every
surviving source in that city is scored on:

| Component | Weight | Why |
|---|---|---|
| Proximity | 0.35 | Linear falloff to zero at 25 km |
| **Upwind alignment** | 0.28 | A source *downwind* of the station cannot be causing the reading |
| Category match | 0.18 | Corroboration from the upstream Attribution Agent |
| Dispatchability | 0.12 | ~half of OSM sites are unnamed; a named facility can be served notice |
| Hotspot severity | 0.07 | Only discriminates when ranking across cities |

The upwind test is the strongest single discriminator and came free: OpenWeatherMap's
`wind.deg` (the direction wind blows *from*) was already being fetched and discarded. Sources
more than ~102° off the wind axis are **excluded outright**, not ranked low — they are
eliminated on physical grounds, and padding a shortlist with them would overstate how much
evidence exists.

Unnamed sites still have exact coordinates, so they get a navigable positional label
(*"Unregistered industry site 2.1 km NW of Kolkata centre"*) instead of a useless one.

### 5. The narration

Only now is the LLM called — with a ranked shortlist of real facilities it must choose from by
exact ID, citing the distance and upwind evidence it was handed. It no longer decides *where*
to inspect; it writes the dispatch order. This is what it actually receives:

```
CITY: Kolkata - AQI 340 (Very Poor), PM2.5 180.0 μg/m³
  Attribution Agent dominant_source: Industry
  Live wind: from 315° at 12.0 km/h
  Ranked registered emission sources near this hotspot:
    - [way/101750901] Unregistered industry site 2.1 km NW of Kolkata centre |
      category: industry | 2.05 km NW of station | directly UPWIND (alignment 0.999) |
      evidence score 0.8288 | coords 22.586089,88.350254
```

Models copy prompt formatting, so a returned `source_id` of `[way/101750901]` is reconciled
back to the real entry (falling back to a name match), and any facility that still can't be
matched is flagged `source_matched: false` and labelled unverified in the UI rather than
presented as evidenced.

### 6. Geospatial documentation

The Enforcement tab renders the correlation on a map: the monitoring station, every candidate
source coloured by category and sized by evidence score, the wind axis, the 25 km screening
radius, and evidence lines from each candidate to the station. Selecting a priority focuses
its facility.

Each recommendation shows the component-score breakdown that produced it, exact coordinates,
and a link to the facility on OpenStreetMap — so the evidence is checkable in the UI, not just
in the API. `GET /api/intel/sources` exposes the registry directly. The endpoint also reports
`response_time_seconds`, the measured signal-to-dispatch latency the evaluation criteria ask
to see demonstrated (typically 30–60 s against live data).

---

## 🔬 Measurement & data integrity

**One AQI scale, end to end.** WAQI serves **US EPA** AQI *index* values (both `aqi` and
`iaqi.pm25.v`), not μg/m³ concentrations — a live Delhi feed returning `iaqi.pm25: 25` means
"EPA sub-index 25" (≈6 μg/m³), not "25 μg/m³". India's CPCB scale is stricter, so the two are
not interchangeable. Every WAQI reading is inverted back to a concentration (`epa_aqi_to_pm25`,
`backend/utils/aqi_calculator.py`) and re-expressed on the CPCB scale before use.

This matters most for **enforcement**: the hotspot ranking sorts live stations against static
fallback ones, so mixing EPA and CPCB values silently mis-ranked the cities feeding the
Enforcement Agent. Mid-range readings were worst affected — an EPA index of 100 (truly
"Satisfactory", 35.4 μg/m³) previously rendered as CPCB 234 "Poor". The original EPA value is
retained as `aqi_epa_raw` so the conversion stays auditable. Pollutants other than PM2.5 need
their own EPA breakpoint tables to invert, so they are surfaced honestly as `*_index` (EPA
sub-index) rather than mislabelled as μg/m³.

**Forecast accuracy against the named benchmark.** The evaluation criteria ask for *"RMSE
versus persistence baseline"*, so both halves of that comparison are computed rather than one
number in isolation. Persistence — "it will stay exactly as it is now" — is the naive benchmark
any forecast must beat to have demonstrated skill at all. `backtest_baseline` holds out the
last 6 hours of real history and reports the statistical model's RMSE, persistence's own RMSE,
and a skill score (`1 - RMSE_model / RMSE_persistence`).

The metric reports failure honestly. On a series where the trend reverses, the extrapolation
loses badly to persistence and the UI says so in amber rather than hiding it. On a flat series
persistence is already perfect, so the skill score returns `null` instead of dividing by zero
and implying an achievement. A metric that can only flatter isn't a measurement.

The response also reports `llm_divergence_from_baseline` — how far the LLM's delivered forecast
sits from the baseline it was anchored to. The backtest measures the *baseline's* skill, and
that only carries over to the line shown to the user insofar as the two agree; quoting the RMSE
without this would overstate what was verified.

**Beyond a pure LLM wrapper.** The 24h forecast is a hybrid: a deterministic statistical
baseline (`backend/utils/forecast_baseline.py`, no LLM call) that the LLM must explain or
justify diverging from, not invent from scratch. Source attribution carries a deterministic
confidence score (`backend/utils/attribution_confidence.py`) measuring how far the LLM strayed
from the cited CPCB baseline. Enforcement runs a three-stage chain — Attribution Agent →
deterministic geospatial correlation → Enforcement Agent — where each stage's output is the
next stage's evidence, not an independent guess.

---

## ⚠️ Known gaps

Stated here rather than discovered later:

- **OpenAQ tier is non-functional.** `services/openaq.py` points at `api.openaq.io/v2`, a host
  that no longer resolves (OpenAQ retired v2; v3 needs an API key). The AQI fallback is
  therefore **WAQI → static dataset**, not three tiers. In practice the 24h history shown in
  the city panel is always the synthetic diurnal estimate — which the UI does disclose
  ("Modelled estimate — no live station history available").
- **City-level, not ward-level.** The problem statement asks for ward / 1 km grid resolution;
  this operates on 43 city monitoring points.
- **No multi-city comparative dashboard** and **no population vulnerability layer**, though the
  sensitive-receptor filter already identifies hospitals and schools in the registry.

---

## 🚀 Quick Start

### Prerequisites
- Python 3.11+, Node.js 18+
- API keys: [Azure OpenAI](https://azure.microsoft.com/products/ai-services/openai-service),
  [WAQI](https://aqicn.org/data-platform/token/),
  [OpenWeatherMap](https://openweathermap.org/api),
  and optionally [NASA FIRMS](https://firms.modaps.eosdis.nasa.gov/api/area/) (free)

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
pytest tests/ -q                # 106 unit tests, no network or API keys required
python test_endpoints.py        # HTTP integration suite, needs a running server + real keys
```

### Re-seeding the source registry (optional)
The registry is committed, so this is only needed to refresh it:
```bash
cd backend
python scripts/fetch_emission_sources.py   # ~40 min; resumes if interrupted
```
It rotates across three Overpass mirrors on 429/504 and writes after every city, so an
interrupted run keeps its progress.

---

## 📡 API Endpoints

| Method | Route | Description |
|--------|-------|-------------|
| `GET`  | `/api/aqi/live` | All live India stations (cached, CPCB scale) |
| `GET`  | `/api/aqi/city/{name}?lat=&lon=` | City feed + weather + 24h history |
| `POST` | `/api/intel/attribution` | Pollution source breakdown + confidence score |
| `GET`  | `/api/intel/enforcement/auto` | **Registry-correlated enforcement priorities for the top-5 live hotspots** |
| `POST` | `/api/intel/enforcement` | Same correlation, for a caller-supplied set of cities |
| `GET`  | `/api/intel/sources` | Emission source registry — coverage + provenance (`?city=Delhi` for one city) |
| `POST` | `/api/intel/forecast` | Hybrid 24h AQI forecast + accuracy vs persistence |
| `POST` | `/api/intel/advisory` | Multilingual citizen health advisory |

---

## 📁 Project Structure

```
airwatch/
├── backend/
│   ├── main.py                        App, CORS, rate-limit middleware, cache warm
│   ├── prompts.py                     LLM prompts + CPCB source-apportionment table
│   ├── routes/
│   │   ├── aqi.py                     /api/aqi/*
│   │   └── intelligence.py            /api/intel/* — the enforcement chain lives here
│   ├── services/
│   │   ├── waqi.py                    Live AQI (EPA→CPCB conversion, per-city fallback)
│   │   ├── openaq.py                  Backup AQI + 24h history (see Known gaps)
│   │   ├── openweather.py             Weather + wind direction
│   │   ├── firms.py                   NASA FIRMS satellite fire detection
│   │   ├── source_registry.py         Emission source registry access layer
│   │   ├── llm.py                     Azure OpenAI (sync + async clients)
│   │   ├── cache.py                   Station + attribution caches
│   │   └── rate_limit.py              Sliding-window limiter
│   ├── utils/
│   │   ├── aqi_calculator.py          CPCB breakpoints + EPA→CPCB inversion
│   │   ├── enforcement_scoring.py     Deterministic hotspot↔source correlation
│   │   ├── forecast_baseline.py       Statistical forecast + persistence backtest
│   │   └── attribution_confidence.py  Divergence-from-baseline scoring
│   ├── scripts/fetch_emission_sources.py   Overpass seeder (mirrors, resume)
│   ├── data/
│   │   ├── cities_fallback.json       43 curated cities
│   │   └── emission_sources.json      5,154 registered emission sources
│   └── tests/                         106 unit + integration tests
└── frontend/src/
    ├── App.jsx                        Tabs: Map / Enforcement / Advisory
    └── components/
        ├── MapView.jsx                Clustered national AQI map
        ├── CityPanel.jsx              Pollutants, trend, attribution, forecast
        ├── EnforcementMap.jsx         Hotspot, candidates, wind axis, screening radius
        ├── EnforcementSidebar.jsx     Ranked actions + evidence breakdown
        ├── ForecastChart.jsx          Baseline vs AI forecast + skill scores
        └── AdvisoryGenerator.jsx      Multilingual citizen chatbot
```

See **[HANDOFF.md](HANDOFF.md)** for architecture details and known gotchas
(reasoning-model token budgets, etc.).

---

## 🔑 Configuration

All secrets live in `backend/.env` (gitignored — never committed). Copy `backend/.env.example`
and fill in your keys. Note: `gpt-5-nano` requires API version `2025-04-01-preview` and
`reasoning_effort="low"` — with default effort it can burn the entire token budget on hidden
reasoning and return empty output, especially for token-heavy scripts like Tamil and Kannada.

---

## 📝 License

Built for a hackathon — no license specified. Contact the author before reuse.
