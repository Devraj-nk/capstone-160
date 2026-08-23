from __future__ import annotations


def score_fake_news(text: str, credibility: float = 0.5, content_risk: float = 0.0) -> dict:
    # TODO: XLM-R fake-probability model
    model_prediction = 0.0
    fake_score = 0.5 * model_prediction + 0.3 * (1 - credibility) + 0.2 * content_risk
    return {"fake_score": fake_score}
