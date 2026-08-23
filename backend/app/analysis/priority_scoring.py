from __future__ import annotations


def score_priority(
    need_severity: float = 0.0,
    sentiment: float = 0.0,
    urgency: float = 0.0,
    credibility: float = 0.0,
    recency: float = 0.0,
) -> dict:
    priority = (
        0.35 * need_severity
        + 0.25 * sentiment
        + 0.2 * urgency
        + 0.1 * credibility
        + 0.1 * recency
    )
    return {"priority_score": priority}
