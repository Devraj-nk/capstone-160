from __future__ import annotations

from collections import deque
from typing import Deque

from fastapi import APIRouter, HTTPException

from ..config import QUEUE_MAX_SIZE
from ..schemas.events import DequeueResponse, EnqueueResponse, QueueItem

router = APIRouter(prefix="/queue", tags=["queue"])

_queue: Deque[QueueItem] = deque()


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/stats")
def stats() -> dict:
    return {
        "queue_size": len(_queue),
        "max_size": QUEUE_MAX_SIZE,
    }


def enqueue_item(item: QueueItem) -> EnqueueResponse:
    """Enqueue an item. Called directly by the ingestion router (same process)
    as well as via the /queue/enqueue HTTP endpoint below."""
    dropped_oldest = False

    if QUEUE_MAX_SIZE <= 0:
        raise HTTPException(status_code=500, detail="QUEUE_MAX_SIZE must be > 0")

    if len(_queue) >= QUEUE_MAX_SIZE:
        _queue.popleft()
        dropped_oldest = True

    _queue.append(item)

    return EnqueueResponse(
        accepted=True,
        item_id=item.id,
        queue_size=len(_queue),
        dropped_oldest=dropped_oldest,
    )


@router.post("/enqueue", response_model=EnqueueResponse)
def enqueue(item: QueueItem) -> EnqueueResponse:
    return enqueue_item(item)


@router.post("/dequeue", response_model=DequeueResponse)
def dequeue() -> DequeueResponse:
    if not _queue:
        return DequeueResponse(item=None, queue_size=0)

    item = _queue.popleft()
    return DequeueResponse(item=item, queue_size=len(_queue))
