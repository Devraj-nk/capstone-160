from __future__ import annotations

import numpy as np
import pytest
from datetime import datetime, timedelta, timezone

from app.analysis import clustering


def record(post_id: str, text: str, hour: int, needs: dict[str, float]) -> dict:
    return {
        "id": post_id,
        "text": text,
        "created_at": (datetime(2026, 9, 2, tzinfo=timezone.utc) + timedelta(hours=hour)).isoformat(),
        "needs": needs,
    }


def test_assign_record_joins_similar_posts_with_shared_department(monkeypatch):
    vectors = {
        "flood one": np.array([1.0, 0.0]),
        "flood two": np.array([0.98, 0.2]),
    }
    monkeypatch.setattr(clustering, "generate_embedding", lambda text: vectors[text])
    manager = clustering.ClusterManager(similarity_threshold=0.8)

    first = manager.assign_record(record("p1", "flood one", 0, {"municipal": 0.9}))
    second = manager.assign_record(record("p2", "flood two", 1, {"municipal": 0.8}))

    assert first[1] == "new_cluster"
    assert second[1] == "joined_existing"
    assert len(manager.clusters) == 1
    assert second[2] is not None


def test_assign_record_rejects_stale_cluster(monkeypatch):
    monkeypatch.setattr(clustering, "generate_embedding", lambda text: np.array([1.0, 0.0]))
    manager = clustering.ClusterManager(similarity_threshold=0.8, time_window_hours=48)

    manager.assign_record(record("p1", "flood", 0, {"municipal": 0.9}))
    manager.assign_record(record("p2", "flood again", 49, {"municipal": 0.9}))

    assert len(manager.clusters) == 2


def test_assign_record_requires_timestamp():
    manager = clustering.ClusterManager()
    with pytest.raises(ValueError, match="created_at"):
        manager.assign_record({"text": "flood", "needs": {}})


def test_posts_naming_different_places_do_not_merge(monkeypatch):
    # same meaning, same department, different cities -> separate events
    monkeypatch.setattr(clustering, "generate_embedding", lambda text: np.array([1.0, 0.0]))
    manager = clustering.ClusterManager(similarity_threshold=0.8)

    manager.assign_record(record("p1", "building collapsed in Kolkata, people trapped", 0, {"municipal": 0.9}))
    other_city = manager.assign_record(record("p2", "landslide in Mangaluru, people trapped", 1, {"municipal": 0.9}))
    same_city = manager.assign_record(record("p3", "Kolkata collapse, rescue teams needed", 1, {"municipal": 0.9}))
    no_place = manager.assign_record(record("p4", "people trapped under debris, send help", 1, {"municipal": 0.9}))

    assert other_city[1] == "new_cluster"
    assert same_city[1] == "joined_existing"
    assert no_place[1] == "joined_existing"
    assert len(manager.clusters) == 2


def test_place_spelling_variants_count_as_the_same_place():
    assert clustering.place_names("Flood in Mysuru") == clustering.place_names("flood in mysore") == {"mysore"}
    assert clustering.place_names("बाढ़ आई है") == set()  # native script: matched on meaning only
