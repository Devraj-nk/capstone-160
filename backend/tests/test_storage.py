"""Step 11 storage: tweets / dropped_tweets / situations (score history) /
verdicts / routing_tickets, indexes and privacy."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from pymongo.errors import DuplicateKeyError

from app.analysis import clustering, disaster_classification
from app.db import ensure_indexes, find_documents, find_one_document, insert_document
from app.evidence.privacy import hash_author, mask_personal_details, pseudonymize_attributes
from app.main import app
from app.pipeline.orchestrator import orchestrator
from app.schemas.situations import SCORE_HISTORY_LIMIT

client = TestClient(app)


def built(cluster_id="c1", priority=0.5, band="Medium", post_count=3, active=("municipal",)):
    """A minimal step 9-10 result, as situation_builder returns it."""
    return {
        "situation": {
            "cluster_id": cluster_id,
            "text": "Flood near Rajajinagar",
            "language": "en",
            "languages": ["en"],
            "post_count": post_count,
            "tweet_ids": [f"t{i}" for i in range(post_count)],
            "n_reports_unique": post_count,
            "first_report_at": 1_780_000_000.0,
            "last_report_at": 1_780_000_000.0 + 60 * post_count,
            "location": "Rajajinagar",
            "sentiment": {"negativity": 0.8, "label": "negative"},
            "needs": {"municipal": 0.9, "healthcare": 0.7, "active": list(active)},
            "fake_news": {"fake_score": 0.1, "likely_fake": False},
            "priority": {"priority_score": priority, "band": band},
            "department": "Public Municipal",
            "summary": f"Flooding reported. {post_count} independent reports.",
            "summary_i18n": {"en": f"Flooding reported. {post_count} independent reports."},
            "summary_method": "template_v1",
            "representative": {},
            "evidence_posts": [],
            "evidence_version": "v1",
            "signals": {},
        },
        "evidence": [],
    }


def upsert(**kwargs) -> str:
    situation_id, _ = asyncio.run(orchestrator._upsert_situation(built(**kwargs)))
    return situation_id


def situation(situation_id: str) -> dict:
    return asyncio.run(find_one_document("situations", {"id": situation_id}))


def decide(situation_id: str, decision: str) -> dict:
    response = client.post(f"/situations/{situation_id}/decision", json={"decision": decision})
    assert response.status_code == 200
    return response.json()


# --- situations: upsert + score history ---


def test_rescoring_upserts_one_document_and_caps_score_history():
    situation_id = upsert(priority=0.40)
    assert len(situation(situation_id)["score_history"]) == 1

    upsert(priority=0.61, band="High", post_count=4)
    doc = situation(situation_id)
    assert [h["priority"] for h in doc["score_history"]] == [0.40, 0.61]
    assert doc["score_history"][-1]["band"] == "High"
    assert len(asyncio.run(find_documents("situations", {}))) == 1

    for i in range(SCORE_HISTORY_LIMIT + 5):
        upsert(priority=0.5 + i / 100)
    history = situation(situation_id)["score_history"]
    assert len(history) == SCORE_HISTORY_LIMIT
    assert history[-1]["priority"] == pytest.approx(0.5 + (SCORE_HISTORY_LIMIT + 4) / 100)


def test_confirmed_situation_stays_confirmed_and_tickets_follow_rescoring():
    situation_id = upsert(priority=0.60, band="High")
    decide(situation_id, "approve")

    upsert(priority=0.80, band="Critical", post_count=6)
    doc = situation(situation_id)
    assert doc["status"] == "confirmed"
    assert doc["post_count"] == 6
    ticket = client.get("/tickets").json()[0]
    assert ticket["queue_priority"] == 0.80
    assert ticket["band"] == "Critical"
    assert ticket["summary_i18n"] == {"en": "Flooding reported. 6 independent reports."}


# --- verdicts ---


def test_verdict_snapshot_is_frozen_when_the_situation_is_rescored_later():
    situation_id = upsert(priority=0.55, band="High")
    decide(situation_id, "approve")
    upsert(priority=0.90, band="Critical", post_count=9)

    verdict = asyncio.run(find_documents("verdicts", {"situation_id": situation_id}))[0]
    assert verdict["verdict"] == "true"
    assert verdict["snapshot"]["priority"] == {"priority_score": 0.55, "band": "High"}
    assert verdict["snapshot"]["post_count"] == 3
    assert verdict["tweet_ids"] == ["t0", "t1", "t2"]


def test_mark_fake_sets_status_verdict_and_cancels_tickets():
    situation_id = upsert()
    decide(situation_id, "approve")
    body = decide(situation_id, "fake")

    assert body["status"] == "fake"
    assert body["routed_to"] is None
    verdicts = asyncio.run(find_documents("verdicts", {"situation_id": situation_id}))
    assert [v["verdict"] for v in verdicts] == ["true", "fake"]
    ticket = client.get("/tickets").json()[0]
    assert ticket["status"] == "cancelled"
    assert [e["status"] for e in ticket["history"]] == ["routed", "cancelled"]
    assert client.get("/analytics/summary").json()["fake"] == 1


# --- routing tickets ---


def test_one_ticket_per_needed_department_and_no_duplicates_on_reapproval():
    situation_id = upsert(active=("municipal", "healthcare"))
    decide(situation_id, "approve")
    decide(situation_id, "approve")

    tickets = client.get("/tickets").json()
    assert sorted(t["department"] for t in tickets) == ["Healthcare", "Public Municipal"]
    assert client.get("/tickets?department=Healthcare").json()[0]["situation_id"] == situation_id
    assert client.get("/analytics/summary").json()["open_tickets_by_department"] == {
        "Public Municipal": 1, "Healthcare": 1,
    }


def test_situation_without_active_need_routes_to_its_department():
    situation_id = upsert(active=())
    decide(situation_id, "approve")
    assert [t["department"] for t in client.get("/tickets").json()] == ["Public Municipal"]


def test_rejected_then_reapproved_situation_reopens_its_ticket():
    situation_id = upsert()
    decide(situation_id, "approve")
    decide(situation_id, "reject")
    assert client.get("/tickets").json()[0]["status"] == "cancelled"

    decide(situation_id, "approve")
    tickets = client.get("/tickets").json()
    assert len(tickets) == 1
    assert [e["status"] for e in tickets[0]["history"]] == ["routed", "cancelled", "routed"]


def test_ticket_lifecycle_and_invalid_transitions():
    decide(upsert(), "approve")
    ticket_id = client.get("/tickets").json()[0]["id"]

    acked = client.post(f"/tickets/{ticket_id}/status", json={"status": "acknowledged", "by": "bbmp_officer"})
    assert acked.status_code == 200
    last = acked.json()["history"][-1]
    assert (last["status"], last["by"]) == ("acknowledged", "bbmp_officer")
    assert client.post(f"/tickets/{ticket_id}/status", json={"status": "resolved"}).json()["status"] == "resolved"

    assert client.post(f"/tickets/{ticket_id}/status", json={"status": "acknowledged"}).status_code == 409
    assert client.post("/tickets/rt_missing/status", json={"status": "resolved"}).status_code == 404
    assert client.get("/tickets?status=resolved").json()[0]["id"] == ticket_id
    assert client.get("/analytics/summary").json()["open_tickets_by_department"] == {}


# --- tweets / dropped_tweets ---


def test_dropped_posts_are_logged_with_reason_detail_and_expiry(monkeypatch):
    monkeypatch.setattr(
        disaster_classification, "_predict_disaster_probability", lambda text: 0.1 if "coffee" in text else 0.9
    )
    monkeypatch.setattr(clustering, "generate_embedding", lambda text: [1.0, 0.0])
    for text in ("@@@ !!!", "Flood near the bridge, send help", "RT: Flood near the bridge, send help",
                 "just had coffee, nice weather"):
        client.post("/pipeline/process", json={"text": text})

    dropped = {d["reason"]: d for d in asyncio.run(find_documents("dropped_tweets", {}))}
    assert set(dropped) == {"invalid", "repost", "not_disaster"}
    assert dropped["repost"]["detail"] == {"repost_count": 2}
    assert dropped["not_disaster"]["detail"] == {"lang": "en", "disaster_confidence": 0.1, "threshold": 0.5}
    days_left = (dropped["invalid"]["expires_at"].replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)).days
    assert days_left in (6, 7)
    assert len(asyncio.run(find_documents("tweets", {}))) == 1
    assert client.get("/analytics/summary").json()["dropped_by_reason"] == {
        "invalid": 1, "repost": 1, "not_disaster": 1,
    }


def test_no_username_is_stored_only_a_salted_author_ref(monkeypatch):
    monkeypatch.setattr(clustering, "generate_embedding", lambda text: [1.0, 0.0])
    client.post(
        "/pipeline/process",
        json={"text": "Flood near the bridge, send help",
              "attributes": {"tweet_id": "t1", "user_id": "usr_101", "username": "ravi_kumar", "verified": "false"}},
    )
    tweet = asyncio.run(find_documents("tweets", {"id": "t1"}))[0]
    assert "usr_101" not in str(tweet) and "ravi_kumar" not in str(tweet)
    assert tweet["metadata"]["author_ref"].startswith("hash:")
    assert tweet["metadata"]["verified"] == "false"


def test_reprocessing_a_tweet_updates_instead_of_duplicating(monkeypatch):
    monkeypatch.setattr(clustering, "generate_embedding", lambda text: [1.0, 0.0])
    payload = {"text": "Flood near the bridge, send help", "attributes": {"tweet_id": "t1"}}
    client.post("/pipeline/process", json=payload)
    orchestrator.reset()  # e.g. a restart: repost counts are gone
    client.post("/pipeline/process", json=payload)
    assert len(asyncio.run(find_documents("tweets", {"id": "t1"}))) == 1


# --- privacy helpers ---


def test_phone_numbers_masked_but_small_counts_kept():
    text = mask_personal_details("Call 9876543210 or +91 98765 43210, water entered 20 houses")
    assert text == "Call [PHONE_REDACTED] or [PHONE_REDACTED], water entered 20 houses"


def test_author_hash_is_stable_one_way_and_replaces_all_user_fields():
    assert hash_author("usr_101") == hash_author("usr_101") != hash_author("usr_102")
    assert pseudonymize_attributes({"user_id": "usr_101", "handle": "@x", "followers_count": "120"}) == {
        "followers_count": "120",
        "author_ref": hash_author("usr_101"),
    }


# --- indexes ---


def test_ensure_indexes_enforces_unique_cluster_and_ticket_keys():
    asyncio.run(ensure_indexes())
    asyncio.run(ensure_indexes())  # idempotent
    asyncio.run(insert_document("situations", {"id": "s1", "cluster_id": "c1", "text": ""}))
    with pytest.raises(DuplicateKeyError):
        asyncio.run(insert_document("situations", {"id": "s2", "cluster_id": "c1", "text": ""}))
    asyncio.run(insert_document("routing_tickets", {"id": "r1", "situation_id": "s1", "department": "Healthcare"}))
    with pytest.raises(DuplicateKeyError):
        asyncio.run(insert_document("routing_tickets", {"id": "r2", "situation_id": "s1", "department": "Healthcare"}))
