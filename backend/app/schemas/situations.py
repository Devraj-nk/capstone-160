from __future__ import annotations

import time
import uuid
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

# pending -> confirmed (routed) | rejected (not relevant) | fake (marked misinformation)
# pending -> auto_routed (no reviewer in time; routed unverified, still reviewable)
SituationStatus = Literal["pending", "auto_routed", "confirmed", "rejected", "fake"]
# Statuses a reviewer still has to decide on.
REVIEWABLE_STATUSES = ("pending", "auto_routed")

# Reviewer decision -> (situation status, stored verdict)
DECISIONS: dict[str, tuple[str, str]] = {
    "approve": ("confirmed", "true"),
    "reject": ("rejected", "not_relevant"),
    "fake": ("fake", "fake"),
}

SCORE_HISTORY_LIMIT = 20


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
    # Filled by the pipeline orchestrator (absent on hand-made situations).
    cluster_id: Optional[str] = None
    post_count: int = 0
    n_reports_unique: int = 0  # independent reports (copies / translations count once)
    tweet_ids: list[str] = Field(default_factory=list)
    first_report_at: Optional[float] = None  # post times of the earliest / latest member
    last_report_at: Optional[float] = None
    location: Optional[str] = None  # place name found in the posts (summary LOCATION slot)
    languages: list[str] = Field(default_factory=list)
    summary_i18n: dict[str, str] = Field(default_factory=dict)  # same summary in en/hi/kn/ta/te
    summary_method: Optional[str] = None
    representative: dict[str, Any] = Field(default_factory=dict)
    evidence_posts: list[dict[str, Any]] = Field(default_factory=list)
    evidence_version: Optional[str] = None
    signals: dict[str, Any] = Field(default_factory=dict)  # matched terms etc., for explainability
    # Last SCORE_HISTORY_LIMIT rescorings: [{"at", "priority", "band", "post_count", "n_unique"}],
    # so the dashboard can show whether an event is growing.
    score_history: list[dict[str, Any]] = Field(default_factory=list)
    updated_at: Optional[float] = None
    # Filled by human review / routing.
    decided_at: Optional[float] = None
    review_note: Optional[str] = None
    routed_to: Optional[str] = None
    routed_at: Optional[float] = None
    # Auto-escalation: when a pending High/Critical situation gets routed
    # without a reviewer (None = never, e.g. Medium/Low), and when it was.
    escalation_due_at: Optional[float] = None
    escalated_at: Optional[float] = None


class SituationDecision(BaseModel):
    decision: Literal["approve", "reject", "fake"]
    note: Optional[str] = None


class AnalyticsSummary(BaseModel):
    total: int
    pending: int
    confirmed: int
    rejected: int
    fake: int = 0
    auto_routed: int = 0
    by_department: dict[str, int] = Field(default_factory=dict)
    # Posts removed before analysis, by reason (from dropped_tweets).
    dropped_by_reason: dict[str, int] = Field(default_factory=dict)
    # Open routing tickets per department (routed or acknowledged).
    open_tickets_by_department: dict[str, int] = Field(default_factory=dict)
