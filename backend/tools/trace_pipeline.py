"""Run a readable offline trace of the main crisis-monitoring pipeline.

This is intentionally separate from pytest. Run it from backend/ with:
    python tools/trace_pipeline.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from mongomock_motor import AsyncMongoMockClient
from fastapi.testclient import TestClient

# Allow the script to work when invoked directly from backend/.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app import db as db_module
from app.analysis import clustering, disaster_classification, need_detection, sentiment
from app.main import app
from app.preprocessing import deduplication, language
from app.routers import queue as queue_module
from tests.test_data import MESSY_POST


client = TestClient(app)


def show(stage: str, label: str, value: object) -> None:
    print(f"\n[{stage}] {label}")
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def request(stage: str, method: str, path: str, payload: object) -> dict:
    show(stage, "INPUT", payload)
    response = client.request(method, path, json=payload)
    body = response.json()
    show(stage, f"OUTPUT ({response.status_code})", body)
    if response.status_code >= 400:
        raise RuntimeError(f"{method} {path} failed with status {response.status_code}")
    return body


def reset_state() -> None:
    db_module.db = AsyncMongoMockClient()["trace_db"]
    queue_module._queue.clear()
    deduplication._repost_counts.clear()
    clustering.manager.clear()


def install_offline_models() -> None:
    language._predict_with_classifier = lambda text: "en"
    disaster_classification._predict_disaster_probability = lambda text: 0.9
    sentiment._predict_sentiment_probs = lambda text: [0.9, 0.1]
    need_detection._predict_need_probs = lambda text: {
        "healthcare": 0.05,
        "municipal": 0.95,
        "tourism": 0.01,
        "law": 0.01,
    }

    def embedding_for(text: str) -> list[float]:
        # Similar flood texts share a direction; the fire text gets another one.
        return [1.0, 0.0] if "flood" in text.lower() or "water" in text.lower() else [0.0, 1.0]

    clustering.generate_embedding = embedding_for


def main() -> None:
    reset_state()
    install_offline_models()

    print("=" * 72)
    print("OFFLINE PIPELINE TRACE")
    print("This is a separate trace runner; pytest is not being executed.")
    print("=" * 72)

    preprocess_input = {"text": MESSY_POST}
    preprocess_output = request("1. PREPROCESSING", "POST", "/preprocessing/preprocess", preprocess_input)

    combined_records: list[dict] = []
    source_posts = [
        ("flood-1", preprocess_output["text"], "2026-09-02T00:00:00+00:00"),
        ("flood-2", "Flood water is entering homes near MG Road, need help", "2026-09-02T01:00:00+00:00"),
        ("fire-1", "Fire spreading near the market, send help", "2026-09-02T02:00:00+00:00"),
    ]
    for tweet_id, text, created_at in source_posts:
        combined_records.append(
            request(
                "2. ANALYSIS",
                "POST",
                "/analysis/pipeline",
                {"tweet_id": tweet_id, "text": text, "created_at": created_at},
            )
        )

    cluster_input = [
        {
            "id": record["tweet_id"],
            "text": record["text"],
            "created_at": record["created_at"],
            "needs": record["needs"],
            "metadata": {"severity": record["severity"]},
        }
        for record in combined_records
    ]
    cluster_output = request("3. CLUSTERING", "POST", "/clustering/assign", cluster_input)

    evidence_input = [
        {
            "id": post["id"],
            "text": post["text"],
            "cluster_id": post["cluster_id"],
            "metadata": post["metadata"],
        }
        for post in cluster_output["posts"]
    ]
    evidence_output = request(
        "4. EVIDENCE EXTRACTION",
        "POST",
        "/evidence/extract",
        {"posts": evidence_input, "top_k": 2},
    )

    stored_output = request(
        "5. EVIDENCE STORAGE",
        "POST",
        "/evidence/store",
        {"evidence": evidence_output["evidence"]},
    )
    stored_documents = asyncio.run(
        db_module.find_documents("evidence", {"id": stored_output["stored_ids"][0]})
    )
    show("5. EVIDENCE STORAGE", "STORED DOCUMENT", stored_documents[0])

    print("\nTrace completed successfully.")


if __name__ == "__main__":
    main()
