from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ..preprocessing.cleaning import clean_text, is_valid_post
from ..preprocessing.deduplication import register_repost

router = APIRouter(prefix="/preprocessing", tags=["preprocessing"])


class PreprocessRequest(BaseModel):
    text: str


class PreprocessResponse(BaseModel):
    text: str
    is_valid: bool
    repost_count: int
    dropped: bool


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.post("/preprocess", response_model=PreprocessResponse)
def preprocess(req: PreprocessRequest) -> PreprocessResponse:
    cleaned = clean_text(req.text)
    valid = is_valid_post(cleaned)
    count = register_repost(cleaned) if valid else 0
    dropped = valid and count > 1

    return PreprocessResponse(
        text=cleaned,
        is_valid=valid,
        repost_count=count,
        dropped=dropped,
    )
