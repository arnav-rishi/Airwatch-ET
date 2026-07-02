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
- **⚖️ Enforcement Priorities** — AI generates the day's top-3 field enforcement actions for
  pollution-control authorities, ranked by evidence.
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

**Resilience:** 3-tier AQI fallback (WAQI → OpenAQ → static dataset), 10-minute station
cache warmed at startup, and retry-with-backoff on all external API calls.

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
| `GET`  | `/api/intel/enforcement/auto` | Enforcement priorities for top-5 live cities |
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
