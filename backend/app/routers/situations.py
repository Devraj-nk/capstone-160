from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, HTTPException, Query

from ..db import (
    DROPPED_TWEETS,
    ROUTING_TICKETS,
    SITUATIONS,
    VERDICTS,
    find_documents,
    find_one_document,
    get_collection,
    insert_document,
    update_document,
)
from ..pipeline.orchestrator import DROP_REASONS
from ..pipeline.tickets import cancel_tickets, open_tickets
from ..schemas.routing import OPEN_STATUSES
from ..schemas.situations import (
    DECISIONS,
    AnalyticsSummary,
    Situation,
    SituationDecision,
    SituationStatus,
)

router = APIRouter(tags=["situations"])


def _priority(doc: dict) -> float:
    return (doc.get("priority") or {}).get("priority_score") or 0.0


@router.get("/situations", response_model=list[Situation])
async def list_situations(
    status: list[SituationStatus] | None = Query(None), department: str | None = None
) -> list[Situation]:
    """`status` can repeat, e.g. ?status=pending&status=auto_routed (the review queue)."""
    query: dict = {}
    if status:
        query["status"] = {"$in": status}
    if department:
        query["department"] = department
    docs = await find_documents(SITUATIONS, query, limit=200)
    # Highest priority first so reviewers see the most urgent situation on top.
    docs.sort(key=_priority, reverse=True)
    return [Situation(**doc) for doc in docs]


@router.get("/situations/{situation_id}", response_model=Situation)
async def get_situation(situation_id: str) -> Situation:
    doc = await find_one_document(SITUATIONS, {"id": situation_id})
    if doc is None:
        raise HTTPException(status_code=404, detail="Situation not found")
    return Situation(**doc)


@router.get("/situations/{situation_id}/evidence")
async def get_situation_evidence(situation_id: str) -> list[dict]:
    """The situation's ranked, privacy-masked evidence posts (stored inside it)."""
    doc = await find_one_document(SITUATIONS, {"id": situation_id})
    if doc is None:
        raise HTTPException(status_code=404, detail="Situation not found")
    return doc.get("evidence_posts", [])


@router.post("/situations/{situation_id}/decision", response_model=Situation)
async def decide_situation(situation_id: str, body: SituationDecision) -> Situation:
    """Steps 12-13: approve routes the situation to every needed department
    (one routing ticket each); reject / fake cancels open tickets. Every
    decision is stored as a verdict with a frozen snapshot of the scores, which
    is what evaluation and retraining read even if the cluster changes later."""
    doc = await find_one_document(SITUATIONS, {"id": situation_id})
    if doc is None:
        raise HTTPException(status_code=404, detail="Situation not found")

    now = time.time()
    status, verdict = DECISIONS[body.decision]
    update: dict = {"status": status, "decided_at": now, "review_note": body.note}
    if body.decision == "approve":
        await open_tickets(doc)
        update.update(routed_to=doc.get("department"), routed_at=now)
    else:
        await cancel_tickets(situation_id)
        update.update(routed_to=None, routed_at=None)
    await update_document(SITUATIONS, {"id": situation_id}, update)
    doc.update(update)

    await insert_document(
        VERDICTS,
        {
            "id": f"vd_{uuid.uuid4().hex[:12]}",
            "situation_id": situation_id,
            "cluster_id": doc.get("cluster_id"),
            "verdict": verdict,
            "decision": body.decision,
            "decided_by": "reviewer",
            "note": body.note,
            "snapshot": {
                "priority": doc.get("priority"),
                "fake_news": doc.get("fake_news"),
                "needs": doc.get("needs"),
                "department": doc.get("department"),
                "languages": doc.get("languages", []),
                "post_count": doc.get("post_count", 0),
            },
            "tweet_ids": doc.get("tweet_ids", []),
            "evidence": doc.get("evidence", []),
            "decided_at": now,
        },
    )
    return Situation(**doc)


@router.get("/analytics/summary", response_model=AnalyticsSummary)
async def analytics_summary() -> AnalyticsSummary:
    docs = await find_documents(SITUATIONS, {}, limit=10000)
    by_department: dict[str, int] = {}
    for doc in docs:
        dept = doc.get("department")
        # live workload only: rejected / fake situations are not a department's concern
        if dept and doc.get("status") in ("pending", "auto_routed", "confirmed"):
            by_department[dept] = by_department.get(dept, 0) + 1

    dropped = {
        reason: await get_collection(DROPPED_TWEETS).count_documents({"reason": reason})
        for reason in DROP_REASONS
    }
    open_tickets_by_department: dict[str, int] = {}
    for ticket in await find_documents(ROUTING_TICKETS, {"status": {"$in": list(OPEN_STATUSES)}}, limit=10000):
        dept = ticket["department"]
        open_tickets_by_department[dept] = open_tickets_by_department.get(dept, 0) + 1

    return AnalyticsSummary(
        total=len(docs),
        pending=sum(1 for d in docs if d.get("status") == "pending"),
        confirmed=sum(1 for d in docs if d.get("status") == "confirmed"),
        rejected=sum(1 for d in docs if d.get("status") == "rejected"),
        fake=sum(1 for d in docs if d.get("status") == "fake"),
        auto_routed=sum(1 for d in docs if d.get("status") == "auto_routed"),
        by_department=by_department,
        dropped_by_reason={k: v for k, v in dropped.items() if v},
        open_tickets_by_department=open_tickets_by_department,
    )
