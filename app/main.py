import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from app import __version__
from app.config import get_settings
from app.database import Base, engine
from app.routers import analytics, devices, ingest

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title=get_settings().app_name,
    version=__version__,
    description="Ingest IoT sensor readings, raise threshold alerts, "
    "and analyse trends and anomalies with pandas.",
    lifespan=lifespan,
)

app.include_router(devices.router)
app.include_router(ingest.router)
app.include_router(analytics.router)


@app.get("/", include_in_schema=False)
def dashboard() -> FileResponse:
    return FileResponse(STATIC_DIR / "dashboard.html")


@app.get("/health", tags=["health"])
def health() -> dict:
    return {"status": "ok", "version": __version__}
