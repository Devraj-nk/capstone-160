"""End-to-end checks of the pipeline as currently implemented: ingestion ->
preprocessing (clean / validity / repost tracking) -> evidence extraction ->
privacy-masked evidence storage -> the dynamic DB layer underneath it all.

Run with `pytest` from backend/ (or click a test in your editor's test
runner) — no real network or MongoDB connection required.
"""

from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from app.db import find_documents, insert_document
from app.main import app
from app.schemas.situations import Situation
from tests.test_data import (
    CLUSTERED_POSTS,
    EMPTY_POSTS,
    MESSY_POST,
    ORIGINAL_POST,
    PII_POST,
    RETWEET_OF_ORIGINAL,
    SIMILAR_BUT_DISTINCT_POST,
)

client = TestClient(app)


# --- Ingestion ---


def test_ingestion_enqueues_a_raw_post():
    response = client.post("/ingestion/ingest", json={"text": "Flooding reported near river bridge"})
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["queue_item_id"]

    stats = client.get("/queue/stats").json()
    assert stats["queue_size"] == 1


# --- Preprocessing: cleaning ---


def test_preprocess_cleans_urls_mentions_hashtags_and_emoji():
    response = client.post("/preprocessing/preprocess", json={"text": MESSY_POST})
    assert response.status_code == 200
    body = response.json()

    assert "https://" not in body["text"]
    assert "@DisasterMgmt" not in body["text"]
    assert "#" not in body["text"]
    assert "water wave" in body["text"]  # decoded emoji, not dropped
    assert "Bangalore" in body["text"]
    assert body["is_valid"] is True


# --- Preprocessing: invalid/empty ---


def test_preprocess_flags_empty_and_symbol_only_posts_invalid():
    for post in EMPTY_POSTS:
        body = client.post("/preprocessing/preprocess", json={"text": post}).json()
        assert body["is_valid"] is False


# --- Preprocessing: repost tracking ---


def test_preprocess_tracks_and_drops_reposts():
    first = client.post("/preprocessing/preprocess", json={"text": ORIGINAL_POST}).json()
    assert first["repost_count"] == 1
    assert first["dropped"] is False

    repost = client.post("/preprocessing/preprocess", json={"text": RETWEET_OF_ORIGINAL}).json()
    assert repost["repost_count"] == 2
    assert repost["dropped"] is True


def test_preprocess_leaves_similar_but_distinct_posts_alone():
    client.post("/preprocessing/preprocess", json={"text": ORIGINAL_POST})
    similar = client.post("/preprocessing/preprocess", json={"text": SIMILAR_BUT_DISTINCT_POST}).json()

    assert similar["repost_count"] == 1
    assert similar["dropped"] is False


# --- Evidence: extraction ---


def test_evidence_extract_returns_top_k_per_cluster():
    response = client.post("/evidence/extract", json={"posts": CLUSTERED_POSTS, "top_k": 2})
    assert response.status_code == 200
    evidence = response.json()["evidence"]

    assert {item["cluster_id"] for item in evidence} == {"flood-blr", "fire-market"}
    flood_ids = {item["post_id"] for item in evidence if item["cluster_id"] == "flood-blr"}
    assert flood_ids == {"p1", "p2"}  # top 2 kept, off-topic p3 dropped


# --- Evidence: privacy-masked storage ---


def test_evidence_store_masks_pii_before_persisting():
    extract_body = client.post(
        "/evidence/extract",
        json={"posts": [{"id": "pii1", "text": PII_POST, "cluster_id": "test-cluster"}], "top_k": 1},
    ).json()

    store_response = client.post("/evidence/store", json={"evidence": extract_body["evidence"]})
    assert store_response.status_code == 200
    stored_ids = store_response.json()["stored_ids"]
    assert len(stored_ids) == 1

    docs = asyncio.run(find_documents("evidence", {"id": stored_ids[0]}))
    assert len(docs) == 1
    stored_text = docs[0]["text"]
    assert "9876543210" not in stored_text
    assert "123 MG Road" not in stored_text
    assert "[PHONE_REDACTED]" in stored_text
    assert "[ADDRESS_REDACTED]" in stored_text


# --- Dynamic DB layer / Situations ---


def test_situations_endpoint_reads_through_the_dynamic_db_layer():
    situation = Situation(text="Fire reported near the market", department="Disaster Management")
    asyncio.run(insert_document("situations", situation.model_dump()))

    response = client.get("/situations")
    assert response.status_code == 200
    situations = response.json()
    assert any(s["id"] == situation.id for s in situations)
