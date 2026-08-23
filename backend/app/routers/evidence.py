from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/evidence", tags=["evidence"])


class ExtractRequest(BaseModel):
    texts: list[str]
    top_k: int = 5


class ExtractResponse(BaseModel):
    top_posts: list[str]


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.post("/extract", response_model=ExtractResponse)
def extract(req: ExtractRequest) -> ExtractResponse:
    # TODO: SBERT/LaBSE embeddings + similarity-to-priority ranking
    return ExtractResponse(top_posts=req.texts[: req.top_k])
