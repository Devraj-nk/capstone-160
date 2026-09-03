from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ..preprocessing.cleaning import clean_text, is_valid_post
from ..preprocessing.deduplication import register_repost
from ..preprocessing.language import detect_language_final

router = APIRouter(prefix="/preprocessing", tags=["preprocessing"])


class PreprocessRequest(BaseModel):
    text: str


class PreprocessResponse(BaseModel):
    text: str
    is_valid: bool
    repost_count: int
    dropped: bool
    lang: str | None = None
    is_romanized: bool = False
    is_code_mixed: bool = False


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.post("/preprocess", response_model=PreprocessResponse)
def preprocess(req: PreprocessRequest) -> PreprocessResponse:
    cleaned = clean_text(req.text)
    valid = is_valid_post(cleaned)
    count = register_repost(cleaned) if valid else 0
    dropped = valid and count > 1

    # Step 4 (language detection) only makes sense on text worth keeping —
    # skip it for invalid/dropped posts rather than spending a model call.
    lang_info = detect_language_final(cleaned) if valid and not dropped else {
        "lang": None,
        "is_romanized": False,
        "is_code_mixed": False,
    }

    return PreprocessResponse(
        text=cleaned,
        is_valid=valid,
        repost_count=count,
        dropped=dropped,
        **lang_info,
    )
