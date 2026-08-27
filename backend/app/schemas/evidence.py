from __future__ import annotations

import time
import uuid
from typing import Any

from pydantic import BaseModel, Field


class EvidencePost(BaseModel):
    id: str
    text: str
    cluster_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceItem(BaseModel):
    post_id: str
    cluster_id: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class StoredEvidence(EvidenceItem):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    stored_at: float = Field(default_factory=lambda: time.time())
