from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ..schemas.events import IngestedEvent, IngestResponse, QueueItem, RawEvent
from .queue import enqueue_item

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.post("/ingest", response_model=IngestResponse)
def ingest(evt: RawEvent) -> IngestResponse:
    metadata: dict[str, Any] = {
        "pipeline": "demo",
        "schema_version": 1,
    }

    if evt.attributes:
        metadata["attributes"] = evt.attributes

    ingested = IngestedEvent(
        text=evt.text,
        created_at=evt.created_at,
        metadata=metadata,
    )

    queue_item = QueueItem(id=ingested.id, payload=ingested.model_dump())
    enqueue_result = enqueue_item(queue_item)

    return IngestResponse(
        ok=True,
        ingested_id=ingested.id,
        queue_item_id=enqueue_result.item_id,
        dropped_oldest=enqueue_result.dropped_oldest,
    )
