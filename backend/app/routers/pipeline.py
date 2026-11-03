from __future__ import annotations

from fastapi import APIRouter, Query

from ..analysis.clustering import manager
from ..pipeline import worker
from ..pipeline.escalation import escalate_overdue
from ..pipeline.orchestrator import orchestrator, summarize_outcome
from ..schemas.events import RawEvent
from .ingestion import build_ingested_event
from .queue import dequeue_item, queue_size

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/stats")
def stats() -> dict:
    situations, holding = manager.situations()
    return {
        "model_backend": orchestrator.model_backend,
        "worker_running": worker.is_running(),
        "queue_size": queue_size(),
        "cluster_count": len(manager.clusters),
        "situation_clusters": len(situations),
        "holding_clusters": len(holding),
        "counts": dict(orchestrator.stats),
        "last_error": orchestrator.last_error,
    }


@router.post("/process")
async def process(evt: RawEvent) -> dict:
    """Run one raw post through the whole pipeline synchronously, bypassing
    the queue — for demos and debugging."""
    ingested = build_ingested_event(evt)
    return summarize_outcome(await orchestrator.process_event(ingested.model_dump()))


@router.post("/drain")
async def drain(max_items: int = Query(100, ge=1, le=10000)) -> dict:
    """Process up to max_items queued posts now (useful when the background
    worker is disabled)."""
    outcomes = []
    while len(outcomes) < max_items:
        item = dequeue_item()
        if item is None:
            break
        outcomes.append(summarize_outcome(await orchestrator.process_event(item.payload)))
    stages: dict[str, int] = {}
    for outcome in outcomes:
        stages[outcome["stage"]] = stages.get(outcome["stage"], 0) + 1
    return {"processed": len(outcomes), "stages": stages, "remaining": queue_size(), "outcomes": outcomes}


@router.post("/escalate")
async def escalate() -> dict:
    """Run the auto-escalation check now (the worker also runs it every
    ESCALATION_CHECK_SECONDS)."""
    escalated = await escalate_overdue()
    orchestrator.stats["auto_routed"] += len(escalated)
    return {"auto_routed": escalated}


@router.post("/reset")
def reset() -> dict:
    """Clear in-memory clusters, repost counts and stats (MongoDB untouched)."""
    orchestrator.reset()
    return {"ok": True}
