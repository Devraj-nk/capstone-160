from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/summarization", tags=["summarization"])


class SummarizeRequest(BaseModel):
    texts: list[str]


class SummarizeResponse(BaseModel):
    summary: str


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.post("/summarize", response_model=SummarizeResponse)
def summarize(req: SummarizeRequest) -> SummarizeResponse:
    # TODO: mT5-based summarization over the clustered posts
    return SummarizeResponse(summary=" ".join(req.texts)[:280])
