from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv(override=True)

from routes.aqi import router as aqi_router
from routes.intelligence import router as intel_router
from services.cache import warm_cache


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Non-fatal on serverless: a cold start must not 500 if the AQI upstream is
    # slow/down. The /api/aqi/live route re-fetches on an empty cache anyway.
    try:
        await warm_cache()
    except Exception as exc:  # noqa: BLE001
        print(f"[cache] warm failed (non-fatal): {exc}")
    yield


app = FastAPI(title="AirWatch India API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:5175",
        "http://localhost:3000",
    ],
    # Allow the deployed frontend and any Vercel preview deployment
    # (e.g. https://airwatch-et-frontend.vercel.app, *-git-*.vercel.app).
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(aqi_router, prefix="/api/aqi", tags=["AQI Data"])
app.include_router(intel_router, prefix="/api/intel", tags=["Intelligence"])


@app.get("/health")
def health():
    return {"status": "ok"}
