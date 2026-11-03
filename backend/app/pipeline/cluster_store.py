"""Persist the clustering state so a restart continues existing clusters
instead of opening duplicates.

    clusters  one small document per live cluster: centroid (float32 bytes,
              ~3 KB for 768-d), member tweet ids, department relevance, times.
    tweets    each member's own embedding (float32 bytes) — needed to rescore
              (closeness to centre, copy detection), kept out of the cluster
              document so a big cluster can't hit Mongo's 16 MB limit.

A cluster can only accept posts inside its time window (48 h), so once it is
past that window its members' embeddings are removed and it is marked
inactive: stored vectors stay bounded to roughly two days of posts.
"""
from __future__ import annotations

import time
from typing import Any

import numpy as np

from ..analysis import embedding
from ..analysis.clustering import Cluster, ClusterManager
from ..db import CLUSTERS, TWEETS, find_documents, get_collection
from .situation_builder import to_unix

# Tweet-document fields that are storage extras, not part of the analysed record.
_NON_RECORD_FIELDS = ("_id", "id", "embedding", "embedding_model", "text_raw", "ingested_at", "processed_at")


def current_embedding_model() -> str:
    return embedding.EMBEDDING_MODEL_ID


def pack_vector(vector: Any) -> bytes:
    return np.asarray(vector, dtype=np.float32).tobytes()


def unpack_vector(data: bytes) -> np.ndarray:
    return np.frombuffer(bytes(data), dtype=np.float32).astype(float)


def cluster_document(cluster: Cluster) -> dict[str, Any]:
    return {
        "id": cluster.cluster_id,
        "centroid": pack_vector(cluster.centroid),
        "dim": int(np.asarray(cluster.centroid).shape[0]),
        "size": cluster.size,
        "tweet_ids": [str(m["tweet_id"]) for m in cluster.members],
        "dept_relevance": {k: float(v) for k, v in cluster.dept_relevance.items()},
        "created_at": to_unix(cluster.created_at),
        "last_updated_at": to_unix(cluster.last_updated_at),
        "embedding_model": current_embedding_model(),
        "active": True,
        "saved_at": time.time(),
    }


async def save_cluster(doc: dict[str, Any]) -> None:
    await get_collection(CLUSTERS).replace_one({"id": doc["id"]}, doc, upsert=True)


async def load_clusters(window_hours: float) -> tuple[list[Cluster], float | None]:
    """Rebuild the active clusters (same ids) from MongoDB. Returns
    (clusters, newest last_updated_at). Clusters built with another embedding
    model, outside the window, or with a member embedding missing are skipped."""
    docs = await find_documents(CLUSTERS, {"active": True}, limit=100_000)
    if not docs:
        return [], None
    newest = max(d["last_updated_at"] for d in docs)
    cutoff = newest - window_hours * 3600
    model = current_embedding_model()

    clusters: list[Cluster] = []
    for doc in sorted(docs, key=lambda d: d["created_at"]):
        if doc.get("embedding_model") != model or doc["last_updated_at"] < cutoff:
            continue
        tweets = {t["id"]: t for t in await find_documents(TWEETS, {"cluster_id": doc["id"]}, limit=100_000)}
        members = [tweets.get(tid) for tid in doc["tweet_ids"]]
        if not members or any(t is None or t.get("embedding") is None for t in members):
            continue
        embeddings = [unpack_vector(t["embedding"]) for t in members]
        clusters.append(
            Cluster(
                cluster_id=doc["id"],
                members=[{k: v for k, v in t.items() if k not in _NON_RECORD_FIELDS} for t in members],
                embeddings=embeddings,
                centroid=np.mean(embeddings, axis=0),
                created_at=doc["created_at"],
                last_updated_at=doc["last_updated_at"],
                dept_relevance=dict(doc.get("dept_relevance") or {}),
            )
        )
    return clusters, newest


async def deactivate_stale(cutoff: float) -> int:
    """Clusters whose last post is before `cutoff` can't grow any more: drop
    their member embeddings and mark them inactive (their situations stay)."""
    stale = await find_documents(CLUSTERS, {"active": True, "last_updated_at": {"$lt": cutoff}}, limit=100_000)
    for doc in stale:
        await get_collection(TWEETS).update_many({"cluster_id": doc["id"]}, {"$unset": {"embedding": ""}})
        await get_collection(CLUSTERS).update_one({"id": doc["id"]}, {"$set": {"active": False}})
    return len(stale)


def drop_stale_in_memory(manager: ClusterManager, cutoff: float) -> int:
    before = len(manager.clusters)
    manager.clusters = [c for c in manager.clusters if to_unix(c.last_updated_at) >= cutoff]
    return before - len(manager.clusters)
