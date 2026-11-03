"""Clustering state in MongoDB: a restart continues existing clusters (and
their situations) instead of opening duplicates."""

from __future__ import annotations

import asyncio

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.analysis import clustering, embedding, need_detection
from app.db import find_documents, find_one_document
from app.main import app
from app.pipeline.cluster_store import unpack_vector
from app.pipeline.orchestrator import orchestrator

client = TestClient(app)

BASE = 1_780_000_000.0
FLOOD = [
    ("f0", "Flood water entering homes near MG Road, send help"),
    ("f1", "MG Road flooded, people trapped, need rescue boats"),
    ("f2", "Water level rising fast at MG Road, urgent help needed"),
    ("f3", "Flood at MG Road getting worse, water inside houses"),
]
VECTORS = {
    FLOOD[0][1]: [1.0, 0.0, 0.5, 0.0],
    FLOOD[1][1]: [1.0, 0.0, 0.0, 0.5],
    FLOOD[2][1]: [1.0, 0.0, -0.5, 0.0],
    FLOOD[3][1]: [1.0, 0.0, 0.0, -0.5],
}


@pytest.fixture(autouse=True)
def stub_models(monkeypatch):
    monkeypatch.setattr(clustering, "generate_embedding", lambda text: VECTORS.get(text, [0.0, 1.0, 0.0, 0.0]))
    monkeypatch.setattr(
        need_detection, "_predict_need_probs",
        lambda text: {"healthcare": 0.05, "municipal": 0.92, "tourism": 0.01, "law": 0.02},
    )


def process(index: int, hours: float = 0.0) -> dict:
    tweet_id, text = FLOOD[index]
    body = {"text": text, "created_at": BASE + index * 60 + hours * 3600, "attributes": {"tweet_id": tweet_id}}
    return client.post("/pipeline/process", json=body).json()


def restart() -> int:
    """Simulate a backend restart: in-memory state gone, then the startup restore."""
    orchestrator.reset()
    return asyncio.run(orchestrator.restore_clusters())


def test_restart_continues_the_same_cluster_and_situation():
    first = [process(i) for i in range(3)]
    situation_id = first[-1]["situation_id"]
    cluster_id = first[-1]["cluster_id"]

    assert restart() == 1
    fourth = process(3)
    assert fourth["cluster_action"] == "joined_existing"
    assert fourth["cluster_id"] == cluster_id
    assert (fourth["situation_id"], fourth["situation_action"]) == (situation_id, "updated")

    situations = asyncio.run(find_documents("situations", {}))
    assert len(situations) == 1
    assert situations[0]["post_count"] == 4
    assert situations[0]["tweet_ids"] == ["f0", "f1", "f2", "f3"]


def test_without_restore_a_restart_would_open_a_duplicate_cluster():
    for i in range(3):
        process(i)
    orchestrator.reset()  # restart with no restore
    assert process(3)["cluster_action"] == "new_cluster"


def test_holding_cluster_survives_a_restart_and_becomes_a_situation():
    process(0)
    process(1)
    assert asyncio.run(find_documents("situations", {})) == []

    assert restart() == 1
    third = process(2)
    assert third["stage"] == "situation"
    assert third["situation_action"] == "created"
    assert asyncio.run(find_documents("situations", {}))[0]["post_count"] == 3


def test_vectors_are_stored_as_compact_float32():
    outcomes = [process(i) for i in range(3)]
    tweet = asyncio.run(find_one_document("tweets", {"id": "f1"}))
    assert isinstance(tweet["embedding"], bytes) and len(tweet["embedding"]) == 4 * 4  # 4 dims x float32
    stored = unpack_vector(tweet["embedding"])
    expected = np.asarray(VECTORS[FLOOD[1][1]]) / np.linalg.norm(VECTORS[FLOOD[1][1]])
    assert np.allclose(stored, expected, atol=1e-6)
    assert tweet["embedding_model"] == embedding.EMBEDDING_MODEL_ID

    doc = asyncio.run(find_one_document("clusters", {"id": outcomes[-1]["cluster_id"]}))
    assert (doc["size"], doc["dim"], doc["active"]) == (3, 4, True)
    assert doc["tweet_ids"] == ["f0", "f1", "f2"]
    assert doc["last_updated_at"] == BASE + 120
    member_vectors = [unpack_vector(t["embedding"]) for t in asyncio.run(find_documents("tweets", {}))]
    assert np.allclose(unpack_vector(doc["centroid"]), np.mean(member_vectors, axis=0), atol=1e-6)


def test_clusters_from_another_embedding_model_are_not_restored(monkeypatch):
    for i in range(3):
        process(i)
    monkeypatch.setattr(embedding, "EMBEDDING_MODEL_ID", "some-other-model")
    assert restart() == 0
    assert process(3)["cluster_action"] == "new_cluster"


def test_restore_is_idempotent():
    for i in range(3):
        process(i)
    restart()
    asyncio.run(orchestrator.restore_clusters())
    assert len(orchestrator.manager.clusters) == 1


def test_clusters_past_their_window_are_deactivated_and_their_embeddings_freed():
    flood_cluster = [process(i) for i in range(3)][-1]["cluster_id"]
    fire = client.post(
        "/pipeline/process",
        json={"text": "Fire spreading near the market", "created_at": BASE + 49 * 3600,
              "attributes": {"tweet_id": "x1"}},
    ).json()

    assert asyncio.run(orchestrator.prune_stale_clusters()) == 1
    assert [c.cluster_id for c in orchestrator.manager.clusters] == [fire["cluster_id"]]
    flood_doc = asyncio.run(find_one_document("clusters", {"id": flood_cluster}))
    assert flood_doc["active"] is False
    flood_tweets = asyncio.run(find_documents("tweets", {"cluster_id": flood_cluster}))
    assert all("embedding" not in t for t in flood_tweets)
    assert asyncio.run(find_one_document("tweets", {"id": "x1"}))["embedding"] is not None
    assert len(asyncio.run(find_documents("situations", {}))) == 1  # the situation itself stays

    assert restart() == 1  # only the fire cluster comes back
