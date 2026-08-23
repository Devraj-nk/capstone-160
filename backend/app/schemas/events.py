from __future__ import annotations

import time
import uuid
from typing import Any, Optional

from pydantic import BaseModel, Field


class RawEvent(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    created_at: float = Field(default_factory=lambda: time.time())
    attributes: dict[str, Any] = Field(default_factory=dict)


class IngestedEvent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    text: str
    created_at: float
    ingested_at: float = Field(default_factory=lambda: time.time())
    metadata: dict


class IngestResponse(BaseModel):
    ok: bool
    ingested_id: str
    queue_item_id: Optional[str] = None
    dropped_oldest: Optional[bool] = None


class QueueItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    payload: dict
    enqueued_at: float = Field(default_factory=lambda: time.time())


class EnqueueResponse(BaseModel):
    accepted: bool
    item_id: str
    queue_size: int
    dropped_oldest: bool = False


class DequeueResponse(BaseModel):
    item: Optional[QueueItem]
    queue_size: int
