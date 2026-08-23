from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ..analysis.fake_news import score_fake_news
from ..analysis.need_detection import detect_needs
from ..analysis.priority_scoring import score_priority
from ..analysis.sentiment import analyze_sentiment

router = APIRouter(prefix="/analysis", tags=["analysis"])


class AnalyzeRequest(BaseModel):
    text: str
    language: str | None = None


class AnalyzeResponse(BaseModel):
    sentiment: dict
    needs: dict
    fake_news: dict
    priority: dict


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
