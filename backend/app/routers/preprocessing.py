from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/preprocessing", tags=["preprocessing"])


class PreprocessRequest(BaseModel):
    text: str


class PreprocessResponse(BaseModel):
    text: str
    language: str | None = None


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.post("/preprocess", response_model=PreprocessResponse)
def preprocess(req: PreprocessRequest) -> PreprocessResponse:
    # TODO: text cleaning (URLs, mentions, hashtags, emojis) + language detection
    return PreprocessResponse(text=req.text, language=None)
