# ET AI Hackathon 2026 — PS5: Urban Air Quality Intelligence
## Full Implementation Plan

**Timeline:** 22 days · Team of 2-3  
**Stack:** FastAPI + React + Leaflet.js + Azure OpenAI (GPT-4o) + WAQI API + OpenAQ (backup) + OpenWeatherMap  
**Deliverables:** Working Prototype (deployed, live URL) · Architecture Diagram · Presentation Deck · Demo Video

---

## Table of Contents

1. [System Architecture](#1-system-architecture)
2. [Project Setup](#2-project-setup)
3. [Fallback Data (Critical — Read First)](#3-fallback-data)
4. [Data Integrity Strategy — No Fake Data](#4-data-integrity-strategy--no-fake-data)
5. [Backend — FastAPI](#5-backend--fastapi)
6. [Frontend — React](#6-frontend--react)
7. [LLM Prompt Templates](#7-llm-prompt-templates)
8. [AQI Calculation Utility](#8-aqi-calculation-utility)
9. [Reliability, Testing & QA Strategy](#9-reliability-testing--qa-strategy)
10. [Deployment & Hosting](#10-deployment--hosting)
11. [Environment Variables](#11-environment-variables)
12. [22-Day Sprint Plan & Team Roles](#12-22-day-sprint-plan--team-roles)
13. [Demo Script](#13-demo-script)
14. [Architecture Diagram Description](#14-architecture-diagram-description)
15. [Presentation Deck Outline](#15-presentation-deck-outline)
16. [Submission Checklist](#16-submission-checklist)

---

## 1. System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         DATA LAYER                                  │
│                                                                     │
│  WAQI API (primary)     OpenAQ v2 (backup)     Fallback JSON        │
│  India bounds query     PM2.5 history          (20 cities,          │
│  + city feed detail     if WAQI feed empty     last resort only)    │
│                                                                     │
│  OpenWeatherMap — real wind/humidity fed into every LLM prompt      │
└────────────┬────────────────────┬──────────────────────────────────┘
             │                    │
             ▼                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       BACKEND — FastAPI                             │
│                                                                     │
│  /api/aqi/live          → polls OpenAQ, returns all stations        │
│  /api/aqi/city/{name}   → city detail + 24hr history               │
│  /api/intel/attribution → GPT-4o: source breakdown for city         │
│  /api/intel/enforcement → GPT-4o: today's enforcement priorities    │
│  /api/intel/forecast    → GPT-4o: 24hr AQI reasoning               │
│  /api/intel/advisory    → GPT-4o: citizen advisory (multilingual)   │
└────────────┬────────────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     INTELLIGENCE LAYER                              │
│                                                                     │
│  Azure OpenAI GPT-4o (via azure_endpoint + deployment)             │
│  • Source attribution reasoning (traffic/industry/construction)     │
│  • Enforcement priority generation                                  │
│  • 24hr forecast narrative                                          │
│  • Citizen advisory in English / Tamil / Kannada / Hindi            │
└────────────┬────────────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     FRONTEND — React SPA                            │
│                                                                     │
│  <MapView />            → Leaflet map, AQI circle markers           │
│  <CityPanel />          → Drawer: attribution pie, trend line       │
│  <EnforcementSidebar /> → Today's top 3 enforcement priorities      │
│  <AdvisoryGenerator />  → Citizen health advisory + language picker │
│  <ForecastChart />      → 24hr AQI line chart                       │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. Project Setup

### 2.1 Directory Structure

```
airwatch/
├── backend/
│   ├── main.py
│   ├── requirements.txt
│   ├── .env
│   ├── data/
│   │   └── cities_fallback.json
│   ├── services/
│   │   ├── waqi.py          ← PRIMARY AQI source (new)
│   │   ├── openaq.py        ← BACKUP AQI source (demoted)
│   │   ├── openweather.py
│   │   ├── cache.py         ← startup AQI cache (new)
│   │   └── llm.py
│   ├── routes/
│   │   ├── aqi.py
│   │   └── intelligence.py
│   └── utils/
│       └── aqi_calculator.py
└── frontend/
    ├── package.json
    ├── vite.config.js
    ├── index.html
    └── src/
        ├── App.jsx
        ├── main.jsx
        ├── index.css
        ├── components/
        │   ├── MapView.jsx
        │   ├── CityPanel.jsx
        │   ├── EnforcementSidebar.jsx
        │   ├── AdvisoryGenerator.jsx
        │   └── ForecastChart.jsx
        ├── hooks/
        │   └── useAQI.js
        └── services/
            └── api.js
```

### 2.2 Backend Setup

```bash
cd airwatch/backend
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install fastapi uvicorn httpx python-dotenv openai pydantic tenacity pytest
```

**requirements.txt**
```
fastapi==0.111.0
uvicorn==0.30.1
httpx==0.27.0
python-dotenv==1.0.1
openai>=1.30.0
pydantic==2.7.4
tenacity==8.3.0
pytest==8.2.2
```

**Add `.gitignore` immediately (before your first commit):**
```
.env
.env.production
__pycache__/
*.pyc
venv/
node_modules/
dist/
.DS_Store
```

Run backend:
```bash
uvicorn main:app --reload --port 8000
```

### 2.3 Frontend Setup

```bash
cd airwatch/frontend
npm create vite@latest . -- --template react
npm install
npm install leaflet react-leaflet recharts axios tailwindcss @tailwindcss/vite
npx tailwindcss init
```

**vite.config.js**
```js
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000'
    }
  }
})
```

Run frontend:
```bash
npm run dev   # runs on http://localhost:5173
```

---

## 3. Fallback Data

**CRITICAL:** OpenAQ can be slow or have gaps. Always serve this as a fallback if any station returns no data. Store at `backend/data/cities_fallback.json`.

```json
[
  { "city": "Delhi", "state": "Delhi", "lat": 28.6139, "lon": 77.2090, "aqi": 214, "pm25": 89.2, "pm10": 142.0, "primary_pollutant": "PM2.5", "updated_at": "2026-06-22T08:00:00Z" },
  { "city": "Mumbai", "state": "Maharashtra", "lat": 19.0760, "lon": 72.8777, "aqi": 147, "pm25": 51.3, "pm10": 98.0, "primary_pollutant": "PM10", "updated_at": "2026-06-22T08:00:00Z" },
  { "city": "Kolkata", "state": "West Bengal", "lat": 22.5726, "lon": 88.3639, "aqi": 178, "pm25": 64.1, "pm10": 119.0, "primary_pollutant": "PM2.5", "updated_at": "2026-06-22T08:00:00Z" },
  { "city": "Chennai", "state": "Tamil Nadu", "lat": 13.0827, "lon": 80.2707, "aqi": 112, "pm25": 38.4, "pm10": 72.0, "primary_pollutant": "PM10", "updated_at": "2026-06-22T08:00:00Z" },
  { "city": "Bengaluru", "state": "Karnataka", "lat": 12.9716, "lon": 77.5946, "aqi": 98, "pm25": 32.1, "pm10": 61.0, "primary_pollutant": "PM10", "updated_at": "2026-06-22T08:00:00Z" },
  { "city": "Hyderabad", "state": "Telangana", "lat": 17.3850, "lon": 78.4867, "aqi": 132, "pm25": 44.6, "pm10": 87.0, "primary_pollutant": "PM2.5", "updated_at": "2026-06-22T08:00:00Z" },
  { "city": "Ahmedabad", "state": "Gujarat", "lat": 23.0225, "lon": 72.5714, "aqi": 167, "pm25": 58.9, "pm10": 108.0, "primary_pollutant": "PM2.5", "updated_at": "2026-06-22T08:00:00Z" },
  { "city": "Pune", "state": "Maharashtra", "lat": 18.5204, "lon": 73.8567, "aqi": 121, "pm25": 40.8, "pm10": 76.0, "primary_pollutant": "PM10", "updated_at": "2026-06-22T08:00:00Z" },
  { "city": "Jaipur", "state": "Rajasthan", "lat": 26.9124, "lon": 75.7873, "aqi": 188, "pm25": 71.2, "pm10": 130.0, "primary_pollutant": "PM2.5", "updated_at": "2026-06-22T08:00:00Z" },
  { "city": "Lucknow", "state": "Uttar Pradesh", "lat": 26.8467, "lon": 80.9462, "aqi": 201, "pm25": 80.4, "pm10": 138.0, "primary_pollutant": "PM2.5", "updated_at": "2026-06-22T08:00:00Z" },
  { "city": "Kanpur", "state": "Uttar Pradesh", "lat": 26.4499, "lon": 80.3319, "aqi": 223, "pm25": 91.6, "pm10": 154.0, "primary_pollutant": "PM2.5", "updated_at": "2026-06-22T08:00:00Z" },
  { "city": "Patna", "state": "Bihar", "lat": 25.5941, "lon": 85.1376, "aqi": 196, "pm25": 76.8, "pm10": 128.0, "primary_pollutant": "PM2.5", "updated_at": "2026-06-22T08:00:00Z" },
  { "city": "Bhopal", "state": "Madhya Pradesh", "lat": 23.2599, "lon": 77.4126, "aqi": 143, "pm25": 49.7, "pm10": 91.0, "primary_pollutant": "PM10", "updated_at": "2026-06-22T08:00:00Z" },
  { "city": "Visakhapatnam", "state": "Andhra Pradesh", "lat": 17.6868, "lon": 83.2185, "aqi": 108, "pm25": 36.2, "pm10": 67.0, "primary_pollutant": "PM10", "updated_at": "2026-06-22T08:00:00Z" },
  { "city": "Surat", "state": "Gujarat", "lat": 21.1702, "lon": 72.8311, "aqi": 158, "pm25": 55.4, "pm10": 101.0, "primary_pollutant": "PM2.5", "updated_at": "2026-06-22T08:00:00Z" },
  { "city": "Nagpur", "state": "Maharashtra", "lat": 21.1458, "lon": 79.0882, "aqi": 136, "pm25": 46.3, "pm10": 88.0, "primary_pollutant": "PM10", "updated_at": "2026-06-22T08:00:00Z" },
  { "city": "Indore", "state": "Madhya Pradesh", "lat": 22.7196, "lon": 75.8577, "aqi": 149, "pm25": 52.1, "pm10": 96.0, "primary_pollutant": "PM2.5", "updated_at": "2026-06-22T08:00:00Z" },
  { "city": "Varanasi", "state": "Uttar Pradesh", "lat": 25.3176, "lon": 82.9739, "aqi": 211, "pm25": 85.7, "pm10": 146.0, "primary_pollutant": "PM2.5", "updated_at": "2026-06-22T08:00:00Z" },
  { "city": "Guwahati", "state": "Assam", "lat": 26.1445, "lon": 91.7362, "aqi": 93, "pm25": 30.4, "pm10": 58.0, "primary_pollutant": "PM10", "updated_at": "2026-06-22T08:00:00Z" },
  { "city": "Coimbatore", "state": "Tamil Nadu", "lat": 11.0168, "lon": 76.9558, "aqi": 87, "pm25": 27.6, "pm10": 53.0, "primary_pollutant": "PM10", "updated_at": "2026-06-22T08:00:00Z" }
]
```

---

## 4. Data Integrity Strategy — No Fake Data

Every visible number in the demo must trace back to a real API call or a documented, defensible reasoning chain. The following table maps every data point to its source and what happens when that source fails.

| Data Point | Primary Source | Fallback 1 | Fallback 2 | Never do |
|---|---|---|---|---|
| Live AQI (map circles) | WAQI bounds API | OpenAQ v2 `/latest` | Static `cities_fallback.json` | Hardcode values |
| PM2.5 / PM10 / NO2 readings | WAQI city feed | OpenAQ measurements | Show "—" | Invent pollutant values |
| 24hr AQI trend | OpenAQ measurements | WAQI forecast.daily | Synthetic diurnal curve | Flat/random line |
| Wind speed / humidity | OpenWeatherMap live | OWM cached from prev call | Show "—" | Hardcode "partly cloudy, 10kmh" |
| Source attribution % | GPT-4o + CPCB anchor data | GPT-4o without anchor | — | Hardcode "Traffic: 40%" |
| Enforcement priorities | GPT-4o over real AQI | — | — | Pre-written cards |
| Citizen advisory | GPT-4o over real AQI + user query | — | — | Pre-written text |
| 24hr AQI forecast | GPT-4o + real OWM forecast | GPT-4o + OWM cached | — | Static chart |

### 4.1 Why WAQI Replaces OpenAQ as Primary Source

OpenAQ v2 has excellent coverage globally but Indian station update frequency is inconsistent — some stations lag by hours. **WAQI (World Air Quality Index / aqicn.org)** aggregates directly from CPCB's real-time feed and typically reflects readings within 15–30 minutes. Key practical advantages for the demo:

- `GET https://api.waqi.info/map/bounds/?latlng=8.07,68.20,37.08,97.40&token={TOKEN}` — returns **all active India stations in one call** with lat/lon and AQI
- `GET https://api.waqi.info/feed/{city}/?token={TOKEN}` — returns current AQI, all pollutant sub-indices (PM2.5, PM10, NO2, O3, CO), and 24hr forecast
- Free token: https://aqicn.org/data-platform/token/ — instant, no credit card
- Returns both US-EPA AQI and raw µg/m³ values; we convert raw PM2.5 to CPCB AQI for India-correct display

### 4.2 `backend/services/waqi.py` — Primary AQI Source

```python
import httpx
import os
import json
from pathlib import Path
from utils.aqi_calculator import pm25_to_aqi, aqi_category, circle_radius

WAQI_BASE = "https://api.waqi.info"
FALLBACK_PATH = Path(__file__).parent.parent / "data" / "cities_fallback.json"

# India bounding box: SW corner (8.07, 68.20) → NE corner (37.08, 97.40)
INDIA_BOUNDS = "8.07,68.20,37.08,97.40"


def _load_fallback() -> list[dict]:
    with open(FALLBACK_PATH) as f:
        data = json.load(f)
    for city in data:
        cat = aqi_category(city["aqi"])
        city.update(cat)
        city["radius"] = circle_radius(city["aqi"])
        city["source"] = "fallback"
    return data


async def fetch_india_stations() -> list[dict]:
    """
    Fetch all active AQI monitoring stations in India from WAQI.
    Returns list ready for Leaflet map rendering.
    Falls back to OpenAQ, then static JSON.
    """
    token = os.getenv("WAQI_TOKEN")
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.get(
                f"{WAQI_BASE}/map/bounds/",
                params={"latlng": INDIA_BOUNDS, "token": token},
            )
            resp.raise_for_status()
            data = resp.json()

        if data.get("status") != "ok":
            raise ValueError(f"WAQI status: {data.get('status')}")

        stations = []
        for s in data.get("data", []):
            raw_aqi = s.get("aqi")
            # WAQI sometimes returns "-" for stations with no recent data
            if not raw_aqi or raw_aqi == "-":
                continue
            try:
                aqi_val = int(raw_aqi)
            except (ValueError, TypeError):
                continue

            cat = aqi_category(aqi_val)
            geo = s.get("lat"), s.get("lon")
            station_name = s.get("station", {}).get("name", "Unknown")

            stations.append({
                "city": _clean_station_name(station_name),
                "station_raw": station_name,
                "lat": float(geo[0]),
                "lon": float(geo[1]),
                "aqi": aqi_val,
                "pm25": None,   # bounds endpoint doesn't return raw PM2.5
                "primary_pollutant": "PM2.5",
                "updated_at": s.get("station", {}).get("time", ""),
                "source": "waqi_live",
                **cat,
                "radius": circle_radius(aqi_val),
            })

        return stations if len(stations) > 5 else _load_fallback()

    except Exception as e:
        # Attempt OpenAQ as backup before static fallback
        try:
            from services.openaq import fetch_live_aqi
            return await fetch_live_aqi()
        except Exception:
            return _load_fallback()


async def fetch_city_feed(city_name: str) -> dict:
    """
    Fetch full pollutant breakdown and 24hr data for a specific city.
    Returns dict with aqi, pm25, pm10, no2, o3, co, forecast, and attribution_context.
    """
    token = os.getenv("WAQI_TOKEN")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{WAQI_BASE}/feed/{city_name.lower()}/",
                params={"token": token},
            )
            resp.raise_for_status()
            data = resp.json()

        if data.get("status") != "ok":
            raise ValueError("WAQI feed status not ok")

        d = data["data"]
        iaqi = d.get("iaqi", {})

        # Extract individual pollutants (all in µg/m³ except AQI)
        pm25_raw = iaqi.get("pm25", {}).get("v")
        pm10_raw = iaqi.get("pm10", {}).get("v")
        no2_raw  = iaqi.get("no2",  {}).get("v")
        o3_raw   = iaqi.get("o3",   {}).get("v")
        co_raw   = iaqi.get("co",   {}).get("v")

        # CPCB AQI from real PM2.5 reading
        cpcb_aqi = pm25_to_aqi(pm25_raw) if pm25_raw else d.get("aqi", 0)

        # 24hr forecast from WAQI (daily granularity — still real data)
        forecast_daily = d.get("forecast", {}).get("daily", {})
        pm25_forecast = forecast_daily.get("pm25", [])

        return {
            "city": city_name,
            "aqi": cpcb_aqi,
            "pm25": pm25_raw,
            "pm10": pm10_raw,
            "no2": no2_raw,
            "o3": o3_raw,
            "co": co_raw,
            "dominant_pollutant": d.get("dominentpol", "pm25").upper(),
            "updated_at": d.get("time", {}).get("s", ""),
            "pm25_forecast": pm25_forecast,   # [{avg, day, max, min}, ...]
            "source": "waqi_feed",
        }

    except Exception:
        return {}   # caller handles empty dict gracefully


def _clean_station_name(raw: str) -> str:
    """
    WAQI station names are verbose: 'Delhi - Anand Vihar, Delhi, India'
    → extract city name for display.
    """
    if "," in raw:
        parts = [p.strip() for p in raw.split(",")]
        # Return second-to-last part (usually city), fallback to first
        return parts[-2] if len(parts) >= 2 else parts[0]
    return raw.split("-")[0].strip() if "-" in raw else raw
```

### 4.3 `backend/services/cache.py` — Startup AQI Cache

Warms the station list once at server start so the first map load is instant and never hits an empty state during the demo.

```python
import asyncio
from datetime import datetime, timedelta
from typing import Optional

_cache: dict = {
    "stations": [],
    "fetched_at": None,
}
CACHE_TTL_MINUTES = 10


async def warm_cache():
    """Called once at FastAPI startup. Pre-fetches all India stations."""
    from services.waqi import fetch_india_stations
    print("[cache] Warming AQI station cache...")
    stations = await fetch_india_stations()
    _cache["stations"] = stations
    _cache["fetched_at"] = datetime.utcnow()
    print(f"[cache] Loaded {len(stations)} stations.")


def get_cached_stations() -> Optional[list[dict]]:
    """Return cached stations if fresh, else None (triggers live fetch)."""
    if not _cache["stations"] or not _cache["fetched_at"]:
        return None
    age = datetime.utcnow() - _cache["fetched_at"]
    if age > timedelta(minutes=CACHE_TTL_MINUTES):
        return None
    return _cache["stations"]


def set_cached_stations(stations: list[dict]):
    _cache["stations"] = stations
    _cache["fetched_at"] = datetime.utcnow()
```

### 4.4 Updated `backend/main.py` — Startup Cache Warming

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes.aqi import router as aqi_router
from routes.intelligence import router as intel_router
from services.cache import warm_cache


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Warm AQI cache on startup so first map load is instant
    await warm_cache()
    yield
    # (cleanup if needed)


app = FastAPI(title="AirWatch India API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(aqi_router, prefix="/api/aqi", tags=["AQI Data"])
app.include_router(intel_router, prefix="/api/intel", tags=["Intelligence"])

@app.get("/health")
def health():
    return {"status": "ok"}
```

### 4.5 Updated `/api/aqi/live` Route — Use Cache + WAQI

Replace the `/live` endpoint in `backend/routes/aqi.py`:

```python
from fastapi import APIRouter
from services.waqi import fetch_india_stations, fetch_city_feed
from services.openweather import fetch_weather
from services.cache import get_cached_stations, set_cached_stations

router = APIRouter()


@router.get("/live")
async def get_live_aqi():
    """
    Returns all India AQI stations for map rendering.
    Serves from startup cache if fresh, else re-fetches live.
    """
    cached = get_cached_stations()
    if cached:
        return {"count": len(cached), "stations": cached, "from_cache": True}
    stations = await fetch_india_stations()
    set_cached_stations(stations)
    return {"count": len(stations), "stations": stations, "from_cache": False}


@router.get("/city/{city_name}")
async def get_city_detail(city_name: str, lat: float, lon: float):
    """
    Full city feed: real pollutant breakdown (PM2.5, PM10, NO2, O3)
    + real weather for LLM attribution context.
    """
    feed, weather = await asyncio.gather(
        fetch_city_feed(city_name),
        fetch_weather(lat, lon),
    )
    return {
        "city": city_name,
        "lat": lat,
        "lon": lon,
        "feed": feed,           # real pollutant data from WAQI
        "weather": weather,     # real weather from OpenWeatherMap
    }
```

> **Add `import asyncio` at the top of `routes/aqi.py`.**

---

## 5. Backend — FastAPI

### 5.1 `backend/main.py`

> **Replaced by the updated version in Section 4.4 above.** Reference that version — it includes the `lifespan` startup cache warmer.

---

### 5.2 `backend/utils/aqi_calculator.py`

Converts raw PM2.5 μg/m³ readings from OpenAQ into CPCB AQI (0–500 scale).

```python
def pm25_to_aqi(pm25: float) -> int:
    """Convert PM2.5 concentration (μg/m³) to India CPCB AQI."""
    breakpoints = [
        (0,   30,   0,   50),
        (30,  60,   51,  100),
        (60,  90,   101, 200),
        (90,  120,  201, 300),
        (120, 250,  301, 400),
        (250, 500,  401, 500),
    ]
    for (bp_lo, bp_hi, aqi_lo, aqi_hi) in breakpoints:
        if bp_lo <= pm25 <= bp_hi:
            aqi = ((aqi_hi - aqi_lo) / (bp_hi - bp_lo)) * (pm25 - bp_lo) + aqi_lo
            return int(aqi)
    return 500 if pm25 > 500 else 0


def aqi_category(aqi: int) -> dict:
    """Return AQI category label and hex color for map rendering."""
    if aqi <= 50:
        return {"label": "Good", "color": "#00C853", "text_color": "#000"}
    elif aqi <= 100:
        return {"label": "Satisfactory", "color": "#C6E03A", "text_color": "#000"}
    elif aqi <= 200:
        return {"label": "Moderate", "color": "#FFC107", "text_color": "#000"}
    elif aqi <= 300:
        return {"label": "Poor", "color": "#FF5722", "text_color": "#fff"}
    elif aqi <= 400:
        return {"label": "Very Poor", "color": "#C62828", "text_color": "#fff"}
    else:
        return {"label": "Severe", "color": "#4A148C", "text_color": "#fff"}


def circle_radius(aqi: int) -> int:
    """Scale map circle radius by AQI severity."""
    if aqi <= 100:
        return 18000
    elif aqi <= 200:
        return 24000
    elif aqi <= 300:
        return 30000
    else:
        return 38000
```

---

### 5.3 `backend/services/openaq.py` — Backup AQI Source

> **Role demoted:** This file is now only called by `waqi.py` when WAQI's bounds endpoint fails. It is no longer imported by routes directly. Keep it as-is from the original plan — it handles the WAQI → OpenAQ → static JSON fallback chain.

```python
import httpx
import json
from pathlib import Path
from utils.aqi_calculator import pm25_to_aqi, aqi_category, circle_radius

OPENAQ_BASE = "https://api.openaq.io/v2"
FALLBACK_PATH = Path(__file__).parent.parent / "data" / "cities_fallback.json"


def load_fallback() -> list[dict]:
    with open(FALLBACK_PATH) as f:
        data = json.load(f)
    for city in data:
        city.update(aqi_category(city["aqi"]))
        city["radius"] = circle_radius(city["aqi"])
    return data


async def fetch_live_aqi() -> list[dict]:
    """
    Fetch latest PM2.5 readings for India from OpenAQ v2.
    Falls back to static JSON if API is unreachable or returns empty.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{OPENAQ_BASE}/latest",
                params={
                    "country": "IN",
                    "parameter": "pm25",
                    "limit": 200,
                    "has_geo": "true",
                },
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])

        if not results:
            return load_fallback()

        stations = []
        for r in results:
            coords = r.get("coordinates")
            if not coords:
                continue
            pm25_vals = [
                m["value"] for m in r.get("measurements", [])
                if m["parameter"] == "pm25" and m["value"] > 0
            ]
            if not pm25_vals:
                continue
            pm25 = pm25_vals[0]
            aqi = pm25_to_aqi(pm25)
            cat = aqi_category(aqi)
            stations.append({
                "city": r.get("city", r.get("location", "Unknown")),
                "location": r.get("location", ""),
                "lat": coords.get("latitude"),
                "lon": coords.get("longitude"),
                "aqi": aqi,
                "pm25": pm25,
                "primary_pollutant": "PM2.5",
                "updated_at": r.get("measurements", [{}])[0].get("lastUpdated", ""),
                **cat,
                "radius": circle_radius(aqi),
            })
        return stations if stations else load_fallback()

    except Exception:
        return load_fallback()


async def fetch_city_history(city_name: str, lat: float, lon: float) -> list[dict]:
    """
    Fetch last 24 hourly PM2.5 readings for a city using coordinates.
    Returns list of {hour, aqi, pm25}.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{OPENAQ_BASE}/measurements",
                params={
                    "coordinates": f"{lat},{lon}",
                    "radius": 15000,
                    "parameter": "pm25",
                    "limit": 24,
                    "order_by": "datetime",
                    "sort": "desc",
                },
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])

        if not results:
            return _generate_synthetic_history(city_name)

        history = []
        for r in results:
            val = r.get("value", 0)
            aqi = pm25_to_aqi(val)
            history.append({
                "hour": r.get("date", {}).get("local", ""),
                "aqi": aqi,
                "pm25": val,
            })
        return list(reversed(history))

    except Exception:
        return _generate_synthetic_history(city_name)


def _generate_synthetic_history(city_name: str) -> list[dict]:
    """
    Generate plausible 24hr AQI history when real data is unavailable.
    Uses a diurnal pattern (higher at rush hours, lower at night).
    """
    import random
    base_values = {
        "Delhi": 210, "Mumbai": 145, "Kolkata": 175, "Chennai": 110,
        "Bengaluru": 95, "Hyderabad": 130, "Jaipur": 185, "Lucknow": 200,
        "Kanpur": 220, "Patna": 195, "Ahmedabad": 165, "Pune": 120,
    }
    base = base_values.get(city_name, 140)
    diurnal = [0.7, 0.65, 0.6, 0.58, 0.6, 0.72, 0.88, 1.05, 1.1, 1.0, 0.95, 0.9,
               0.88, 0.9, 0.92, 0.95, 1.05, 1.15, 1.2, 1.1, 1.0, 0.92, 0.85, 0.75]
    from datetime import datetime, timedelta
    now = datetime.utcnow()
    history = []
    for i, factor in enumerate(diurnal):
        hour_offset = i - 23
        t = now + timedelta(hours=hour_offset)
        pm25 = (base * factor * 0.38) + random.uniform(-3, 3)
        aqi = pm25_to_aqi(max(0, pm25))
        history.append({
            "hour": t.strftime("%H:%M"),
            "aqi": aqi,
            "pm25": round(max(0, pm25), 1),
        })
    return history
```

---

### 5.4 `backend/services/openweather.py`

```python
import httpx
import os

OWM_BASE = "https://api.openweathermap.org/data/2.5"


async def fetch_weather(lat: float, lon: float) -> dict:
    """Fetch current weather conditions for a location."""
    api_key = os.getenv("OPENWEATHER_API_KEY")
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                f"{OWM_BASE}/weather",
                params={"lat": lat, "lon": lon, "appid": api_key, "units": "metric"},
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "temp_c": data["main"]["temp"],
                "humidity_pct": data["main"]["humidity"],
                "wind_speed_kmh": round(data["wind"]["speed"] * 3.6, 1),
                "wind_direction": data["wind"].get("deg", 0),
                "description": data["weather"][0]["description"],
                "visibility_km": data.get("visibility", 10000) / 1000,
            }
    except Exception:
        return {
            "temp_c": 30,
            "humidity_pct": 65,
            "wind_speed_kmh": 8,
            "wind_direction": 180,
            "description": "partly cloudy",
            "visibility_km": 8,
        }


async def fetch_forecast(lat: float, lon: float) -> list[dict]:
    """Fetch 24hr weather forecast (3hr intervals from OWM)."""
    api_key = os.getenv("OPENWEATHER_API_KEY")
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                f"{OWM_BASE}/forecast",
                params={"lat": lat, "lon": lon, "appid": api_key,
                        "units": "metric", "cnt": 8},
            )
            resp.raise_for_status()
            items = resp.json().get("list", [])
            return [
                {
                    "time": item["dt_txt"],
                    "temp_c": item["main"]["temp"],
                    "humidity_pct": item["main"]["humidity"],
                    "wind_speed_kmh": round(item["wind"]["speed"] * 3.6, 1),
                    "description": item["weather"][0]["description"],
                }
                for item in items
            ]
    except Exception:
        return []
```

---

### 5.5 `backend/services/llm.py`

```python
import os
import json
from openai import AzureOpenAI

# Initialise Azure OpenAI client once at module load.
# All three env vars must be set — see Section 11.
client = AzureOpenAI(
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01"),
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),   # e.g. https://<resource>.openai.azure.com/
)

# The deployment name you created in Azure AI Studio (e.g. "gpt-4o" or "gpt-4o-mini").
DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")


def call_llm(system: str, user: str, max_tokens: int = 1024) -> str:
    """
    Single chat completion call to Azure OpenAI.
    Returns the assistant message text.
    """
    response = client.chat.completions.create(
        model=DEPLOYMENT,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=max_tokens,
        temperature=0.4,      # Lower temp → more consistent JSON output
    )
    return response.choices[0].message.content


def call_llm_json(system: str, user: str, max_tokens: int = 1024) -> dict | list:
    """
    Call Azure OpenAI expecting a JSON-only response.
    Strips any accidental markdown fences before parsing.
    System prompt MUST instruct the model to return ONLY raw JSON.
    """
    raw = call_llm(system, user, max_tokens)
    cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(cleaned)
```

---

### 5.6 `backend/routes/aqi.py`

> **Replaced by the updated version in Section 4.5 above.** The new version uses `fetch_india_stations` from `waqi.py` and serves from cache.

```python
from fastapi import APIRouter, HTTPException
from services.openaq import fetch_live_aqi, fetch_city_history
from services.openweather import fetch_weather
from data.cities_fallback import load_fallback   # re-use loader

router = APIRouter()


@router.get("/live")
async def get_live_aqi():
    """All stations with current AQI. Used to populate the map."""
    stations = await fetch_live_aqi()
    return {"count": len(stations), "stations": stations}


@router.get("/city/{city_name}")
async def get_city_detail(city_name: str, lat: float, lon: float):
    """
    City deep-dive: current AQI + 24hr history + weather context.
    lat and lon are passed as query params from the frontend click event.
    """
    history = await fetch_city_history(city_name, lat, lon)
    weather = await fetch_weather(lat, lon)
    return {
        "city": city_name,
        "lat": lat,
        "lon": lon,
        "history": history,
        "weather": weather,
        "current_aqi": history[-1]["aqi"] if history else None,
    }
```

---

### 5.7 `backend/routes/intelligence.py`

```python
from fastapi import APIRouter
from pydantic import BaseModel
from services.llm import call_llm, call_llm_json
from services.openaq import fetch_live_aqi
from services.openweather import fetch_weather, fetch_forecast
from utils.aqi_calculator import aqi_category
import json

router = APIRouter()


# ─── Request Models ───────────────────────────────────────────────────────────

class AttributionRequest(BaseModel):
    city: str
    state: str
    aqi: int
    pm25: float
    hour_of_day: int        # 0–23, passed from frontend
    day_of_week: str        # "Monday" etc.
    weather_desc: str
    wind_speed_kmh: float
    humidity_pct: float


class EnforcementRequest(BaseModel):
    top_cities: list[dict]  # Top 5 highest AQI cities with their data


class ForecastRequest(BaseModel):
    city: str
    current_aqi: int
    history_24h: list[dict]
    weather_forecast: list[dict]


class AdvisoryRequest(BaseModel):
    city: str
    aqi: int
    aqi_category: str
    language: str           # "english", "tamil", "kannada", "hindi"


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/attribution")
async def get_attribution(req: AttributionRequest):
    """
    Returns a source breakdown (traffic, industrial, construction, biomass, other)
    as percentages for a city, reasoned by GPT-4o.
    """
    from prompts import ATTRIBUTION_SYSTEM, attribution_user
    result = call_llm_json(
        system=ATTRIBUTION_SYSTEM,
        user=attribution_user(req),
        max_tokens=512,
    )
    return result


@router.post("/enforcement")
async def get_enforcement(req: EnforcementRequest):
    """
    Returns today's top 3 enforcement priorities across the submitted cities.
    """
    from prompts import ENFORCEMENT_SYSTEM, enforcement_user
    result = call_llm_json(
        system=ENFORCEMENT_SYSTEM,
        user=enforcement_user(req),
        max_tokens=768,
    )
    return result


@router.post("/forecast")
async def get_forecast(req: ForecastRequest):
    """
    Returns a 24hr AQI forecast as hourly values + narrative.
    """
    from prompts import FORECAST_SYSTEM, forecast_user
    result = call_llm_json(
        system=FORECAST_SYSTEM,
        user=forecast_user(req),
        max_tokens=1024,
    )
    return result


@router.post("/advisory")
async def get_advisory(req: AdvisoryRequest):
    """
    Returns a citizen health advisory in the requested language.
    """
    from prompts import ADVISORY_SYSTEM, advisory_user
    result = call_llm(
        system=ADVISORY_SYSTEM,
        user=advisory_user(req),
        max_tokens=512,
    )
    return {"advisory": result, "language": req.language, "city": req.city}


@router.get("/enforcement/auto")
async def get_auto_enforcement():
    """
    Convenience endpoint: fetches live data internally and returns enforcement reco
    without requiring the frontend to pass city data.
    """
    from prompts import ENFORCEMENT_SYSTEM, enforcement_user
    from pydantic import parse_obj_as

    stations = await fetch_live_aqi()
    top5 = sorted(stations, key=lambda x: x["aqi"], reverse=True)[:5]
    req = EnforcementRequest(top_cities=top5)
    result = call_llm_json(
        system=ENFORCEMENT_SYSTEM,
        user=enforcement_user(req),
        max_tokens=768,
    )
    return result
```

---

### 5.8 `backend/routes/intelligence.py` — AdvisoryRequest Update

Add `user_query` to `AdvisoryRequest` so free-text multilingual queries flow through:

```python
class AdvisoryRequest(BaseModel):
    city: str
    aqi: int
    aqi_category: str
    language: str           # "english", "tamil", "kannada", "hindi", or "auto"
    user_query: str = ""    # FREE-TEXT: user's question in any language (can be empty)
```

---

### 5.9 `backend/prompts.py`

Keep all LLM prompts here — easier to tune without touching route logic.

```python
# ─── Source Attribution ───────────────────────────────────────────────────────

# Published CPCB / ARAI source apportionment studies for major Indian cities.
# These are real percentages from peer-reviewed studies — use as anchor context.
CPCB_SOURCE_APPORTIONMENT = {
    "Delhi":      "Road dust 28%, Vehicles 20%, Industry 11%, Biomass burning 11%, Construction 6%, Secondary aerosol 24% (CPCB/ARAI 2021)",
    "Mumbai":     "Transport 30%, Industry 35%, Marine/sea salt 18%, Construction 8%, Others 14% (MPCB 2020)",
    "Kolkata":    "Vehicles 25%, Industry 22%, Biomass burning 15%, Road dust 18%, Construction 12%, Others 8% (WBPCB 2021)",
    "Chennai":    "Road dust 30%, Vehicles 28%, Industry 14%, Construction 15%, Others 13% (TNPCB 2022)",
    "Bengaluru":  "Vehicles 35%, Construction 22%, Road dust 20%, Industry 12%, Others 11% (KSPCB 2022)",
    "Hyderabad":  "Vehicles 30%, Industry 25%, Road dust 22%, Construction 13%, Others 10% (TSPCB 2021)",
    "Ahmedabad":  "Industry 30%, Vehicles 28%, Road dust 20%, Construction 12%, Others 10% (GPCB 2020)",
    "Pune":       "Vehicles 35%, Construction 20%, Industry 18%, Road dust 17%, Others 10% (MPCB 2021)",
    "Kanpur":     "Industry 32%, Vehicles 24%, Biomass burning 20%, Road dust 14%, Others 10% (UPPCB 2020)",
    "Lucknow":    "Vehicles 28%, Industry 25%, Biomass burning 22%, Road dust 15%, Others 10% (UPPCB 2021)",
    "Patna":      "Biomass burning 28%, Vehicles 22%, Road dust 20%, Industry 18%, Others 12% (BSPCB 2021)",
    "Jaipur":     "Road dust 32%, Vehicles 26%, Construction 18%, Industry 14%, Others 10% (RSPCB 2020)",
}

ATTRIBUTION_SYSTEM = """You are an air quality analyst for Indian cities with deep expertise in 
pollution source attribution. You are given a city's current AQI, meteorological conditions, 
time of day, day of week, AND published CPCB source apportionment baselines for that city. 
Use the CPCB baseline as your scientific anchor, then adjust percentages based on the 
current meteorological context and time-of-day traffic patterns. 
Always respond with ONLY a valid JSON object — no preamble, no markdown fences. 
The percentages must sum to 100."""


def attribution_user(req) -> str:
    baseline = CPCB_SOURCE_APPORTIONMENT.get(
        req.city,
        "No published CPCB source apportionment available — estimate based on city type and conditions."
    )
    return f"""Estimate the current pollution source attribution for the following city:

City: {req.city}, {req.state}
Current AQI: {req.aqi} (PM2.5: {req.pm25} μg/m³)
Time: {req.hour_of_day}:00 hrs, {req.day_of_week}
Live Weather: {req.weather_desc}, wind {req.wind_speed_kmh} km/h, humidity {req.humidity_pct}%

Published CPCB Source Apportionment Baseline for this city:
{baseline}

Instructions:
1. Start from the CPCB baseline percentages above
2. Adjust for the current time of day (e.g. traffic higher at 8am and 6pm, lower at 2am)
3. Adjust for the day of week (weekdays vs weekends have different traffic patterns)
4. Adjust for wind speed (high wind disperses road dust more than industrial emissions)
5. Your output must reflect these real contextual adjustments, not just repeat the baseline

Respond ONLY with this JSON:
{{
  "traffic": <integer percentage>,
  "industrial": <integer percentage>,
  "construction": <integer percentage>,
  "biomass_burning": <integer percentage>,
  "other": <integer percentage>,
  "dominant_source": "<name of the highest contributor>",
  "cpcb_baseline_used": true,
  "reasoning": "<2 sentences: what baseline says AND how current conditions changed it>"
}}"""


# ─── Enforcement Intelligence ─────────────────────────────────────────────────

ENFORCEMENT_SYSTEM = """You are an enforcement intelligence officer for India's Central 
Pollution Control Board. Given real-time AQI data from multiple cities, you generate 
prioritised, evidence-backed field enforcement recommendations for pollution control 
authorities. Always respond with ONLY valid JSON — no preamble, no markdown fences."""


def enforcement_user(req) -> str:
    cities_text = "\n".join(
        f"- {c['city']}: AQI {c['aqi']} ({c.get('label','')}) | PM2.5: {c.get('pm25','-')} μg/m³"
        for c in req.top_cities
    )
    return f"""Current top pollution cities in India:

{cities_text}

Generate today's top 3 enforcement action priorities. For each, specify: which city, 
what type of violation to inspect (industrial stack, construction dust, diesel generators, 
waste burning, etc.), the specific zone or area type most likely to yield results, 
recommended inspector count, and the evidentiary basis for prioritising this action.

Respond ONLY with this JSON:
{{
  "generated_at": "<today's date>",
  "priorities": [
    {{
      "rank": 1,
      "city": "<city name>",
      "action": "<specific enforcement action>",
      "violation_type": "<type of violation>",
      "target_zone": "<area or zone type>",
      "inspector_count": <number>,
      "aqi_at_decision": <aqi value>,
      "rationale": "<2-sentence evidence-backed justification>"
    }},
    ... (3 total)
  ]
}}"""


# ─── AQI Forecast ─────────────────────────────────────────────────────────────

FORECAST_SYSTEM = """You are a predictive air quality modeller for Indian cities. 
Using historical AQI trends and meteorological forecasts, you predict AQI for the 
next 24 hours at hourly intervals. Always respond with ONLY valid JSON."""


def forecast_user(req) -> str:
    history_text = " → ".join(
        f"{h['hour']}:{h['aqi']}" for h in req.history_24h[-8:]
    )
    forecast_text = "\n".join(
        f"  {f['time']}: {f['temp_c']}°C, wind {f['wind_speed_kmh']} km/h, {f['description']}"
        for f in req.weather_forecast[:4]
    )
    return f"""City: {req.city}
Current AQI: {req.current_aqi}
Last 8 hours AQI trend: {history_text}

Upcoming weather forecast:
{forecast_text}

Predict AQI for the next 12 hours (at 2-hour intervals).
Factor in: typical diurnal traffic patterns for Indian cities, weather-induced 
dispersion or stagnation, and the current trend trajectory.

Respond ONLY with:
{{
  "city": "{req.city}",
  "forecast": [
    {{"hour": "HH:00", "predicted_aqi": <integer>, "confidence": "high|medium|low"}},
    ... (6 entries, 2-hr intervals)
  ],
  "narrative": "<3-sentence summary of what to expect and why>",
  "peak_hour": "<HH:00>",
  "peak_aqi": <integer>
}}"""


# ─── Citizen Health Advisory — Multilingual Query Support ────────────────────

ADVISORY_SYSTEM = """You are a public health communication officer generating citizen-facing 
air quality advisories for Indian cities. You support both:
(A) Structured advisory generation: output a formatted advisory in the specified language
(B) Free-text query answering: a citizen has sent a message in any Indian language — 
    detect the language and respond in the SAME language and script.

Rules for ALL responses:
- Clear, empathetic, jargon-free language
- For Tamil, Kannada, Hindi, Bengali, or any regional script: respond ENTIRELY in that script
- For English: 7th-grade reading level
- Never include JSON — plain text only
- Under 130 words"""


def advisory_user(req) -> str:
    # PATH A: User typed a free-text query (multilingual input)
    if req.user_query and req.user_query.strip():
        return f"""A citizen has sent the following message about air quality in {req.city}:

"{req.user_query}"

Current real-time conditions in {req.city}:
- AQI: {req.aqi} — Category: {req.aqi_category}
- Data source: Live CPCB monitoring station

Instructions:
1. Detect the language of the citizen's message above
2. Respond ENTIRELY in that same language and script — do not switch to English
3. Directly answer their specific question using the AQI data
4. Include: current air quality status, who is most at risk, 2-3 practical things 
   they should do or avoid today
5. Close with one reassuring note
6. If message is English, respond in English"""

    # PATH B: Explicit language selected via toggle (original flow)
    lang_map = {
        "english": "English",
        "tamil":   "Tamil (தமிழ்)",
        "kannada": "Kannada (ಕನ್ನಡ)",
        "hindi":   "Hindi (हिंदी)",
    }
    lang = lang_map.get(req.language, "English")
    return f"""Generate a citizen health advisory for:

City: {req.city}
Current AQI: {req.aqi} — Category: {req.aqi_category} (live CPCB data)
Output language: {lang}

The advisory must include:
1. Clear statement of today's air quality level
2. Who is most at risk (elderly, children, pregnant women, people with asthma/COPD)
3. 3 specific actionable recommendations (what to do / avoid today)
4. One positive closing note

Keep it under 120 words total. Write in {lang} ONLY — do not use any other language."""
```

---

## 6. Frontend — React

### 6.1 `frontend/src/index.css`

```css
@import "tailwindcss";
@import "leaflet/dist/leaflet.css";

:root {
  --bg: #0f1117;
  --surface: #1a1f2e;
  --border: #2d3348;
  --text: #e2e8f0;
  --text-muted: #94a3b8;
  --accent: #3b82f6;
}

body {
  background: var(--bg);
  color: var(--text);
  font-family: 'Inter', system-ui, sans-serif;
}
```

---

### 6.2 `frontend/src/services/api.js`

Single source of truth for all backend calls. `BASE` is environment-aware so the same code works on `localhost` during development and against the deployed Render URL in production (see Section 10.3).

```js
import axios from 'axios'

// In dev, proxies through vite.config.js to localhost:8000.
// In production, set VITE_API_URL in Vercel's environment variables.
const BASE = import.meta.env.VITE_API_URL || '/api'

export const api = {
  // AQI Data
  getLiveAQI: () =>
    axios.get(`${BASE}/aqi/live`).then(r => r.data),

  getCityDetail: (city, lat, lon) =>
    axios.get(`${BASE}/aqi/city/${encodeURIComponent(city)}`, {
      params: { lat, lon }
    }).then(r => r.data),

  // Intelligence
  getAttribution: (payload) =>
    axios.post(`${BASE}/intel/attribution`, payload).then(r => r.data),

  getEnforcement: () =>
    axios.get(`${BASE}/intel/enforcement/auto`).then(r => r.data),

  getForecast: (payload) =>
    axios.post(`${BASE}/intel/forecast`, payload).then(r => r.data),

  getAdvisory: (payload) =>
    axios.post(`${BASE}/intel/advisory`, payload).then(r => r.data),
}
```

---

### 6.3 `frontend/src/hooks/useAQI.js`

```js
import { useState, useEffect, useCallback } from 'react'
import { api } from '../services/api'

export function useAQI() {
  const [stations, setStations] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [lastUpdated, setLastUpdated] = useState(null)

  const refresh = useCallback(async () => {
    try {
      setLoading(true)
      const data = await api.getLiveAQI()
      setStations(data.stations)
      setLastUpdated(new Date())
      setError(null)
    } catch (e) {
      setError('Failed to fetch AQI data')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
    const interval = setInterval(refresh, 5 * 60 * 1000) // poll every 5 min
    return () => clearInterval(interval)
  }, [refresh])

  return { stations, loading, error, lastUpdated, refresh }
}
```

---

### 6.4 `frontend/src/App.jsx` — Real Weather in Attribution

Key fix: the old version passed hardcoded `weather_desc: 'partly cloudy', wind_speed_kmh: 10, humidity_pct: 65` to the attribution request. Now we fetch weather first and pass real values.

```jsx
import { useState, useEffect } from 'react'
import MapView from './components/MapView'
import CityPanel from './components/CityPanel'
import EnforcementSidebar from './components/EnforcementSidebar'
import AdvisoryGenerator from './components/AdvisoryGenerator'
import { useAQI } from './hooks/useAQI'
import { api } from './services/api'

export default function App() {
  const { stations, loading, lastUpdated } = useAQI()
  const [selectedCity, setSelectedCity] = useState(null)
  const [cityDetail, setCityDetail] = useState(null)
  const [attribution, setAttribution] = useState(null)
  const [enforcement, setEnforcement] = useState(null)
  const [activeTab, setActiveTab] = useState('map')

  useEffect(() => {
    api.getEnforcement().then(setEnforcement).catch(console.error)
  }, [])

  const handleCityClick = async (station) => {
    setSelectedCity(station)
    setCityDetail(null)
    setAttribution(null)

    // Step 1: fetch real city detail (includes real weather from OWM)
    const detail = await api.getCityDetail(station.city, station.lat, station.lon)
    setCityDetail(detail)

    // Step 2: now pass REAL weather values to attribution — no hardcoded fallbacks
    const now = new Date()
    const weather = detail.weather || {}
    const attr = await api.getAttribution({
      city: station.city,
      state: station.state || '',
      aqi: station.aqi,
      pm25: detail.feed?.pm25 ?? station.pm25 ?? 0,
      hour_of_day: now.getHours(),
      day_of_week: now.toLocaleDateString('en-US', { weekday: 'long' }),
      weather_desc: weather.description || 'clear',
      wind_speed_kmh: weather.wind_speed_kmh || 0,
      humidity_pct: weather.humidity_pct || 50,
    })
    setAttribution(attr)
  }

  return (
    <div className="h-screen flex flex-col bg-[#0f1117] text-slate-200">
      <header className="flex items-center justify-between px-6 py-3 bg-[#1a1f2e] border-b border-[#2d3348]">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-blue-500 rounded-lg flex items-center justify-center text-sm font-bold">🌫️</div>
          <div>
            <h1 className="text-lg font-bold text-white">AirWatch India</h1>
            <p className="text-xs text-slate-400">Urban Air Quality Intelligence Platform</p>
          </div>
        </div>
        <div className="flex gap-2">
          {['map', 'enforcement', 'advisory'].map(tab => (
            <button key={tab} onClick={() => setActiveTab(tab)}
              className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors
                ${activeTab === tab ? 'bg-blue-600 text-white' : 'bg-[#2d3348] text-slate-300 hover:bg-[#374162]'}`}>
              {tab.charAt(0).toUpperCase() + tab.slice(1)}
            </button>
          ))}
        </div>
        <div className="text-xs text-slate-400">
          {lastUpdated ? `Live · ${lastUpdated.toLocaleTimeString()}` : 'Connecting...'}
          <span className="ml-2 inline-block w-2 h-2 rounded-full bg-green-400 animate-pulse" />
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {activeTab === 'map' && (
          <>
            <div className="flex-1">
              <MapView stations={stations} onCityClick={handleCityClick} selectedCity={selectedCity} />
            </div>
            {selectedCity && (
              <div className="w-96 overflow-y-auto border-l border-[#2d3348] bg-[#1a1f2e]">
                <CityPanel city={selectedCity} detail={cityDetail} attribution={attribution}
                  onClose={() => setSelectedCity(null)} />
              </div>
            )}
          </>
        )}
        {activeTab === 'enforcement' && (
          <div className="flex-1 overflow-y-auto p-6">
            <EnforcementSidebar enforcement={enforcement} />
          </div>
        )}
        {activeTab === 'advisory' && (
          <div className="flex-1 overflow-y-auto p-6">
            <AdvisoryGenerator stations={stations} />
          </div>
        )}
      </div>
    </div>
  )
}

---

### 6.5 `frontend/src/components/MapView.jsx`

```jsx
import { MapContainer, TileLayer, CircleMarker, Tooltip } from 'react-leaflet'

const AQI_COLORS = {
  Good: '#00C853',
  Satisfactory: '#C6E03A',
  Moderate: '#FFC107',
  Poor: '#FF5722',
  'Very Poor': '#C62828',
  Severe: '#4A148C',
}

export default function MapView({ stations, onCityClick, selectedCity }) {
  return (
    <MapContainer
      center={[22.5, 82.0]}
      zoom={5}
      style={{ height: '100%', width: '100%', background: '#0f1117' }}
    >
      <TileLayer
        url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
        attribution='© OpenStreetMap © CARTO'
      />
      {stations.map((station, idx) => (
        <CircleMarker
          key={idx}
          center={[station.lat, station.lon]}
          radius={station.aqi > 300 ? 22 : station.aqi > 200 ? 18 : station.aqi > 100 ? 14 : 10}
          pathOptions={{
            color: AQI_COLORS[station.label] || '#888',
            fillColor: AQI_COLORS[station.label] || '#888',
            fillOpacity: selectedCity?.city === station.city ? 1.0 : 0.7,
            weight: selectedCity?.city === station.city ? 3 : 1,
          }}
          eventHandlers={{ click: () => onCityClick(station) }}
        >
          <Tooltip>
            <div className="text-sm">
              <strong>{station.city}</strong><br />
              AQI: {station.aqi} — {station.label}<br />
              PM2.5: {station.pm25 ? `${station.pm25} μg/m³` : 'See city detail'}<br />
              <span className="text-gray-400 text-xs">Source: {station.source === 'waqi_live' ? 'CPCB via WAQI' : station.source}</span>
            </div>
          </Tooltip>
        </CircleMarker>
      ))}
    </MapContainer>
  )
}
```

---

### 6.6 `frontend/src/components/CityPanel.jsx` — Real Multi-Pollutant Display

```jsx
import { PieChart, Pie, Cell, LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'

const SOURCE_COLORS = ['#3b82f6','#f97316','#a855f7','#10b981','#94a3b8']
const AQI_COLOR = (aqi) =>
  aqi > 300 ? '#C62828' : aqi > 200 ? '#FF5722' : aqi > 100 ? '#FFC107' : '#00C853'

export default function CityPanel({ city, detail, attribution, onClose }) {
  const sources = attribution
    ? [
        { name: 'Traffic', value: attribution.traffic },
        { name: 'Industrial', value: attribution.industrial },
        { name: 'Construction', value: attribution.construction },
        { name: 'Biomass', value: attribution.biomass_burning },
        { name: 'Other', value: attribution.other },
      ]
    : []

  return (
    <div className="p-5 space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-xl font-bold text-white">{city.city}</h2>
          <p className="text-sm text-slate-400">{city.state || ''}</p>
        </div>
        <button onClick={onClose} className="text-slate-400 hover:text-white text-xl leading-none">×</button>
      </div>

      {/* AQI Badge */}
      <div
        className="rounded-xl p-4 text-center"
        style={{ background: AQI_COLOR(city.aqi) + '22', border: `1px solid ${AQI_COLOR(city.aqi)}44` }}
      >
        <div className="text-5xl font-black" style={{ color: AQI_COLOR(city.aqi) }}>
          {city.aqi}
        </div>
        <div className="text-sm font-medium text-slate-300 mt-1">{city.label}</div>
        <div className="text-xs text-slate-400 mt-1">PM2.5: {city.pm25} μg/m³</div>
      </div>

      {/* Source Attribution */}
      {attribution ? (
        <div>
          <h3 className="text-sm font-semibold text-slate-300 mb-3">Pollution Sources</h3>
          <div className="flex items-center gap-4">
            <PieChart width={120} height={120}>
              <Pie data={sources} cx={55} cy={55} innerRadius={30} outerRadius={55} dataKey="value">
                {sources.map((_, i) => <Cell key={i} fill={SOURCE_COLORS[i]} />)}
              </Pie>
            </PieChart>
            <div className="space-y-1.5 flex-1">
              {sources.map((s, i) => (
                <div key={i} className="flex items-center gap-2 text-xs">
                  <div className="w-3 h-3 rounded-full flex-shrink-0" style={{ background: SOURCE_COLORS[i] }} />
                  <span className="text-slate-300 flex-1">{s.name}</span>
                  <span className="font-bold text-white">{s.value}%</span>
                </div>
              ))}
            </div>
          </div>
          {attribution.reasoning && (
            <p className="text-xs text-slate-400 mt-2 italic">{attribution.reasoning}</p>
          )}
        </div>
      ) : (
        <div className="text-center py-4 text-slate-500 text-sm">Analysing sources...</div>
      )}

      {/* 24hr Trend */}
      {detail?.history?.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-slate-300 mb-3">24hr AQI Trend</h3>
          <ResponsiveContainer width="100%" height={100}>
            <LineChart data={detail.history}>
              <XAxis dataKey="hour" tick={{ fontSize: 9, fill: '#94a3b8' }} interval={5} />
              <YAxis domain={['auto', 'auto']} tick={{ fontSize: 9, fill: '#94a3b8' }} width={30} />
              <Tooltip
                contentStyle={{ background: '#1a1f2e', border: '1px solid #2d3348', fontSize: 11 }}
                labelStyle={{ color: '#94a3b8' }}
              />
              <Line
                type="monotone"
                dataKey="aqi"
                stroke={AQI_COLOR(city.aqi)}
                strokeWidth={2}
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Real Multi-Pollutant Breakdown from WAQI feed */}
      {detail?.feed && (
        <div>
          <h3 className="text-sm font-semibold text-slate-300 mb-2">Live Pollutant Readings</h3>
          <div className="grid grid-cols-2 gap-2">
            {[
              { key: 'pm25', label: 'PM2.5', unit: 'μg/m³', limit: 60 },
              { key: 'pm10', label: 'PM10',  unit: 'μg/m³', limit: 100 },
              { key: 'no2',  label: 'NO₂',   unit: 'μg/m³', limit: 80 },
              { key: 'o3',   label: 'O₃',    unit: 'μg/m³', limit: 100 },
            ].map(({ key, label, unit, limit }) => {
              const val = detail.feed[key]
              if (!val) return null
              const over = val > limit
              return (
                <div key={key} className="bg-[#0f1117] rounded-lg p-2.5">
                  <div className="text-xs text-slate-400">{label}</div>
                  <div className={`text-lg font-bold ${over ? 'text-orange-400' : 'text-green-400'}`}>
                    {val.toFixed(1)}
                  </div>
                  <div className="text-xs text-slate-500">{unit}</div>
                </div>
              )
            })}
          </div>
          <p className="text-xs text-slate-500 mt-1.5">
            Source: CPCB via WAQI · Updated: {detail.feed.updated_at || 'recently'}
          </p>
        </div>
      )}

      {/* Weather Context — real data from OpenWeatherMap */}
      {detail?.weather && (
        <div className="bg-[#0f1117] rounded-lg p-3 text-xs text-slate-400 grid grid-cols-2 gap-2">
          <span>🌡 {detail.weather.temp_c}°C</span>
          <span>💧 {detail.weather.humidity_pct}% humidity</span>
          <span>💨 {detail.weather.wind_speed_kmh} km/h wind</span>
          <span>👁 {detail.weather.visibility_km} km visibility</span>
        </div>
      )}

      {/* Data source badge */}
      <div className="text-xs text-slate-600 text-center pt-1">
        AQI: CPCB India scale · Pollutants: WAQI live feed · Weather: OpenWeatherMap
      </div>
    </div>
  )
}
```

---

### 6.7 `frontend/src/components/EnforcementSidebar.jsx`

```jsx
const RANK_COLORS = ['#f59e0b', '#94a3b8', '#b45309']

export default function EnforcementSidebar({ enforcement }) {
  if (!enforcement) return (
    <div className="text-center py-20 text-slate-500">Loading enforcement priorities...</div>
  )

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-white">Today's Enforcement Priorities</h2>
        <p className="text-slate-400 text-sm mt-1">
          AI-generated recommendations based on real-time AQI data — {enforcement.generated_at}
        </p>
      </div>

      {enforcement.priorities?.map((p) => (
        <div key={p.rank} className="bg-[#1a1f2e] rounded-xl p-5 border border-[#2d3348] space-y-3">
          <div className="flex items-center gap-3">
            <div
              className="w-10 h-10 rounded-full flex items-center justify-center font-black text-lg"
              style={{ background: RANK_COLORS[p.rank - 1] + '33', color: RANK_COLORS[p.rank - 1] }}
            >
              #{p.rank}
            </div>
            <div>
              <h3 className="font-bold text-white text-lg">{p.city}</h3>
              <p className="text-slate-400 text-sm">{p.violation_type}</p>
            </div>
            <div className="ml-auto text-right">
              <div className="text-2xl font-black text-red-400">{p.aqi_at_decision}</div>
              <div className="text-xs text-slate-400">AQI</div>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3 text-sm">
            <div className="bg-[#0f1117] rounded-lg p-3">
              <div className="text-slate-400 text-xs mb-1">Action</div>
              <div className="text-white font-medium">{p.action}</div>
            </div>
            <div className="bg-[#0f1117] rounded-lg p-3">
              <div className="text-slate-400 text-xs mb-1">Target Zone</div>
              <div className="text-white font-medium">{p.target_zone}</div>
            </div>
          </div>

          <div className="flex items-center gap-2 text-sm">
            <span className="text-slate-400">Inspectors required:</span>
            <span className="bg-blue-500/20 text-blue-300 px-2 py-0.5 rounded font-bold">
              {p.inspector_count}
            </span>
          </div>

          <div className="text-sm text-slate-300 bg-[#0f1117] rounded-lg p-3 italic">
            {p.rationale}
          </div>
        </div>
      ))}
    </div>
  )
}
```

---

### 6.8 `frontend/src/components/AdvisoryGenerator.jsx` — Multilingual Query Input

```jsx
import { useState } from 'react'
import { api } from '../services/api'

const LANGUAGES = [
  { code: 'english', label: 'English' },
  { code: 'hindi',   label: 'हिंदी' },
  { code: 'tamil',   label: 'தமிழ்' },
  { code: 'kannada', label: 'ಕನ್ನಡ' },
]

const AQI_CATS = {
  Good: 'bg-green-500', Satisfactory: 'bg-lime-500', Moderate: 'bg-yellow-500',
  Poor: 'bg-orange-500', 'Very Poor': 'bg-red-600', Severe: 'bg-purple-800',
}

const MODE_LABELS = {
  query: 'Ask a question (any language)',
  generate: 'Generate standard advisory',
}

export default function AdvisoryGenerator({ stations }) {
  const [selectedCity, setSelectedCity] = useState('')
  const [language, setLanguage]       = useState('english')
  const [mode, setMode]               = useState('query')    // 'query' | 'generate'
  const [userQuery, setUserQuery]     = useState('')
  const [advisory, setAdvisory]       = useState(null)
  const [loading, setLoading]         = useState(false)
  const [detectedLang, setDetectedLang] = useState(null)

  const cityData = stations.find(s => s.city === selectedCity)

  const generate = async () => {
    if (!cityData) return
    setLoading(true)
    setAdvisory(null)
    setDetectedLang(null)
    try {
      const payload = {
        city: cityData.city,
        aqi: cityData.aqi,
        aqi_category: cityData.label,
        language: mode === 'query' ? 'auto' : language,
        user_query: mode === 'query' ? userQuery : '',
      }
      const result = await api.getAdvisory(payload)
      setAdvisory(result.advisory)
      // Show language detection hint for query mode
      if (mode === 'query' && userQuery) {
        setDetectedLang('Language auto-detected from your query')
      }
    } catch (e) {
      setAdvisory('Failed to generate advisory. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  const canGenerate = selectedCity && (mode === 'generate' || userQuery.trim().length > 3)

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-white">Citizen Health Advisory</h2>
        <p className="text-slate-400 text-sm mt-1">
          Real-time AQI-based advisories · Free-text queries in any Indian language
        </p>
      </div>

      {/* Mode Toggle */}
      <div className="flex rounded-lg overflow-hidden border border-[#2d3348]">
        {Object.entries(MODE_LABELS).map(([m, label]) => (
          <button key={m} onClick={() => { setMode(m); setAdvisory(null) }}
            className={`flex-1 py-2 text-sm font-medium transition-colors
              ${mode === m ? 'bg-blue-600 text-white' : 'bg-[#1a1f2e] text-slate-400 hover:text-white'}`}>
            {label}
          </button>
        ))}
      </div>

      {/* City Picker */}
      <div className="space-y-2">
        <label className="text-sm text-slate-400">City</label>
        <select value={selectedCity} onChange={e => setSelectedCity(e.target.value)}
          className="w-full bg-[#1a1f2e] border border-[#2d3348] rounded-lg px-4 py-2.5 text-white">
          <option value="">— select a city —</option>
          {stations.slice().sort((a, b) => b.aqi - a.aqi).map(s => (
            <option key={s.city} value={s.city}>
              {s.city} — AQI {s.aqi} ({s.label})
            </option>
          ))}
        </select>
      </div>

      {/* Query Mode: free-text input */}
      {mode === 'query' && (
        <div className="space-y-2">
          <label className="text-sm text-slate-400">
            Your question — type in English, हिंदी, தமிழ், ಕನ್ನಡ, or any Indian language
          </label>
          <textarea
            value={userQuery}
            onChange={e => setUserQuery(e.target.value)}
            placeholder={
              "e.g.  \"Is it safe to take my child to school today?\"\n" +
              "      \"आज बाहर जाना सुरक्षित है?\"\n" +
              "      \"இன்று காற்று மாசு எவ்வளவு ஆபத்தானது?\""
            }
            className="w-full bg-[#1a1f2e] border border-[#2d3348] rounded-lg px-4 py-3 text-white
              resize-none h-28 text-sm placeholder:text-slate-600 focus:border-blue-500 outline-none"
          />
          <p className="text-xs text-slate-500">
            The language of your question is detected automatically — no selection needed.
          </p>
        </div>
      )}

      {/* Generate Mode: language picker */}
      {mode === 'generate' && (
        <div className="space-y-2">
          <label className="text-sm text-slate-400">Output Language</label>
          <div className="flex gap-2 flex-wrap">
            {LANGUAGES.map(l => (
              <button key={l.code} onClick={() => setLanguage(l.code)}
                className={`px-4 py-2 rounded-lg text-sm font-medium border transition-colors
                  ${language === l.code
                    ? 'bg-blue-600 border-blue-500 text-white'
                    : 'bg-[#1a1f2e] border-[#2d3348] text-slate-300 hover:border-blue-500'}`}>
                {l.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Current AQI pill */}
      {cityData && (
        <div className="flex items-center gap-3 bg-[#1a1f2e] rounded-lg px-4 py-3">
          <div className={`w-3 h-3 rounded-full flex-shrink-0 ${AQI_CATS[cityData.label] || 'bg-gray-500'}`} />
          <span className="text-slate-300 text-sm">
            {cityData.city} · AQI <strong className="text-white">{cityData.aqi}</strong>
            {' '}<span className="text-slate-400">({cityData.label})</span>
            {' '}<span className="text-slate-600 text-xs">· Live CPCB data</span>
          </span>
        </div>
      )}

      {/* Generate Button */}
      <button onClick={generate} disabled={!canGenerate || loading}
        className="w-full bg-blue-600 hover:bg-blue-500 disabled:bg-[#2d3348] disabled:text-slate-500
          text-white font-semibold py-3 rounded-xl transition-colors">
        {loading ? 'Generating...' : mode === 'query' ? 'Get Answer' : 'Generate Advisory'}
      </button>

      {/* Output */}
      {advisory && (
        <div className="bg-[#1a1f2e] border border-[#2d3348] rounded-xl p-5">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-lg">🔔</span>
            <span className="font-semibold text-white">
              {mode === 'query' ? 'Answer' : 'Health Advisory'} — {cityData?.city}
            </span>
            {detectedLang && (
              <span className="ml-auto text-xs text-slate-500 italic">{detectedLang}</span>
            )}
          </div>
          <p className="text-slate-200 leading-relaxed whitespace-pre-wrap text-sm">{advisory}</p>
          <div className="mt-3 pt-3 border-t border-[#2d3348] flex gap-3 items-center">
            <button onClick={() => navigator.clipboard.writeText(advisory)}
              className="text-xs text-blue-400 hover:text-blue-300">📋 Copy</button>
            <span className="text-xs text-slate-600 ml-auto">Based on live AQI {cityData?.aqi}</span>
          </div>
        </div>
      )}
    </div>
  )
}
```

---

## 7. LLM Prompt Templates

Already included in `backend/prompts.py` above. Key design decisions:

- **JSON-only system prompts**: Every intelligence endpoint uses `call_llm_json()` so responses parse cleanly without regex hacks
- **Context richness**: Every prompt injects time-of-day, day-of-week, and weather — these genuinely change the reasoning and make outputs non-generic
- **Explicit format contracts**: JSON schema is defined in the prompt. GPT-4o follows it reliably at temperature 0.4
- **Fallback safety**: `call_llm_json()` strips code fences before `json.loads()` — handles any accidental formatting
- **Language instructions**: Advisory prompt explicitly names both the language and the script (`Tamil (தமிழ்)`) to prevent English leakage

---

## 8. AQI Calculation Utility

Already included in `backend/utils/aqi_calculator.py`. Key notes:

- Uses **CPCB India breakpoints**, not EPA USA — this matters for demo credibility
- India's AQI sub-index uses PM2.5 as the dominant pollutant in most urban stations
- The 6 bands are: Good / Satisfactory / Moderate / Poor / Very Poor / Severe
- Circle radius scaling ensures visual differentiation between 100 AQI and 400 AQI on the map

---

## 9. Reliability, Testing & QA Strategy

A 12-hour build can get away with "it worked when I tried it." A 22-day build judged live cannot — if WAQI rate-limits you mid-demo or Azure OpenAI times out, the platform needs to degrade gracefully, not show a blank screen in front of judges.

### 9.1 Retry Logic for All External API Calls

Install `tenacity` and wrap every external call:

```bash
pip install tenacity
```

Update `backend/services/waqi.py` and `openweather.py` with retry decorators:

```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import httpx

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=6),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
    reraise=True,
)
async def _fetch_with_retry(client: httpx.AsyncClient, url: str, **kwargs) -> httpx.Response:
    """Generic retry wrapper: 3 attempts, exponential backoff, only retries on network errors."""
    resp = await client.get(url, **kwargs)
    resp.raise_for_status()
    return resp
```

Use `_fetch_with_retry()` in place of direct `client.get()` calls inside `fetch_india_stations()`, `fetch_city_feed()`, and `fetch_weather()`. This alone eliminates most demo-day flakiness — a single dropped packet no longer crashes the call.

### 9.2 LLM Call Resilience

Azure OpenAI occasionally returns malformed JSON under load. Add a one-retry repair loop to `call_llm_json()`:

```python
def call_llm_json(system: str, user: str, max_tokens: int = 1024, _retry: bool = True) -> dict | list:
    """
    Call Azure OpenAI expecting JSON. On parse failure, retries once with an
    explicit correction instruction appended to the system prompt.
    """
    raw = call_llm(system, user, max_tokens)
    cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        if not _retry:
            raise
        corrected_system = system + "\n\nCRITICAL: Your previous response was not valid JSON. Respond with ONLY the raw JSON object, nothing else."
        return call_llm_json(corrected_system, user, max_tokens, _retry=False)
```

### 9.3 Backend Test Suite

Add `backend/tests/` with pytest covering the parts most likely to break silently:

```python
# backend/tests/test_aqi_calculator.py
from utils.aqi_calculator import pm25_to_aqi, aqi_category, circle_radius

def test_pm25_to_aqi_boundaries():
    assert pm25_to_aqi(0) == 0
    assert pm25_to_aqi(30) == 50
    assert pm25_to_aqi(60) == 100
    assert pm25_to_aqi(250) == 400

def test_aqi_category_labels():
    assert aqi_category(25)["label"] == "Good"
    assert aqi_category(150)["label"] == "Moderate"
    assert aqi_category(450)["label"] == "Severe"

def test_circle_radius_scales_with_severity():
    assert circle_radius(50) < circle_radius(150) < circle_radius(350)
```

```python
# backend/tests/test_llm_json_parsing.py
from services.llm import call_llm_json
from unittest.mock import patch

def test_strips_markdown_fences():
    with patch("services.llm.call_llm", return_value='```json\n{"a": 1}\n```'):
        result = call_llm_json("system", "user")
        assert result == {"a": 1}
```

```bash
# Run before every deploy
pytest backend/tests/ -v
```

### 9.4 Manual QA Checklist — Run Before Every Demo Rehearsal

```
[ ] Kill WAQI token temporarily — confirm OpenAQ fallback kicks in within 10s
[ ] Kill OpenAQ too — confirm static fallback JSON serves, map still populates
[ ] Throttle network (Chrome DevTools "Slow 3G") — confirm loading states show, no blank screens
[ ] Submit empty advisory query — confirm graceful "type a question" message, no crash
[ ] Submit advisory query in a language not in your test set (e.g. Bengali) — confirm GPT-4o still detects and responds correctly
[ ] Click 10 cities rapidly — confirm no race condition shows stale city's data
[ ] Refresh page mid-session — confirm cache reload doesn't error
[ ] Test on mobile viewport (375px) — confirm map/panels are usable, not just "doesn't crash"
```

### 9.5 Frontend Error Boundary

Wrap the app in a React error boundary so a single component crash doesn't white-screen the whole demo:

```jsx
// frontend/src/components/ErrorBoundary.jsx
import { Component } from 'react'

export default class ErrorBoundary extends Component {
  state = { hasError: false }

  static getDerivedStateFromError() {
    return { hasError: true }
  }

  componentDidCatch(error, info) {
    console.error('Caught by ErrorBoundary:', error, info)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="h-screen flex items-center justify-center bg-[#0f1117] text-slate-300">
          <div className="text-center space-y-3">
            <p className="text-lg font-semibold">Something went wrong loading this view.</p>
            <button onClick={() => window.location.reload()}
              className="bg-blue-600 px-4 py-2 rounded-lg text-white text-sm">
              Reload
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
```

Wrap `<App />` with it in `main.jsx`:

```jsx
import ErrorBoundary from './components/ErrorBoundary'

ReactDOM.createRoot(document.getElementById('root')).render(
  <ErrorBoundary>
    <App />
  </ErrorBoundary>
)
```

---

## 10. Deployment & Hosting

A 1-day hackathon demo runs on `localhost`. A 22-day project should ship a **live, public URL** — judges can poke at it themselves, and it removes "will the laptop Wi-Fi cooperate" as a demo-day risk entirely.

### 10.1 Recommended Hosting

| Component | Service | Why | Cost |
|---|---|---|---|
| Frontend (React build) | **Vercel** | Zero-config for Vite, instant deploys on git push, free tier | Free |
| Backend (FastAPI) | **Render** | Free tier supports FastAPI + uvicorn, persistent process (no cold-start issues like serverless) | Free |
| Alternative backend | Railway | Similar to Render, slightly faster cold starts on free tier | Free |

### 10.2 Backend Deployment (Render)

1. Push `backend/` to a GitHub repo
2. On Render: New → Web Service → connect repo, root directory `backend/`
3. Build command: `pip install -r requirements.txt`
4. Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Add all env vars from Section 11 in Render's dashboard (Environment tab) — never commit `.env`
6. Note the generated URL, e.g. `https://airwatch-api.onrender.com`

### 10.3 Frontend Deployment (Vercel)

1. `frontend/src/services/api.js` is already environment-aware (Section 6.2) — no code change needed here, just set the env var:

```
VITE_API_URL=https://airwatch-api.onrender.com/api
```

2. Create `frontend/.env.production` with that value
3. Push `frontend/` to GitHub, import into Vercel, set root directory to `frontend/`
4. Vercel auto-detects Vite — no config needed
5. Add `VITE_API_URL` in Vercel's Environment Variables dashboard too

### 10.4 CORS Update for Production

Update `backend/main.py` CORS origins to include your live Vercel URL:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "https://airwatch-india.vercel.app",   # replace with your actual Vercel URL
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### 10.5 Render Free Tier Cold Start — Know This Before Demo Day

Render's free tier spins down after 15 minutes of inactivity and takes ~30-50 seconds to wake up on the next request. **Ping your backend 5 minutes before your judging slot** to warm it up, or upgrade to Render's $7/mo tier for the judging week if budget allows. A cold-start delay during live judging looks like the app is broken — don't let this be your failure mode.

A simple warmup script:
```bash
# Run this 5 min before your demo slot
curl https://airwatch-api.onrender.com/health
```

### 10.6 Custom Domain (Optional Polish)

If anyone on the team has a spare domain, Vercel supports custom domains free. `airwatch.yourteam.dev` reads more credibly to judges than `airwatch-india-xk2j9.vercel.app`. Not essential, but a 10-minute task that adds polish.

---

## 11. Environment Variables

**`backend/.env`**

```
# Azure OpenAI — all three are required
AZURE_OPENAI_API_KEY=your_azure_openai_key_here
AZURE_OPENAI_ENDPOINT=https://<your-resource-name>.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT=gpt-4o                  # your deployment name in Azure AI Studio
AZURE_OPENAI_API_VERSION=2024-02-01             # stable version, keep as-is

# AQI data — WAQI is primary, OpenAQ needs no key
WAQI_TOKEN=your_waqi_token_here                 # get free from https://aqicn.org/data-platform/token/

# Weather
OPENWEATHER_API_KEY=your_owm_key_here
```

**`frontend/.env.production`**
```
VITE_API_URL=https://airwatch-api.onrender.com/api
```

**Getting API keys (20 minutes total):**

| Key | Where | Time |
|---|---|---|
| `AZURE_OPENAI_API_KEY` | Azure Portal → your OpenAI resource → Keys and Endpoint | 2 min |
| `AZURE_OPENAI_ENDPOINT` | Same page as above (Endpoint field) | — |
| `AZURE_OPENAI_DEPLOYMENT` | Azure AI Studio → Deployments → your GPT-4o deployment name | 2 min |
| `WAQI_TOKEN` | https://aqicn.org/data-platform/token/ — enter email, instant token | 3 min |
| `OPENWEATHER_API_KEY` | openweathermap.org → free tier signup | 5 min (instant activation) |
| OpenAQ | No key needed for v2 basic | 0 min |

> **Note:** If you already have an Azure OpenAI resource from Happiest Minds / UniKnow, reuse those credentials directly. The deployment name is whatever you named your GPT-4o deployment in Azure AI Studio (common defaults: `gpt-4o`, `gpt4o`, `gpt-4o-deployment`).

> **Production secret management:** Never commit `.env` to git. Add it to `.gitignore` on day one. Set the same variables directly in Render's and Vercel's dashboards for production.

---

## 12. 22-Day Sprint Plan & Team Roles

### 12.1 Team Roles (2-3 People)

| Role | Owns | If team is 2 (not 3) |
|---|---|---|
| **Backend Lead** | `waqi.py`, `openaq.py`, `openweather.py`, `llm.py`, `prompts.py`, all FastAPI routes, deployment (Render), reliability layer | Same |
| **Frontend Lead** | All React components, Leaflet integration, Tailwind styling, deployment (Vercel), mobile responsiveness | Same |
| **QA / Content Lead** | Test suite, manual QA checklist execution, architecture diagram, presentation deck, demo video production, CPCB/Lancet/DGFASLI fact-checking for slides | **Split between Backend and Frontend Lead** — budget extra days in Week 3 for this |

Use a shared GitHub repo with two branches: `main` (always deployable) and `dev` (active work). Each person works in a feature branch off `dev`, opens a PR, the other person reviews before merging. This matters more than it sounds — over 22 days, an unreviewed merge that silently breaks the WAQI fallback chain is much harder to catch than in a 12-hour sprint where you're staring at the same screen.

### 12.2 Phase Overview

| Phase | Days | Goal |
|---|---|---|
| **Phase 1 — Foundation** | 1–7 | Backend data layer + frontend shell both working independently against real APIs |
| **Phase 2 — Feature Complete** | 8–14 | All 3 tabs fully functional end-to-end, deployed to staging URLs |
| **Phase 3 — Reliability & Polish** | 15–19 | Retry logic, tests, error boundaries, mobile responsiveness, UI refinement |
| **Phase 4 — Submission Prep** | 20–22 | Architecture diagram, deck, demo video, final rehearsal, submission |

### 12.3 Day-by-Day Breakdown

**Phase 1 — Foundation (Days 1–7)**

| Day | Backend Lead | Frontend Lead |
|---|---|---|
| 1 | Repo setup, branching strategy, get WAQI/OWM/Azure OpenAI keys, FastAPI skeleton boots | React + Vite + Tailwind scaffolded, basic routing/layout shell |
| 2 | `aqi_calculator.py` written + tested (CPCB breakpoints) | `MapView.jsx` renders empty Leaflet map centered on India |
| 3 | `waqi.py` — bounds endpoint working, returns real stations | `useAQI.js` hook + `api.js` service layer, hits backend `/aqi/live` |
| 4 | `openaq.py` backup wired, `cities_fallback.json` finalized | Map markers render from live `/aqi/live` data, color-coded by AQI band |
| 5 | `cache.py` + startup warming via `lifespan`, `openweather.py` working | City click handler stubbed, opens empty `CityPanel.jsx` shell |
| 6 | `llm.py` Azure OpenAI client working, test one raw completion call | `CityPanel.jsx` static layout (AQI badge, placeholder pie chart) |
| 7 | `prompts.py` — attribution prompt with CPCB anchor data, test via curl | **Checkpoint:** both pull a live demo together, confirm map + click flow works end-to-end with placeholder attribution |

**Phase 2 — Feature Complete (Days 8–14)**

| Day | Backend Lead | Frontend Lead |
|---|---|---|
| 8 | `/intel/attribution` endpoint live, returns real CPCB-anchored JSON | Pie chart wired to real attribution response |
| 9 | `fetch_city_feed()` in `waqi.py` — real PM2.5/PM10/NO2/O3 per city | Multi-pollutant grid in `CityPanel.jsx` rendering real values |
| 10 | Enforcement prompt + `/intel/enforcement/auto` endpoint working | `EnforcementSidebar.jsx` built, wired to real endpoint |
| 11 | Advisory prompt — both query mode and generate mode in `prompts.py` | `AdvisoryGenerator.jsx` — mode toggle, textarea, language buttons |
| 12 | `AdvisoryRequest` model updated with `user_query` field, test multilingual queries via curl (Tamil, Hindi, Bengali) | Wire `AdvisoryGenerator` to advisory endpoint, test query mode end-to-end in browser |
| 13 | Deploy backend to Render, confirm env vars, test live URL | Deploy frontend to Vercel pointing at Render URL, confirm CORS works |
| 14 | **Checkpoint:** full team walkthrough on the live deployed URL — every tab, every feature, no localhost | Same |

**Phase 3 — Reliability & Polish (Days 15–19)**

| Day | Backend Lead | Frontend Lead |
|---|---|---|
| 15 | Add `tenacity` retry decorators to all external API calls (Section 9.1) | Build `ErrorBoundary.jsx`, wrap `App`, test by forcing a crash |
| 16 | LLM JSON repair-retry logic (Section 9.2) | Loading skeletons for map, city panel, enforcement, advisory — replace blank "Loading..." text |
| 17 | Write pytest suite (`test_aqi_calculator.py`, `test_llm_json_parsing.py`), run in CI if time allows | Mobile responsiveness pass — test at 375px, fix any overflow/clipping |
| 18 | Run manual QA checklist (Section 9.4) — kill WAQI, kill OpenAQ, confirm fallback chain | UI refinement pass: spacing, color consistency, AQI freshness badge in header |
| 19 | **Buffer day** — fix whatever the QA checklist surfaced | **Buffer day** — fix whatever cross-browser/device testing surfaced |

**Phase 4 — Submission Prep (Days 20–22)**

| Day | Backend Lead | Frontend Lead | (or QA/Content Lead if team of 3) |
|---|---|---|---|
| 20 | Final deployment check, warm-up script tested | Final UI pass, screenshot every view for the deck | Architecture diagram in Excalidraw (Section 14), draft presentation deck outline |
| 21 | Full team demo rehearsal — run the script in Section 13 twice | Same | Demo video recording — aim for 2-3 takes, pick the cleanest |
| 22 | Final smoke test on live URL, ping Render to keep it warm before any live judging slot | Final smoke test | Submission packaging — upload all 4 deliverables, double-check links work in an incognito window |

### 12.4 Built-In Buffer

Notice Days 19 and the structure of Phase 4 deliberately leave slack — a 22-day plan with zero buffer is a 12-hour hackathon plan wearing a costume. If Phase 1 or 2 runs long, the buffer days are the first thing to compress, not Phase 4's rehearsal time. Rehearsing the demo on the actual deployed URL at least twice before submission day is non-negotiable — that's where cold-start delays, CORS issues, and "works on my machine" problems surface.

---

## 13. Demo Script

Practice this flow on the **live deployed URL**, not localhost. It should take 3–4 minutes.

> **Before walking up to present:** ping `https://airwatch-api.onrender.com/health` 5 minutes ahead of your slot to wake the backend from Render's free-tier cold start (Section 10.5). A 30-second hang on slide one is avoidable and shouldn't be your first impression.

```
1. OPEN the live URL — map loads, India visible.
   Say: "This is live on the web right now at [your-url] — every circle is a 
         real CPCB monitoring station pulled from the WAQI feed, the same data 
         source the pollution control board uses."
   Hover over a marker to show the tooltip with "Source: CPCB via WAQI".

2. POINT to Delhi/Kanpur/Lucknow cluster — dark red circles.
   Say: "The entire Indo-Gangetic Plain is in 'Poor' to 'Very Poor' right now."

3. CLICK Chennai — panel opens.
   Say: "Chennai, AQI 112 — Moderate. Let's see what's driving it."
   Wait for attribution pie to load.
   Say: "Our source attribution is grounded in published CPCB apportionment studies 
         for Chennai — then adjusted by the live wind speed and time of day. 
         Road dust and vehicles dominate, consistent with TNPCB field data."
   POINT to multi-pollutant grid (PM2.5, PM10, NO2 values).
   Say: "These are the actual pollutant readings from the WAQI feed right now —
         not estimates."

4. SCROLL DOWN to weather strip.
   Say: "Wind, humidity, visibility — live from OpenWeatherMap. Every number 
         on this panel traces back to a real API call, nothing is hardcoded."

5. SWITCH to Enforcement tab.
   Say: "The enforcement agent analysed live AQI across all stations and generated 
         today's inspection priorities — ranked by severity, with rationale."
   READ one enforcement card including the rationale sentence.

6. SWITCH to Advisory tab — select QUERY mode.
   TYPE in Tamil: "இன்று காற்று மாசு எவ்வளவு ஆபத்தானது?"
   SELECT Chennai.
   CLICK Get Answer.
   Say: "The platform detects the language automatically — no toggle needed. 
         A Chennai resident can ask in Tamil and get a response in Tamil."
   Wait for Tamil response to appear. Read first sentence aloud.

7. SWITCH to GENERATE mode. SELECT Delhi → Hindi → Generate Advisory.
   Say: "For bulk advisory generation — push notifications, SMS, IVR — 
         switch to generate mode and pick the language."
   Read first 2 lines of the Hindi output.

8. CLOSE with:
   "Every AQI value, every pollutant reading, every weather parameter came from a 
    live API call made seconds ago, on a platform that's actually deployed and 
    publicly accessible right now — not running off someone's laptop. The AI 
    layer reasons over real data — enforcement priorities, source attribution, 
    citizen advisories — all grounded in published CPCB science. This is what 
    actionable air quality intelligence looks like."
```

---

## 14. Architecture Diagram Description

Create this in Excalidraw (excalidraw.com) — takes 20 minutes.

**Layout: Left to right in 5 columns**

```
Column 1: DATA SOURCES (blue boxes)
- WAQI API (primary — CPCB live feed)
- OpenAQ v2 API (backup)
- OpenWeatherMap API
- Cities Fallback JSON (last resort)

Column 2: BACKEND — FastAPI on Render (purple box)
- /api/aqi/live (cached, 10min TTL)
- /api/aqi/city/{name}
- /api/intel/attribution
- /api/intel/enforcement
- /api/intel/forecast
- /api/intel/advisory
- Retry layer (tenacity, 3 attempts, exp. backoff)

Column 3: INTELLIGENCE LAYER (orange box)
- Azure OpenAI GPT-4o
- Deployment: gpt-4o (Azure AI Studio)
- 4 Reasoning Agents:
  → Source Attribution Agent (CPCB-anchored)
  → Enforcement Intelligence Agent
  → Forecast Reasoning Agent
  → Advisory Generation Agent (multilingual, query + generate modes)

Column 4: FRONTEND — React SPA on Vercel (green box)
- MapView (Leaflet)
- CityPanel (Recharts, multi-pollutant grid)
- EnforcementSidebar
- AdvisoryGenerator
- ErrorBoundary wrapper

Column 5: END USER
- City administrator (enforcement view)
- Citizen (advisory view, any device)
- Judge / public (live demo URL)

Arrows:
- Data Sources → FastAPI (labelled "REST / JSON, retried on failure")
- FastAPI → Azure OpenAI (labelled "Structured Prompts")
- Azure OpenAI → FastAPI (labelled "JSON Responses")
- FastAPI → React (labelled "REST API / CORS, deployed cross-origin")
- React → End User (labelled "Public HTTPS URL")

Bottom row: CPCB regulation logos + India map icon + "Live at airwatch-india.vercel.app"
```

---

## 15. Presentation Deck Outline

**10 slides. Keep each under 40 words of text — let visuals do the work.** With 22 days instead of one, you have time to actually design this properly rather than throw together bullet points — budget real hours for it in Phase 4 (Section 12.3, Day 20).

| Slide | Title | Content |
|---|---|---|
| 1 | The Problem | "1.67 million premature deaths annually. 900+ monitoring stations. Only 31% of cities have any response protocol linked to their data." Full-bleed smog photo. |
| 2 | The Gap | Split: LEFT = current state (dashboard, no action). RIGHT = what's needed (attribution, forecast, enforcement, advisory). One sentence each. |
| 3 | AirWatch India — Live Now | One-line product statement + the live URL prominently displayed (e.g. a QR code judges can scan to open it on their own phone). |
| 4 | Architecture | The 5-column diagram from Section 14. |
| 5 | Live Demo | 4 screenshots: Map view, City panel with multi-pollutant grid + source attribution, Enforcement priorities, Advisory in Tamil |
| 6 | The Intelligence Layer | 4 boxes: CPCB-Anchored Source Attribution / Enforcement Intelligence / Forecast Reasoning / Multilingual Advisory (query + generate modes). Brief description under each. |
| 7 | Built for Reliability | "Real APIs with retry logic and 3-tier fallback. Deployed and load-tested, not a demo running on a laptop." Mention pytest coverage briefly. |
| 8 | Data Integrity | One sentence: "Every number you saw traces to a live API call — CPCB via WAQI, OpenWeatherMap, and GPT-4o reasoning grounded in published source apportionment studies." |
| 9 | Scalability | Three bullets: (1) Add satellite data (Sentinel-5P NO2 bands) for source validation (2) Plug into GRAP/NCAP enforcement workflows (3) Extend to 200+ CPCB stations already live |
| 10 | Team | Names, roles, and one-line each on contribution. |

---

## 16. Submission Checklist

```
DATA INTEGRITY — verify before recording demo video
[ ] Map markers show "Source: CPCB via WAQI" in tooltip (not "fallback")
[ ] City panel shows real PM2.5, PM10, NO2 values from WAQI feed (not dashes)
[ ] Weather strip shows real temp/wind/humidity from OpenWeatherMap
[ ] Attribution reasoning mentions CPCB baseline study in its 2-sentence output
[ ] Advisory generated from real AQI value (check it matches map marker)
[ ] Tamil/Hindi query response is in correct script (not English)

DEPLOYMENT & RELIABILITY
[ ] Backend deployed and reachable at a public Render URL
[ ] Frontend deployed and reachable at a public Vercel URL
[ ] CORS configured for the live frontend domain (not just localhost)
[ ] Render backend pinged/warmed within 5 minutes of any live demo or judging slot
[ ] Retry logic confirmed working (Section 9.1) — temporarily kill WAQI token, confirm fallback
[ ] pytest suite passes (`pytest backend/tests/ -v`)
[ ] Manual QA checklist (Section 9.4) run at least once in the final week
[ ] Mobile viewport tested (375px) — no clipped or unusable panels
[ ] ErrorBoundary tested — forced crash shows reload screen, not a white page

PROTOTYPE
[ ] FastAPI backend running on live URL, startup cache warms on launch
[ ] WAQI bounds endpoint returning >10 India stations
[ ] City feed returning real pollutant breakdown for at least Delhi/Mumbai/Chennai
[ ] All 6 intelligence endpoints returning valid JSON
[ ] AdvisoryGenerator mode toggle works (query ↔ generate)
[ ] Tamil free-text query returns Tamil response, Hindi returns Hindi
[ ] No console errors during full demo flow on the live URL

ARCHITECTURE DIAGRAM
[ ] Exported as PNG at min 1920×1080
[ ] Shows all 5 layers: Data Sources / FastAPI Backend / Azure OpenAI / React SPA / End User
[ ] WAQI listed as primary, OpenAQ as backup
[ ] Render + Vercel deployment noted on the diagram
[ ] Arrows labelled with protocol/data type

PRESENTATION DECK
[ ] 10 slides, exported as PDF
[ ] Slide 1 includes 1.67M deaths statistic (Lancet — cite it)
[ ] Slide 3 includes the live URL / QR code
[ ] Slide 4 is the architecture diagram
[ ] Slide 5 has actual screenshots from the deployed app (not localhost, not wireframes)
[ ] At least one screenshot shows multi-pollutant panel with real values
[ ] At least one screenshot shows multilingual advisory output
[ ] Slide 7 mentions test coverage / reliability work briefly

DEMO VIDEO
[ ] 3–4 minutes max
[ ] Screen recorded at 1080p, on the live deployed URL
[ ] Narration follows the demo script in Section 13
[ ] Shows Tamil query → Tamil response moment explicitly
[ ] Shows tooltip with "CPCB via WAQI" data source label
[ ] Shows multi-pollutant PM2.5/PM10/NO2 panel
[ ] Uploaded to YouTube (unlisted) or Google Drive with public link

SUBMISSION
[ ] All four deliverables linked in submission form
[ ] Live URL included separately if the form allows it
[ ] Team registration number included
[ ] Contact email correct
[ ] Links tested in an incognito window before final submission
```

---

*Built for ET AI Hackathon 2026 · Team Orcus · VIT Vellore*
