from __future__ import annotations

import time
import uuid
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

# routed -> acknowledged -> resolved; cancelled when the situation is later
# rejected / marked fake.
TicketStatus = Literal["routed", "acknowledged", "resolved", "cancelled"]
OPEN_STATUSES = ("routed", "acknowledged")

# Allowed manual transitions (by a department officer).
TRANSITIONS: dict[str, tuple[str, ...]] = {
    "routed": ("acknowledged", "resolved"),
    "acknowledged": ("resolved",),
    "resolved": (),
    "cancelled": (),
}


class TicketEvent(BaseModel):
    status: TicketStatus
    at: float = Field(default_factory=lambda: time.time())
    by: str = "system"


class RoutingTicket(BaseModel):
    """One situation sent to one department queue. A situation can need
    several departments (flood + health), hence a separate collection."""

    id: str = Field(default_factory=lambda: f"rt_{uuid.uuid4().hex[:12]}")
    situation_id: str
    cluster_id: Optional[str] = None
    department: str
    queue_priority: float = 0.0  # = the situation's priority score, kept in sync on rescoring
    band: Optional[str] = None
    summary: Optional[str] = None
    summary_i18n: dict[str, str] = Field(default_factory=dict)
    # False = routed by auto-escalation before any reviewer looked at it.
    verified: bool = True
    # "fake" when a reviewer marked the situation as possibly fake. The ticket
    # is still routed: a human decision is a signal for the department, not a veto.
    reviewer_flag: Optional[str] = None
    status: TicketStatus = "routed"
    history: list[TicketEvent] = Field(default_factory=list)
    created_at: float = Field(default_factory=lambda: time.time())
    updated_at: float = Field(default_factory=lambda: time.time())


class TicketStatusUpdate(BaseModel):
    status: Literal["acknowledged", "resolved"]
    by: str = "department"


def ticket_view(doc: dict[str, Any]) -> RoutingTicket:
    return RoutingTicket(**{k: v for k, v in doc.items() if k != "_id"})
