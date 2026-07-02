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
    await warm_cache()
    yield


app = FastAPI(title="AirWatch India API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:5175",
        "http://localhost:3000",
        # Add your Vercel URL here once deployed, e.g.:
        # "https://airwatch-india.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(aqi_router, prefix="/api/aqi", tags=["AQI Data"])
app.include_router(intel_router, prefix="/api/intel", tags=["Intelligence"])


@app.get("/health")
def health():
    return {"status": "ok"}
