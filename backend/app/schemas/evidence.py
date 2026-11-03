from __future__ import annotations

import time
import uuid
from typing import Any, Optional

from pydantic import BaseModel, Field


class EvidencePost(BaseModel):
    id: str
    text: str
    cluster_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    # Optional ranking inputs — posts without a score keep their input order
    # and sort after scored posts.
    score: Optional[float] = None


class EvidenceItem(BaseModel):
    post_id: str
    cluster_id: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    score: Optional[float] = None
    # Step 10 fields (set by the pipeline's evidence selection).
    lang: Optional[str] = None
    text_en: Optional[str] = None  # English translation for reviewers; None = not translated
    why: list[str] = Field(default_factory=list)


class StoredEvidence(EvidenceItem):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    stored_at: float = Field(default_factory=lambda: time.time())
