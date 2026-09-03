from __future__ import annotations

from datetime import datetime, timezone

ACTION_KEYWORDS = {
    1.0: ["send help", "need rescue", "trapped", "urgent", "immediately", "sos", "please send", "need medical help"],
    0.6: ["please help", "someone check", "worried about", "not sure what to do", "need assistance"],
    0.2: ["this is sad", "can't believe", "thoughts and prayers", "hope everyone"],
}


def actionability_score(text: str) -> float:
    """Rule-based keyword-tier scoring: 1.0 for urgent/rescue-type phrases,
    0.6 for softer help requests, 0.2 for sympathy-only text with no actual
    request, 0.0 if nothing matches."""
    text_lower = text.lower()
    best_score = 0.0
    for tier_score, phrases in ACTION_KEYWORDS.items():
        for phrase in phrases:
            if phrase in text_lower:
                best_score = max(best_score, tier_score)
    return best_score


def compute_severity(sentiment_negativity: float, need_confidence: float) -> float:
    """severity = 0.6 * NeedSeverity + 0.4 * sentiment_negativity, using
    need_confidence directly as the NeedSeverity proxy (per the
    Priority/Severity formula agreed with the team)."""
    return round(0.6 * need_confidence + 0.4 * sentiment_negativity, 4)


def combine_tweet_record(
    *,
    tweet_id: str,
    text: str,
    lang: str | None,
    is_disaster: bool,
    disaster_confidence: float,
    created_at: str,
    sentiment: dict,
    needs: dict,
) -> dict:
    """Step 6. Merges Step 3 (disaster gate) + Step 4 (language) + Step 5a
    (sentiment) + Step 5b (need detection) into the one record Clustering
    (Step 8) consumes.

    `sentiment` and `needs` are the dicts returned by
    app.analysis.sentiment.analyze_sentiment() and
    app.analysis.need_detection.detect_needs() respectively.

    Signature note: the handoff doc's reference implementation takes
    `sentiment_json`/`need_json` blobs that already carry tweet_id/text/lang/
    is_disaster baked in (their notebook's earlier steps wrote to shared
    JSON files). Here those pieces come from separate function calls instead,
    so they're passed explicitly — the output schema is unchanged."""
    actionability = actionability_score(text)
    severity = compute_severity(
        sentiment_negativity=sentiment["sentiment_negativity"],
        need_confidence=needs["need_confidence"],
    )

    return {
        "tweet_id": tweet_id,
        "text": text,
        "lang": lang,
        "is_disaster": is_disaster,
        "disaster_confidence": disaster_confidence,
        "created_at": created_at,
        "sentiment_negativity": sentiment["sentiment_negativity"],
        "needs": needs["needs"],
        "need_confidence": needs["need_confidence"],
        "actionability": actionability,
        "severity": severity,
        "combined_at": datetime.now(timezone.utc).isoformat(),
    }
