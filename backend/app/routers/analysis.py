from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ..analysis.combine import combine_tweet_record
from ..analysis.disaster_classification import classify_disaster
from ..analysis.fake_news import score_fake_news
from ..analysis.need_detection import detect_needs
from ..analysis.priority_scoring import score_priority
from ..analysis.sentiment import analyze_sentiment
from ..preprocessing.language import detect_language_final

router = APIRouter(prefix="/analysis", tags=["analysis"])


class AnalyzeRequest(BaseModel):
    text: str
    language: str | None = None


class AnalyzeResponse(BaseModel):
    sentiment: dict
    needs: dict
    fake_news: dict
    priority: dict


class PipelineRequest(BaseModel):
    """Input is assumed already cleaned/deduped by
    POST /preprocessing/preprocess — this runs Steps 3-6 (disaster gate,
    language, sentiment, need detection, combine) on top of that."""

    tweet_id: str
    text: str
    created_at: str


class PipelineResponse(BaseModel):
    tweet_id: str
    text: str
    lang: str | None
    is_romanized: bool
    is_code_mixed: bool
    is_disaster: bool
    disaster_confidence: float
    created_at: str
    sentiment_negativity: float
    needs: dict
    need_confidence: float
    actionability: float
    severity: float
    combined_at: str


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze(req: AnalyzeRequest) -> AnalyzeResponse:
    sentiment = analyze_sentiment(req.text)
    needs = detect_needs(req.text)
    fake_news = score_fake_news(req.text)
    priority = score_priority()
    return AnalyzeResponse(sentiment=sentiment, needs=needs, fake_news=fake_news, priority=priority)


@router.post("/pipeline", response_model=PipelineResponse)
def run_pipeline(req: PipelineRequest) -> PipelineResponse:
    """Steps 3-6 end to end: language is detected first (needed for the
    disaster gate's per-language threshold — the handoff doc lists Disaster
    Classification as step 3 and Language Detection as step 4, but the
    classifier's own threshold lookup needs a language, so this runs language
    detection before the gate rather than strictly in doc-listed order),
    then the disaster gate, sentiment, and need detection run, and everything
    gets merged by the Combine step into the record Clustering (Step 8) will
    consume."""
    lang_info = detect_language_final(req.text)
    disaster = classify_disaster(req.text, lang_info["lang"])
    sentiment_result = analyze_sentiment(req.text)
    needs_result = detect_needs(req.text)

    combined = combine_tweet_record(
        tweet_id=req.tweet_id,
        text=req.text,
        lang=lang_info["lang"],
        is_disaster=disaster["is_disaster"],
        disaster_confidence=disaster["disaster_confidence"],
        created_at=req.created_at,
        sentiment=sentiment_result,
        needs=needs_result,
    )

    return PipelineResponse(
        **combined,
        is_romanized=lang_info["is_romanized"],
        is_code_mixed=lang_info["is_code_mixed"],
    )
