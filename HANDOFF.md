# AirWatch India — Project Handoff

**Urban Air Quality Intelligence Platform** — ET AI Hackathon 2026, Problem Statement 5.

A live map of India's air quality with AI-powered pollution source attribution, enforcement
prioritisation, forecasting, and a multilingual citizen health advisory chatbot.

---

## 1. Current Status

**Working end-to-end.** All 6 backend endpoints pass an HTTP integration suite (14/14).
Frontend map, city detail, enforcement, and advisory chatbot are all functional.

| Area | Status |
|------|--------|
| Live AQI map (Leaflet, 21 real WAQI stations) | ✅ Working |
| City detail panel (feed + weather + 24h history) | ✅ Working |
| Source attribution (LLM, CPCB-anchored) | ✅ Working |
| Enforcement priorities (LLM, top-5 cities) | ✅ Working |
| Citizen advisory chatbot (multilingual) | ✅ Working |
| 24h forecast endpoint | ✅ Endpoint works; not yet wired into a UI tab |
| Deployment (Vercel + backend host) | ⬜ Not done |

---

## 2. Architecture

```
airwatch/
├── backend/                 FastAPI (Python 3.11)
│   ├── main.py              App + CORS + lifespan cache warm
│   ├── routes/
│   │   ├── aqi.py           /api/aqi/live, /api/aqi/city/{name}
│   │   └── intelligence.py  /api/intel/{attribution,enforcement,forecast,advisory}
│   ├── services/
│   │   ├── waqi.py          Primary AQI source (India bounds query)
│   │   ├── openaq.py        Backup AQI source
│   │   ├── openweather.py   Weather context for LLM prompts
│   │   ├── llm.py           Azure OpenAI wrapper (call_llm, call_llm_json)
│   │   └── cache.py         10-min in-memory station cache
│   ├── utils/aqi_calculator.py   CPCB AQI breakpoints + categories
│   ├── prompts.py           All LLM system/user prompt builders
│   ├── data/cities_fallback.json Static fallback data
│   ├── test_endpoints.py    HTTP integration suite (run against live server)
│   └── tests/               Unit tests (pytest)
└── frontend/                React + Vite + Tailwind v4
    └── src/
        ├── App.jsx          Tabs: Map / Enforcement / Advisory
        ├── hooks/useAQI.js  Polls /api/aqi/live
        ├── services/api.js  Axios API client
        └── components/       MapView, CityPanel, EnforcementSidebar,
                              AdvisoryGenerator, ForecastChart, ErrorBoundary
```

**Data flow (3-tier fallback for AQI):** WAQI → OpenAQ → static `cities_fallback.json`.
Station data is cached at startup (`lifespan` in `main.py`) for 10 minutes.

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
- Uses `max_completion_tokens`, **not** `max_tokens`. All calls set it to **6000–8000**;
  anything under ~4000 returns empty content because reasoning eats the whole budget.
- Does **not** support a custom `temperature` — must be omitted entirely.
- Requires API version **`2025-04-01-preview`**. Stable versions like `2024-02-01` return 404.
- `services/llm.py` guards against `None` content and raises a clear error if the budget runs out.

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

1. **Wire the forecast into the UI** — `/api/intel/forecast` works and `ForecastChart.jsx`
   exists, but there's no tab/panel calling it yet.
2. **Deploy** — frontend to Vercel (set `VITE_API_URL`), backend to a host (Render/Railway/
   Azure). Add the deployed frontend URL to `allow_origins` in `main.py`.
3. **Persist cache** — current cache is in-memory per-process; consider Redis for multi-worker.
4. **Rate-limiting / cost control** on LLM endpoints before any public demo.
5. **Presentation / demo script** for the hackathon submission.

See `PS5_AirQuality_Implementation_Plan.md` (repo root) for the original full plan.
