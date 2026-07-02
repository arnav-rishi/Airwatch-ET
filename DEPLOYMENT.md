# Deploying AirWatch India to Vercel

This app deploys as **two Vercel projects from this one repo**, both built from the
`deployment` branch:

| Project | Root Directory | What it is |
|---------|----------------|------------|
| `airwatch-backend`  | `backend`  | FastAPI, run as a Python serverless function |
| `airwatch-frontend` | `frontend` | React + Vite static site |

Deploy the **backend first** — the frontend needs the backend's URL.

---

## 1. Backend project

1. Go to <https://vercel.com/new> → **Import** this GitHub repo (`arnav-rishi/Airwatch-ET`).
2. **Project Name:** `airwatch-backend`
3. **Root Directory:** click *Edit* → select **`backend`**.
4. **Production Branch:** set to `deployment` (Project → Settings → Git, if not offered on import).
5. **Environment Variables** — add all six (values live in `Keys.txt` / from your teammate,
   **never commit them**):

   | Name | Notes |
   |------|-------|
   | `AZURE_OPENAI_API_KEY` | Azure OpenAI key |
   | `AZURE_OPENAI_ENDPOINT` | `https://<resource>.openai.azure.com` |
   | `AZURE_OPENAI_DEPLOYMENT` | `gpt-5-nano` |
   | `AZURE_OPENAI_API_VERSION` | `2025-04-01-preview` |
   | `WAQI_TOKEN` | raw token only (no `WAQI_TOKEN=` prefix) |
   | `OPENWEATHER_API_KEY` | OpenWeather key |

6. **Deploy.** When done, copy the URL, e.g. `https://airwatch-backend.vercel.app`.
7. Verify: open `https://airwatch-backend.vercel.app/health` → should return `{"status":"ok"}`.

`backend/vercel.json` routes every request to the FastAPI app and sets
`maxDuration: 60` so the LLM endpoints don't time out.

---

## 2. Frontend project

1. <https://vercel.com/new> → **Import the same repo again**.
2. **Project Name:** `airwatch-frontend`
3. **Root Directory:** **`frontend`** (framework auto-detects as **Vite**).
4. **Production Branch:** `deployment`.
5. **Environment Variable:**

   | Name | Value |
   |------|-------|
   | `VITE_API_URL` | `https://airwatch-backend.vercel.app/api` (your backend URL + `/api`) |

6. **Deploy.** Open the frontend URL — the map should load.

CORS is already handled: `backend/main.py` allows any `*.vercel.app` origin.

---

## 3. Verify end-to-end

- Map loads with AQI stations ✔
- Click a city → detail panel + attribution ✔
- Enforcement tab loads priorities ✔
- Advisory tab returns text (may take 10–40s — LLM reasoning model) ✔

## Notes / gotchas

- **Timeouts:** LLM calls are slow. `maxDuration: 60` covers them on Vercel's free tier.
- **Cold starts:** the in-memory station cache doesn't persist between serverless
  invocations; the first request after idle re-fetches live data (a few seconds).
- **Redeploys:** push to `deployment` → both projects auto-redeploy.
- **Secrets:** only ever entered in Vercel's env-var UI and the local gitignored
  `backend/.env`. `Keys.txt` is gitignored and lives outside the repo.
