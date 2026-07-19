from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

load_dotenv(override=True)

from routes.aqi import router as aqi_router
from routes.intelligence import router as intel_router
from services.cache import warm_cache
from services.rate_limit import check_rate_limit


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

@app.middleware("http")
async def rate_limit_intel_routes(request: Request, call_next):
    """Throttle the LLM-backed /api/intel/* routes so one caller can't burn
    Azure OpenAI budget unbounded on a public deployment. AQI data routes are
    cheap (cached/static) and left unthrottled."""
    if request.url.path.startswith("/api/intel/"):
        # Behind Vercel's proxy, request.client.host is the proxy's own IP,
        # not the caller's — that collapses every caller onto one bucket.
        # Vercel forwards the real client IP in X-Forwarded-For.
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            client_id = forwarded_for.split(",")[0].strip()
        else:
            client_id = request.client.host if request.client else "unknown"
        allowed, retry_after = check_rate_limit(client_id)
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Please slow down and try again shortly."},
                headers={"Retry-After": str(retry_after)},
            )
    return await call_next(request)


app.include_router(aqi_router, prefix="/api/aqi", tags=["AQI Data"])
app.include_router(intel_router, prefix="/api/intel", tags=["Intelligence"])


@app.get("/health")
def health():
    return {"status": "ok"}
