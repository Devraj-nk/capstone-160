"""Step 13 routing tickets: one per (situation, department)."""
from __future__ import annotations

import time
from typing import Any

from ..db import ROUTING_TICKETS, find_documents, find_one_document, get_collection, insert_document
from ..schemas.routing import OPEN_STATUSES, TRANSITIONS, RoutingTicket, TicketEvent
from .routing import DEFAULT_DEPARTMENT, DEPARTMENT_BY_NEED


def departments_for(situation: dict[str, Any]) -> list[str]:
    """Every department whose need cleared its threshold (strongest first);
    the situation's own department when none did."""
    active = (situation.get("needs") or {}).get("active") or []
    names = list(dict.fromkeys(DEPARTMENT_BY_NEED[n] for n in active if n in DEPARTMENT_BY_NEED))
    return names or [situation.get("department") or DEFAULT_DEPARTMENT]


def _event(status: str, by: str, at: float) -> dict[str, Any]:
    return TicketEvent(status=status, by=by, at=at).model_dump()


async def open_tickets(situation: dict[str, Any], by: str = "reviewer", verified: bool = True) -> list[str]:
    """Route a situation. Idempotent: re-approving never duplicates a ticket; a
    previously cancelled ticket is reopened; a resolved one stays resolved.
    verified=False marks tickets opened by auto-escalation (no reviewer yet);
    a later reviewer approval flips them to verified."""
    now = time.time()
    priority = situation.get("priority") or {}
    ids: list[str] = []
    for department in departments_for(situation):
        existing = await find_one_document(
            ROUTING_TICKETS, {"situation_id": situation["id"], "department": department}
        )
        if existing is None:
            ticket = RoutingTicket(
                situation_id=situation["id"],
                cluster_id=situation.get("cluster_id"),
                department=department,
                queue_priority=priority.get("priority_score") or 0.0,
                band=priority.get("band"),
                summary=situation.get("summary"),
                summary_i18n=situation.get("summary_i18n") or {},
                verified=verified,
                history=[TicketEvent(status="routed", by=by, at=now)],
                created_at=now,
                updated_at=now,
            )
            await insert_document(ROUTING_TICKETS, ticket.model_dump())
            ids.append(ticket.id)
            continue
        update: dict[str, Any] = {"updated_at": now}
        push = None
        if existing["status"] == "cancelled":
            update["status"] = "routed"
            push = _event("routed", by, now)
        if verified and not existing.get("verified", True):
            update["verified"] = True
        if len(update) > 1:
            change: dict[str, Any] = {"$set": update}
            if push:
                change["$push"] = {"history": push}
            await get_collection(ROUTING_TICKETS).update_one({"id": existing["id"]}, change)
        ids.append(existing["id"])
    return ids


async def cancel_tickets(situation_id: str, by: str = "reviewer") -> int:
    """Close the open tickets of a situation that was rejected / marked fake."""
    now = time.time()
    tickets = await find_documents(
        ROUTING_TICKETS, {"situation_id": situation_id, "status": {"$in": list(OPEN_STATUSES)}}
    )
    for ticket in tickets:
        await get_collection(ROUTING_TICKETS).update_one(
            {"id": ticket["id"]},
            {"$set": {"status": "cancelled", "updated_at": now}, "$push": {"history": _event("cancelled", by, now)}},
        )
    return len(tickets)


async def sync_ticket_priority(situation: dict[str, Any]) -> None:
    """Rescoring a routed situation updates its open tickets' queue position
    and summary. `situation` holds the rescored fields."""
    priority = situation.get("priority") or {}
    await get_collection(ROUTING_TICKETS).update_many(
        {"situation_id": situation["id"], "status": {"$in": list(OPEN_STATUSES)}},
        {"$set": {
            "queue_priority": priority.get("priority_score") or 0.0,
            "band": priority.get("band"),
            "summary": situation.get("summary"),
            "summary_i18n": situation.get("summary_i18n") or {},
            "updated_at": time.time(),
        }},
    )


async def set_ticket_status(ticket_id: str, status: str, by: str) -> dict[str, Any]:
    """Department lifecycle step. Raises LookupError (no ticket) or
    ValueError (transition not allowed, e.g. resolved -> acknowledged)."""
    ticket = await find_one_document(ROUTING_TICKETS, {"id": ticket_id})
    if ticket is None:
        raise LookupError(ticket_id)
    if status not in TRANSITIONS[ticket["status"]]:
        raise ValueError(f"cannot move a {ticket['status']} ticket to {status}")
    now = time.time()
    event = _event(status, by, now)
    await get_collection(ROUTING_TICKETS).update_one(
        {"id": ticket_id}, {"$set": {"status": status, "updated_at": now}, "$push": {"history": event}}
    )
    ticket.update(status=status, updated_at=now, history=[*ticket["history"], event])
    return ticket
