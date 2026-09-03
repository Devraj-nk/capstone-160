from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from mongomock_motor import AsyncMongoMockClient

from app import db as db_module
from app.analysis import disaster_classification, need_detection, sentiment
from app.preprocessing import deduplication, language
from app.routers import queue as queue_module


@pytest.fixture(autouse=True)
def mock_database(monkeypatch):
    """Every test gets its own in-memory Mongo — no real Atlas connection,
    no state leaking between tests."""
    mock_client = AsyncMongoMockClient()
    mock_db = mock_client["test_db"]
    monkeypatch.setattr(db_module, "db", mock_db)
    yield mock_db


@pytest.fixture(autouse=True)
def reset_in_memory_pipeline_state():
    """The Streaming Queue and the repost counter are module-level
    in-process state (by design, same as production) — reset both before
    each test so results don't depend on test order."""
    queue_module._queue.clear()
    deduplication._repost_counts.clear()
    yield


@pytest.fixture(autouse=True)
def mock_ml_inference(monkeypatch):
    """Every test gets safe, offline defaults for the four Hugging Face model
    calls (language classifier fallback, disaster gate, sentiment, need
    detection) — no real download/inference, same "safe by default" idea as
    mock_database above. Tests that care about specific model output
    override these with their own monkeypatch.setattr call."""
    monkeypatch.setattr(language, "_predict_with_classifier", lambda text: "en")
    monkeypatch.setattr(disaster_classification, "_predict_disaster_probability", lambda text: 0.8)
    monkeypatch.setattr(sentiment, "_predict_sentiment_probs", lambda text: [0.5, 0.5])
    monkeypatch.setattr(
        need_detection,
        "_predict_need_probs",
        lambda text: {"healthcare": 0.1, "municipal": 0.1, "tourism": 0.1, "law": 0.1},
    )
    yield
