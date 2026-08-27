from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ..db import insert_document
from ..evidence.privacy import mask_metadata, mask_personal_details
from ..evidence.ranking import select_representative_posts
from ..schemas.evidence import EvidenceItem, EvidencePost, StoredEvidence

router = APIRouter(prefix="/evidence", tags=["evidence"])

COLLECTION = "evidence"


class ExtractRequest(BaseModel):
    posts: list[EvidencePost]
    top_k: int = 3


class ExtractResponse(BaseModel):
    evidence: list[EvidenceItem]


class StoreRequest(BaseModel):
    evidence: list[EvidenceItem]


class StoreResponse(BaseModel):
    stored_ids: list[str]


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.post("/extract", response_model=ExtractResponse)
def extract(req: ExtractRequest) -> ExtractResponse:
    evidence = select_representative_posts(req.posts, top_k=req.top_k)
    return ExtractResponse(evidence=evidence)


@router.post("/store", response_model=StoreResponse)
async def store(req: StoreRequest) -> StoreResponse:
    stored_ids: list[str] = []
    for item in req.evidence:
        record = StoredEvidence(
            post_id=item.post_id,
            cluster_id=item.cluster_id,
            text=mask_personal_details(item.text),
            metadata=mask_metadata(item.metadata),
        )
        await insert_document(COLLECTION, record.model_dump())
        stored_ids.append(record.id)
    return StoreResponse(stored_ids=stored_ids)
