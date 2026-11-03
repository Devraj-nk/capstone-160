from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ..analysis.summarization import summarize_texts

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
    return SummarizeResponse(summary=summarize_texts(req.texts))
