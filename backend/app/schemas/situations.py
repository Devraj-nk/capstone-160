from __future__ import annotations

import time
import uuid
from typing import Literal, Optional

from pydantic import BaseModel, Field

SituationStatus = Literal["pending", "confirmed", "rejected"]


class Situation(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    text: str
    language: Optional[str] = None
    sentiment: dict = Field(default_factory=dict)
    needs: dict = Field(default_factory=dict)
    fake_news: dict = Field(default_factory=dict)
    priority: dict = Field(default_factory=dict)
    department: Optional[str] = None
    summary: Optional[str] = None
    evidence: list[str] = Field(default_factory=list)
    status: SituationStatus = "pending"
    created_at: float = Field(default_factory=lambda: time.time())


class SituationDecision(BaseModel):
    decision: Literal["approve", "reject"]


class AnalyticsSummary(BaseModel):
    total: int
    pending: int
    confirmed: int
    rejected: int
    by_department: dict[str, int] = Field(default_factory=dict)
