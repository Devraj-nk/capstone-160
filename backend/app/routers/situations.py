from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..db import find_documents, find_one_document, update_document
from ..schemas.situations import AnalyticsSummary, Situation, SituationDecision, SituationStatus

router = APIRouter(tags=["situations"])

COLLECTION = "situations"


@router.get("/situations", response_model=list[Situation])
async def list_situations(status: SituationStatus | None = None) -> list[Situation]:
    query = {"status": status} if status else {}
    docs = await find_documents(COLLECTION, query, limit=200)
    return [Situation(**doc) for doc in docs]


@router.post("/situations/{situation_id}/decision", response_model=Situation)
async def decide_situation(situation_id: str, body: SituationDecision) -> Situation:
    doc = await find_one_document(COLLECTION, {"id": situation_id})
    if doc is None:
        raise HTTPException(status_code=404, detail="Situation not found")

    new_status = "confirmed" if body.decision == "approve" else "rejected"
    await update_document(COLLECTION, {"id": situation_id}, {"status": new_status})
    doc["status"] = new_status
    return Situation(**doc)


@router.get("/analytics/summary", response_model=AnalyticsSummary)
async def analytics_summary() -> AnalyticsSummary:
    docs = await find_documents(COLLECTION, {}, limit=10000)
    by_department: dict[str, int] = {}
    for doc in docs:
        dept = doc.get("department")
        if dept:
            by_department[dept] = by_department.get(dept, 0) + 1

    return AnalyticsSummary(
        total=len(docs),
        pending=sum(1 for d in docs if d.get("status") == "pending"),
        confirmed=sum(1 for d in docs if d.get("status") == "confirmed"),
        rejected=sum(1 for d in docs if d.get("status") == "rejected"),
        by_department=by_department,
    )
