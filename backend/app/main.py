from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import CORS_ORIGINS
from .routers import analysis, evidence, ingestion, preprocessing, queue, situations, summarization

app = FastAPI(title="Crisis Monitoring Backend", version="0.1.0")

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
app.include_router(summarization.router)
app.include_router(evidence.router)
app.include_router(situations.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
