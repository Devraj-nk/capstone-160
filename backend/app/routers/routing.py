from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..db import ROUTING_TICKETS, find_documents
from ..pipeline.tickets import set_ticket_status
from ..schemas.routing import RoutingTicket, TicketStatus, TicketStatusUpdate, ticket_view

router = APIRouter(prefix="/tickets", tags=["routing"])


@router.get("", response_model=list[RoutingTicket])
async def list_tickets(department: str | None = None, status: TicketStatus | None = None) -> list[RoutingTicket]:
    """A department's queue: highest priority first."""
    query: dict = {}
    if department:
        query["department"] = department
    if status:
        query["status"] = status
    docs = await find_documents(ROUTING_TICKETS, query, limit=500)
    docs.sort(key=lambda d: d.get("queue_priority") or 0.0, reverse=True)
    return [ticket_view(doc) for doc in docs]


@router.post("/{ticket_id}/status", response_model=RoutingTicket)
async def update_ticket(ticket_id: str, body: TicketStatusUpdate) -> RoutingTicket:
    try:
        return ticket_view(await set_ticket_status(ticket_id, body.status, body.by))
    except LookupError:
        raise HTTPException(status_code=404, detail="Ticket not found")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
