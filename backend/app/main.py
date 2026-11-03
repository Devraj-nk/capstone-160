from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .analysis.offline_models import configure_model_backend
from .config import CORS_ORIGINS, MODEL_BACKEND, PIPELINE_POLL_INTERVAL, PIPELINE_WORKER_ENABLED
from .db import ensure_indexes
from .pipeline import worker
from .pipeline.orchestrator import orchestrator
from .routers import (
    analysis,
    analytics,
    clustering,
    evidence,
    ingestion,
    pipeline,
    preprocessing,
    queue,
    routing,
    situations,
    summarization,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    orchestrator.model_backend = configure_model_backend(MODEL_BACKEND)
    try:
        await asyncio.wait_for(ensure_indexes(), timeout=15)
        # Continue the clusters that were live before the restart.
        await asyncio.wait_for(orchestrator.restore_clusters(), timeout=60)
    except Exception as exc:  # noqa: BLE001 — an unreachable DB must not stop the API from starting
        logger.warning("MongoDB startup step failed (indexes / cluster restore): %s", exc)
    if PIPELINE_WORKER_ENABLED:
        worker.start(orchestrator, PIPELINE_POLL_INTERVAL)
    yield
    await worker.stop()


app = FastAPI(title="Crisis Monitoring Backend", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ingestion.router)
app.include_router(queue.router)
app.include_router(preprocessing.router)
app.include_router(analysis.router)
app.include_router(clustering.router)
app.include_router(summarization.router)
app.include_router(evidence.router)
app.include_router(pipeline.router)
app.include_router(routing.router)
app.include_router(situations.router)
app.include_router(analytics.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
