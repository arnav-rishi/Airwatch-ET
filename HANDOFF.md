# AirWatch India — Project Handoff

**Urban Air Quality Intelligence Platform** — ET AI Hackathon 2026, Problem Statement 5.

A live map of India's air quality with AI-powered pollution source attribution, enforcement
prioritisation, forecasting, and a multilingual citizen health advisory chatbot.

---

## 1. Current Status

**Working end-to-end**, verified against live WAQI, OpenWeatherMap, Azure OpenAI and NASA
FIRMS. 150 unit/integration tests pass with no keys or network required.

| Area | Status |
|------|--------|
| **Enforcement: registry correlation (5,154 sources, 43 cities)** | ✅ Working — the primary focus |
| **Enforcement: Gaussian plume dispersion (Pasquill-Gifford)** | ✅ Working |
| **Enforcement: geospatial map + auditable evidence** | ✅ Working |
| **Enforcement: quantified impact (search-space narrowing)** | ✅ Working, computed live |
| Satellite fire detection (NASA FIRMS / VIIRS) | ✅ Working — 0 detections in monsoon; see README |
| Spatial grid index (cross-city airshed queries) | ✅ Working |
| Live AQI map (Leaflet, 43 curated cities via WAQI, per-city fallback) | ✅ Working — now on the CPCB scale |
| City detail panel (feed + weather + 24h history) | ✅ Working — 24h history is always synthetic, see §Known gaps |
| Source attribution (LLM, CPCB-anchored, deterministic confidence score) | ✅ Working |
| 24h forecast (hybrid + RMSE vs persistence + skill score) | ✅ Working |
| Citizen advisory chatbot (multilingual) | ✅ Working |
| Rate limiting on `/api/intel/*` | ✅ Working (in-memory, per-process — see SCALABILITY.md) |
| CI (`.github/workflows/ci.yml`) | ✅ Runs pytest + frontend build on every push |
| Deployment (Vercel) | ⚠️ Tracks `master`; the enforcement work is on a feature branch — **merge before demoing** |
| Architecture diagram / deck / demo video | ⚠️ Required deliverables — see §Deliverables |

---

## 2. Architecture

```
airwatch/
├── .github/workflows/ci.yml  pytest + frontend build on every push/PR
├── backend/                 FastAPI (Python 3.11)
│   ├── main.py              App + CORS + rate-limit middleware + lifespan cache warm
│   ├── routes/
│   │   ├── aqi.py           /api/aqi/live, /api/aqi/city/{name}
│   │   └── intelligence.py  /api/intel/{attribution,enforcement,forecast,advisory}
│   ├── services/
│   │   ├── waqi.py          Primary AQI source (EPA->CPCB conversion, per-city fallback)
│   │   ├── openaq.py        Backup AQI + 24h history (NON-FUNCTIONAL - see Known gaps)
│   │   ├── openweather.py   Weather; wind speed + direction drive the plume model
│   │   ├── firms.py         NASA FIRMS satellite active-fire detection
│   │   ├── source_registry.py  Emission source registry + spatial grid index
│   │   ├── llm.py           Azure OpenAI wrapper (sync + async clients)
│   │   ├── cache.py         10-min in-memory station + attribution caches
│   │   └── rate_limit.py    In-memory sliding-window limiter for /api/intel/*
│   ├── utils/
│   │   ├── aqi_calculator.py         CPCB breakpoints + EPA->CPCB inversion
│   │   ├── enforcement_scoring.py    Deterministic hotspot<->source correlation
│   │   ├── dispersion.py             Gaussian plume + Pasquill-Gifford stability
│   │   ├── impact_metrics.py         Search-space narrowing from the registry
│   │   ├── forecast_baseline.py      Stat forecast + persistence backtest (no LLM)
│   │   └── attribution_confidence.py Divergence-from-baseline confidence scoring
│   ├── prompts.py           All LLM system/user prompt builders + CPCB citation table
│   ├── scripts/
│   │   ├── fetch_emission_sources.py Overpass seeder (mirrors, resume)
│   │   └── benchmark_spatial.py      Reproduces SCALABILITY.md figures
│   ├── data/
│   │   ├── cities_fallback.json      Static fallback data (43 cities)
│   │   └── emission_sources.json     5,154 registered emission sources
│   ├── test_endpoints.py    HTTP integration suite (run against live server)
│   └── tests/               150 unit + integration tests, no keys needed
└── frontend/                React + Vite + Tailwind v4
    └── src/
        ├── App.jsx          Tabs: Map / Enforcement / Advisory
        ├── hooks/useAQI.js  Polls /api/aqi/live
        ├── services/api.js  Axios API client
        ├── constants/enforcement.js  MAX_RELEVANT_KM mirror of the backend
        └── components/      MapView, CityPanel, EnforcementMap,
                             EnforcementSidebar, AdvisoryGenerator,
                             ForecastChart, ErrorBoundary
```

**Data flow (map stations):** A curated list of major Indian cities
(`data/cities_fallback.json`, 43 cities as of 2026-07-17, each with a WAQI `slug`) is fetched
**live** in parallel via WAQI's **named city feeds** (`/feed/{slug}/`). Every curated city is
always shown: one whose live feed fails (bad slug, timeout, no current reading) falls back to
its own last-known static reading (`source: "fallback"`) instead of being dropped — so a single
flaky request no longer thins out the map, it only ages that one marker. The map tooltip already
shows each station's `source`, so live vs. fallback is transparent per-marker. Only if the HTTP
client itself fails entirely does it fall back further, to OpenAQ → the full static dataset, so
the app is never blank. Station data is cached at startup (`lifespan` in `main.py`) for 10
minutes.

> ⚠️ Do NOT use WAQI's `/map/bounds/` or `/feed/geo:lat;lon/` for this — bounds returns a
> downsampled cluster dominated by Nepal/Tibet stations, and geo-feed frequently resolves
> distant cities to a default Delhi station. Named feeds (`/feed/{slug}/`) are the reliable path.

---

## 3. Running Locally

### Backend
```powershell
cd airwatch/backend
python -m venv venv            # first time only
venv\Scripts\activate
pip install -r requirements.txt   # first time only
# copy .env.example -> .env and fill in real keys (see section 5)
uvicorn main:app --reload --port 8001
```
Wait for `[cache] Loaded N stations.` and `Application startup complete.`

### Frontend
```powershell
cd airwatch/frontend
npm install                   # first time only
npm run dev
```
Opens on http://localhost:5173 (or 5174 if 5173 is taken).

### Verify backend health
```powershell
cd airwatch/backend
venv\Scripts\python.exe test_endpoints.py    # expects: 14/14 passed
```

---

## 4. Key Technical Decisions & Gotchas

These caused real debugging pain — read before touching the LLM or proxy code.

### Azure OpenAI `gpt-5-nano` is a REASONING model
- Consumes **1,400–2,300 hidden reasoning tokens** before producing any visible output.
- Uses `max_completion_tokens`, **not** `max_tokens`. All calls set it to **8000**.
- **`reasoning_effort="low"` is REQUIRED** (`services/llm.py`). With default reasoning
  effort, token-heavy scripts like Tamil/Kannada consume the ENTIRE budget on hidden
  reasoning (`reasoning_tokens == max`, `finish_reason == "length"`) and return an
  **empty** advisory. `"low"` caps reasoning (~1500 tokens) leaving room for output.
- `call_llm` also guards against empty/whitespace content and raises a descriptive error.
- Does **not** support a custom `temperature` — must be omitted entirely.
- Requires API version **`2025-04-01-preview`**. Stable versions like `2024-02-01` return 404.
- `services/llm.py` guards against `None` content and raises a clear error if the budget runs out.
- **The `openai` Python package must actually be new enough to send `max_completion_tokens`
  and `reasoning_effort` to the Chat Completions endpoint.** `requirements.txt` used to read
  `openai>=1.30.0`, which resolves to old releases that raise
  `TypeError: Completions.create() got an unexpected keyword argument 'max_completion_tokens'`
  — a hard crash on every LLM call, not a graceful fallback. Verified working at
  **`openai==2.45.0`**, now pinned exactly in `requirements.txt`. Don't loosen this pin
  without testing an actual `call_llm()` round trip first.
- Relatedly: `openai==1.30.5` also breaks under `httpx>=0.28` (it still passes a `proxies`
  kwarg to `httpx.Client` that 0.28 removed) — another reason to install exactly from
  `requirements.txt` rather than letting pip resolve latest-compatible versions freely.

### Ports
- Backend runs on **8001** (port 8000 was blocked by Windows — WinError 10013).
- Frontend Vite proxy (`vite.config.js`) targets **`http://127.0.0.1:8001`** — explicit IPv4.
  Do **not** change this back to `localhost`: Node 17+ resolves `localhost` to IPv6 `::1`
  first, but uvicorn binds IPv4 `127.0.0.1`, so the proxy fails with 500s.

### Windows uvicorn `--reload` zombie processes
- If a **syntax error** occurs while the server is running, `--reload` keeps the last-working
  worker alive AND orphaned reloader processes keep holding port 8001. Symptom: endpoints
  return **empty 500s** no matter how often you "restart" — because the new server can't bind
  the port and the stale one answers.
- Fix: kill everything on the port, then restart.
  ```powershell
  Get-NetTCPConnection -LocalPort 8001 -State Listen -ErrorAction SilentlyContinue |
    ForEach-Object { taskkill /F /PID $_.OwningProcess }
  ```

### AQI standard
- Uses **India CPCB** breakpoints (not US-EPA). See `utils/aqi_calculator.py`.

### Advisory chatbot
- `AdvisoryGenerator.jsx` supports two modes via one `sendMessage()`:
  - no arg → "Generate" structured advisory in the selected language pill.
  - string arg → free-text chat; backend auto-detects the language and replies in the same script.
- City dropdown deduplicates stations by city (keeps highest-AQI per city) so the dropdown
  and the status bar always agree.

### Hybrid forecast, multi-agent enforcement, and confidence scoring — why they exist
The original forecast/attribution endpoints were 100% LLM output with nothing to check them
against — plausible numbers, no accuracy claim. Three additions close that gap without adding
new infrastructure or fabricating data:
- **`utils/forecast_baseline.py`** computes a forecast with zero LLM calls (persistence + linear
  trend + a wind-dispersion multiplier) and backtests its own accuracy (MAE) against real held-out
  history. `routes/intelligence.py::get_forecast` hands this to the LLM as the number it must
  explain or justify diverging from, instead of asking it to invent numbers from a blank page.
  `ForecastChart.jsx` plots both lines so a viewer can see exactly where (if anywhere) the AI
  actually disagreed with the deterministic baseline.
- **`utils/attribution_confidence.py`** measures how far the LLM's returned source breakdown
  actually is from the CPCB baseline it was anchored to (`prompts.py::CPCB_SOURCE_APPORTIONMENT`),
  and surfaces `high`/`medium`/`low`/`unverified` confidence in the API response and in
  `CityPanel.jsx`. High divergence isn't automatically wrong, but it's now visible instead of
  buried in free-form prose.
- **Multi-agent enforcement** (`routes/intelligence.py::_attribute_city`): `/enforcement/auto` now
  runs the Attribution Agent for each of the top-5 cities in parallel first, and the Enforcement
  Agent is instructed to ground its recommended violation type in that upstream `dominant_source`
  finding rather than re-guessing from AQI alone. Trade-off, stated plainly: this adds a real
  sequential dependency (~one attribution call's latency, ~15-20s) to `/enforcement/auto` — it's
  not free.

None of this claims to be a validated meteorological model or a trained classifier — it's a
linear baseline and a rule-based divergence check, honestly scoped to what's actually being
computed. See the repo's Phase 8-10 design-review conversation for the full reasoning on why
this was the highest-value addition relative to more exotic-sounding alternatives (federated
learning, TinyML, etc.) that this project doesn't have the hardware/data to do honestly.

---

## 5. Required API Keys (.env)

Copy `backend/.env.example` to `backend/.env` and fill in:

| Variable | Where to get it |
|----------|-----------------|
| `AZURE_OPENAI_API_KEY` / `_ENDPOINT` / `_DEPLOYMENT` / `_API_VERSION` | Azure OpenAI resource. Deployment = `gpt-5-nano`, version = `2025-04-01-preview` |
| `WAQI_TOKEN` | https://aqicn.org/data-platform/token/ |
| `OPENWEATHER_API_KEY` | https://openweathermap.org/api |

**`.env` is gitignored — never commit it.** Real keys are NOT in this repo.

---

## 6. What's Next (suggested)

1. **Sync the `deployment` branch** — it's currently behind `master` (missing the per-city WAQI
   fallback fix and everything in this document). Needs an explicit decision to merge/push since
   it triggers live Vercel auto-redeploy on two projects.
2. **Persist cache** — current cache and rate limiter are in-memory per-process; consider Redis
   for multi-worker/serverless deployments where they currently do nothing across invocations.
3. **Real sensor fusion** — WAQI and OpenAQ are currently a strict waterfall (primary → backup),
   not a fusion. A confidence-weighted combination when both sources return a value for the same
   city would be a real, modest accuracy improvement.
4. **Satellite data fusion (Sentinel-5P NO2)** — the highest-novelty-ceiling extension available;
   almost no comparable project pulls real satellite retrieval data instead of ground stations.
   Needs a real geospatial ingestion pipeline and validation against ground truth to be honest,
   not just a visual overlay.
5. **PII handling for advisory queries** — free-text citizen queries go to Azure OpenAI with no
   stated retention policy. A naive regex scrubber would give false confidence; this needs a
   properly resourced solution (e.g. Azure Content Safety's PII detection).
6. **Presentation / demo script** for the hackathon submission.

See `PS5_AirQuality_Implementation_Plan.md` (repo root) for the original full plan.

---

## Known gaps

Recorded here so they are not rediscovered under time pressure. Full detail in the README.

- **OpenAQ tier is non-functional.** `services/openaq.py` points at `api.openaq.io/v2`, a host
  that no longer resolves (OpenAQ retired v2; v3 needs a key). The AQI fallback is therefore
  **WAQI -> static dataset**, not three tiers, and the 24h history in the city panel is always
  the synthetic diurnal estimate. The UI does disclose this ("Modelled estimate"), but the
  underlying integration has never worked.
- **City-level, not ward-level.** The problem statement asks for ward / 1 km grid resolution.
- **No multi-city comparative dashboard**, and **no population vulnerability layer** — though
  the sensitive-receptor filter already identifies hospitals and schools in the registry.
- **Scale limits** are catalogued in [SCALABILITY.md](SCALABILITY.md): per-process caches and
  rate limiter, file-backed registry, static station list, no outcome persistence.

---

## Deliverables

| Required | Status | Where |
|---|---|---|
| Working prototype | ✅ | This repo |
| Architecture diagram | ✅ | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — Mermaid, renders on GitHub |
| Presentation deck | ✅ | [docs/DECK.md](docs/DECK.md) — Marp; `marp DECK.md --pdf` to export |
| Demo video | ⚠️ Script ready, **recording pending** | [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md) |

The demo script front-loads the pre-record checklist for a reason: the Enforcement
tab's first load runs six LLM calls (~48 s), and the attribution cache holds only
10 minutes. Pre-warm the tab, then record inside that window.

**Before demoing:** the enforcement work lives on `feature/enforcement-intelligence`. Vercel
builds from `master`. Merge first, or the live URL serves none of it.
