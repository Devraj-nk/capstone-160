from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from mongomock_motor import AsyncMongoMockClient

from app import db as db_module
from app.preprocessing import deduplication
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
