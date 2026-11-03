"""Auto-escalation: urgent situations must not wait forever for a reviewer.

A pending situation whose band has an AUTO_ROUTE_MINUTES deadline (Critical,
High) is routed when no reviewer decides in time. Its tickets are marked
unverified and the situation becomes `auto_routed`, which stays in the review
queue: a reviewer can still approve (tickets become verified) or reject / mark
fake (tickets cancelled). Likely-fake situations are never auto-routed — acting
on a copy-paste rumour is worse than waiting. Escalation writes no verdict:
verdicts are human labels for evaluation only.

The bands and the fake flag are the scoring module's heuristic outputs, so this
routes on machine tags; the evaluation script's confirmation rate per band is
how that is checked.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from ..config import AUTO_ROUTE_MINUTES
from ..db import SITUATIONS, find_documents, update_document
from .tickets import open_tickets

logger = logging.getLogger(__name__)


def next_due(previous_due: float | None, band: str | None, now: float) -> float | None:
    """Deadline after a (re)score at wall-clock `now`. The earliest deadline is
    kept while the band stays escalating (High -> Critical never postpones it);
    dropping to a non-escalating band clears it, and rising again starts a new one."""
    minutes = AUTO_ROUTE_MINUTES.get(band or "", 0)
    if minutes <= 0:
        return None
    due = now + minutes * 60
    return due if previous_due is None else min(previous_due, due)


async def escalate_overdue(now: float | None = None) -> list[str]:
    """Route every overdue, non-fake pending situation. Returns their ids."""
    now = time.time() if now is None else now
    overdue: list[dict[str, Any]] = await find_documents(
        SITUATIONS,
        {
            "status": "pending",
            "escalation_due_at": {"$ne": None, "$lte": now},
            "fake_news.likely_fake": {"$ne": True},
        },
        limit=500,
    )
    escalated: list[str] = []
    for doc in overdue:
        # Claim it first, still conditional on "pending": if a reviewer decided
        # in the meantime nothing changes and no ticket is opened.
        claimed = await update_document(
            SITUATIONS,
            {"id": doc["id"], "status": "pending"},
            {"status": "auto_routed", "routed_to": doc.get("department"), "routed_at": now, "escalated_at": now},
        )
        if not claimed:
            continue
        await open_tickets(doc, by="auto_escalation", verified=False)
        escalated.append(doc["id"])
        logger.warning(
            "Auto-routed %s situation %s to %s: no reviewer decision in time",
            (doc.get("priority") or {}).get("band"), doc["id"], doc.get("department"),
        )
    return escalated
