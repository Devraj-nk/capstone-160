"""Full pipeline: ingestion -> queue -> orchestrator (steps 2-12) ->
situations/evidence in MongoDB -> human review -> department routing.

Model hooks are stubbed by conftest.py (offline, deterministic); clustering
embeddings are stubbed here so cluster membership is controlled exactly.
"""

from __future__ import annotations

import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from app.analysis import clustering, need_detection
from app.db import find_documents
from app.evidence.ranking import select_representative_posts
from app.main import app
from app.pipeline import worker
from app.pipeline.orchestrator import orchestrator
from app.pipeline.routing import DEFAULT_DEPARTMENT, route_department
from app.preprocessing.cleaning import clean_text
from app.schemas.evidence import EvidencePost

client = TestClient(app)

FLOOD_POSTS = [
    "Flood water entering homes near MG Road, send help, call 9876543210",
    "MG Road flooded, people trapped, need rescue boats",
    "Water level rising fast at MG Road, urgent help needed",
]
FIRE_POST = "Fire spreading near the market"


# Similar (cosine 0.8) but not near-duplicate (< 0.92) flood vectors, so the
# flood posts cluster together yet count as independent reports.
FLOOD_VECTORS = {
    FLOOD_POSTS[0]: [1.0, 0.0, 0.5, 0.0],
    FLOOD_POSTS[1]: [1.0, 0.0, 0.0, 0.5],
    FLOOD_POSTS[2]: [1.0, 0.0, -0.5, 0.0],
}


@pytest.fixture(autouse=True)
def topic_embeddings(monkeypatch):
    """Flood posts share one direction, everything else another."""

    def embed(text: str) -> list[float]:
        lowered = text.lower()
        if any(w in lowered for w in ("flood", "water")):
            return FLOOD_VECTORS.get(text, [1.0, 0.0, 0.0, -0.5])
        return [0.0, 1.0, 0.0, 0.0]

    monkeypatch.setattr(clustering, "generate_embedding", embed)
    monkeypatch.setattr(
        need_detection,
        "_predict_need_probs",
        lambda text: {"healthcare": 0.05, "municipal": 0.92, "tourism": 0.01, "law": 0.02},
    )


def _ingest(text: str, tweet_id: str, created_at: float) -> None:
    response = client.post(
        "/ingestion/ingest",
        json={"text": text, "created_at": created_at, "attributes": {"tweet_id": tweet_id, "location": "MG Road"}},
    )
    assert response.status_code == 200


def test_queued_posts_become_a_scored_routed_situation():
    base = 1_780_000_000.0
    for i, text in enumerate(FLOOD_POSTS):
        _ingest(text, f"f{i}", base + i * 60)
    _ingest(FIRE_POST, "x1", base + 300)

    body = client.post("/pipeline/drain").json()
    assert body["processed"] == 4
    assert body["remaining"] == 0
    assert body["stages"] == {"holding": 3, "situation": 1}

    situations = client.get("/situations?status=pending").json()
    assert len(situations) == 1
    situation = situations[0]
    assert situation["post_count"] == 3
    assert situation["department"] == "Public Municipal"
    assert situation["needs"]["active"] == ["municipal"]
    assert situation["priority"]["band"] in {"Critical", "High", "Medium", "Low"}
    assert 0.0 <= situation["priority"]["priority_score"] <= 1.0
    assert 0.0 <= situation["fake_news"]["fake_score"] <= 1.0
    # Step 10: template summary, representative post, explained evidence.
    assert situation["summary"] == (
        "Flooding reported: people trapped, people asking for urgent help. "
        "3 independent reports in 1 language over the last hour. Main need: Municipal."
    )
    assert situation["summary_method"] == "template_v1"
    assert set(situation["summary_i18n"]) == {"en", "hi", "kn", "ta", "te"}
    assert situation["summary_i18n"]["en"] == situation["summary"]
    assert situation["evidence_version"] == "v1"
    assert situation["representative"]["tweet_id"] in {"f0", "f1", "f2"}
    assert situation["text"] == situation["representative"]["text"]
    assert len(situation["evidence"]) == 3
    scores = [e["score"] for e in situation["evidence_posts"]]
    assert scores == sorted(scores, reverse=True)
    for item in situation["evidence_posts"]:
        assert item["lang"] == "en"
        assert item["text_en"] == item["text"]  # English needs no translation
        assert 1 <= len(item["why"]) <= 2

    # Evidence is privacy-masked everywhere it lands.
    stored = client.get(f"/situations/{situation['id']}/evidence").json()
    assert [e["post_id"] for e in stored] == situation["evidence"]
    assert asyncio.run(find_documents("evidence", {})) == []  # no second copy outside the situation
    for item in stored + situation["evidence_posts"]:
        assert "9876543210" not in item["text"]
        assert item["metadata"]["location"] == "[ADDRESS_REDACTED]"
    tweets = asyncio.run(find_documents("tweets", {}))
    assert len(tweets) == 4
    assert all("9876543210" not in t["text"] and "9876543210" not in t["text_raw"] for t in tweets)

    # Human review: approve routes to the department (one ticket) and stores a verdict.
    decided = client.post(
        f"/situations/{situation['id']}/decision", json={"decision": "approve", "note": "verified by phone"}
    ).json()
    assert decided["status"] == "confirmed"
    assert decided["routed_to"] == "Public Municipal"
    assert decided["routed_at"] is not None
    verdicts = asyncio.run(find_documents("verdicts", {"situation_id": situation["id"]}))
    assert verdicts[0]["verdict"] == "true"
    assert verdicts[0]["note"] == "verified by phone"
    tickets = client.get("/tickets?department=Public Municipal").json()
    assert [t["situation_id"] for t in tickets] == [situation["id"]]

    summary = client.get("/analytics/summary").json()
    assert summary["confirmed"] == 1
    assert summary["by_department"] == {"Public Municipal": 1}


def test_new_posts_update_the_situation_but_keep_the_review_decision():
    base = 1_780_000_000.0
    for i, text in enumerate(FLOOD_POSTS):
        _ingest(text, f"f{i}", base + i * 60)
    client.post("/pipeline/drain")
    situation_id = client.get("/situations").json()[0]["id"]
    client.post(f"/situations/{situation_id}/decision", json={"decision": "reject"})

    _ingest("Flood at MG Road getting worse, water inside houses", "f9", base + 600)
    outcome = client.post("/pipeline/drain").json()["outcomes"][0]
    assert outcome["situation_id"] == situation_id
    assert outcome["situation_action"] == "updated"

    situations = client.get("/situations").json()
    assert len(situations) == 1
    assert situations[0]["post_count"] == 4
    assert situations[0]["status"] == "rejected"


def test_invalid_reposts_and_non_disaster_posts_stop_early(monkeypatch):
    from app.analysis import disaster_classification

    monkeypatch.setattr(
        disaster_classification,
        "_predict_disaster_probability",
        lambda text: 0.1 if "coffee" in text else 0.9,
    )
    _ingest("@@@ !!!", "a", 1.0)
    _ingest("Flood near the bridge, send help", "b", 2.0)
    _ingest("RT @someone: Flood near the bridge, send help", "c", 3.0)
    _ingest("just had coffee, nice weather", "d", 4.0)

    stages = [o["stage"] for o in client.post("/pipeline/drain").json()["outcomes"]]
    assert stages == ["invalid", "holding", "repost", "non_disaster"]
    stats = client.get("/pipeline/stats").json()
    assert stats["counts"]["received"] == 4
    assert stats["cluster_count"] == 1


def test_process_endpoint_runs_one_post_without_the_queue():
    body = client.post("/pipeline/process", json={"text": FIRE_POST, "attributes": {"tweet_id": "t1"}}).json()
    assert body["stage"] == "holding"
    assert body["post_id"] == "t1"
    assert body["record"]["is_disaster"] is True
    assert client.get("/queue/stats").json()["queue_size"] == 0


def test_a_failing_model_is_reported_not_raised(monkeypatch):
    from app.analysis import sentiment

    def boom(text):
        raise RuntimeError("model offline")

    monkeypatch.setattr(sentiment, "_predict_sentiment_probs", boom)
    body = client.post("/pipeline/process", json={"text": FIRE_POST}).json()
    assert body["stage"] == "error"
    assert "model offline" in body["error"]
    assert client.get("/pipeline/stats").json()["last_error"] == "RuntimeError: model offline"


def test_background_worker_drains_the_queue(monkeypatch):
    async def run() -> None:
        worker.start(orchestrator, poll_interval=0.01)
        assert worker.is_running()
        deadline = time.monotonic() + 5
        while orchestrator.stats["received"] < 3 and time.monotonic() < deadline:
            await asyncio.sleep(0.02)
        await worker.stop()

    base = 1_780_000_000.0
    for i, text in enumerate(FLOOD_POSTS):
        _ingest(text, f"f{i}", base + i)
    asyncio.run(run())

    assert not worker.is_running()
    assert client.get("/queue/stats").json()["queue_size"] == 0
    assert orchestrator.stats["situations_created"] == 1


# --- Pieces the orchestrator relies on ---


def test_clean_text_keeps_indic_vowel_signs_and_viramas():
    assert clean_text("भारी बारिश के कारण सड़क बंद है, मदद चाहिए!!") == "भारी बारिश के कारण सड़क बंद है, मदद चाहिए!!"
    assert clean_text("ನಮ್ಮ ಪ್ರದೇಶದಲ್ಲಿ ನೀರು ತುಂಬಿದೆ #flood") == "ನಮ್ಮ ಪ್ರದೇಶದಲ್ಲಿ ನೀರು ತುಂಬಿದೆ flood"
    assert clean_text("வெள்ளம் — உதவி தேவை") == "வெள்ளம் உதவி தேவை"


def test_route_department_picks_strongest_need_above_threshold():
    assert route_department({"healthcare": 0.7, "municipal": 0.9, "law": 0.1, "tourism": 0.0}) == (
        "Public Municipal",
        ["municipal", "healthcare"],
    )
    # municipal 0.75 is below its 0.80 threshold; healthcare 0.70 clears 0.65
    assert route_department({"healthcare": 0.70, "municipal": 0.75}) == ("Healthcare", ["healthcare"])
    assert route_department({"healthcare": 0.1, "municipal": 0.2}) == (DEFAULT_DEPARTMENT, [])


def test_evidence_ranking_orders_by_score_with_stable_unscored_fallback():
    posts = [
        EvidencePost(id="a", text="a", cluster_id="c"),
        EvidencePost(id="b", text="b", cluster_id="c", score=0.4),
        EvidencePost(id="c", text="c", cluster_id="c", score=0.9),
        EvidencePost(id="d", text="d", cluster_id="c", score=0.4),
        EvidencePost(id="e", text="e", cluster_id="c"),
    ]
    ranked = [item.post_id for item in select_representative_posts(posts, top_k=5)]
    assert ranked == ["c", "b", "d", "a", "e"]
