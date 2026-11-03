from __future__ import annotations

from typing import Any, Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING

from .config import MONGO_DB_NAME, MONGO_URI

_client: AsyncIOMotorClient = AsyncIOMotorClient(MONGO_URI)
db: AsyncIOMotorDatabase = _client[MONGO_DB_NAME]

# Collections (docs/Step 11 — Storage (MongoDB) Spec.pdf). "situations" is the
# spec's "clusters" collection: one document per event cluster.
TWEETS = "tweets"                    # posts that passed both gates, with model outputs
DROPPED_TWEETS = "dropped_tweets"    # posts removed by a gate, with the reason (TTL-expired)
CLUSTERS = "clusters"                # live clustering state: centroid, members, window (restored at startup)
SITUATIONS = "situations"            # one per cluster: scores, summary, evidence, review state
# Standalone evidence store for POST /evidence/store only; the pipeline keeps
# each cluster's evidence inside its situation document.
EVIDENCE = "evidence"
VERDICTS = "verdicts"                # human decisions with a frozen score snapshot
ROUTING_TICKETS = "routing_tickets"  # one per (situation, department), with lifecycle
DAILY_REPORTS = "daily_reports"      # one per day (IST): the stored daily situation report

# (collection, keys, options) — every query the console, routing and dashboard make.
INDEXES: list[tuple[str, list[tuple[str, int]], dict[str, Any]]] = [
    (TWEETS, [("id", ASCENDING)], {"unique": True}),
    (TWEETS, [("cluster_id", ASCENDING)], {}),
    (TWEETS, [("created_at", DESCENDING)], {}),
    (DROPPED_TWEETS, [("reason", ASCENDING), ("dropped_at", DESCENDING)], {}),
    (DROPPED_TWEETS, [("expires_at", ASCENDING)], {"expireAfterSeconds": 0}),  # retention TTL
    (CLUSTERS, [("id", ASCENDING)], {"unique": True}),
    (CLUSTERS, [("active", ASCENDING), ("last_updated_at", DESCENDING)], {}),
    (SITUATIONS, [("id", ASCENDING)], {"unique": True}),
    (SITUATIONS, [("cluster_id", ASCENDING)], {"unique": True}),
    (SITUATIONS, [("status", ASCENDING), ("priority.priority_score", DESCENDING)], {}),
    (SITUATIONS, [("updated_at", DESCENDING)], {}),
    (EVIDENCE, [("cluster_id", ASCENDING)], {}),
    (VERDICTS, [("situation_id", ASCENDING)], {}),
    (VERDICTS, [("decided_at", DESCENDING)], {}),
    (DAILY_REPORTS, [("id", ASCENDING)], {"unique": True}),
    (ROUTING_TICKETS, [("id", ASCENDING)], {"unique": True}),
    (ROUTING_TICKETS, [("situation_id", ASCENDING), ("department", ASCENDING)], {"unique": True}),
    (ROUTING_TICKETS, [("department", ASCENDING), ("status", ASCENDING), ("queue_priority", DESCENDING)], {}),
]


async def ensure_indexes() -> None:
    """Create all indexes (idempotent — existing ones are left as they are)."""
    for collection, keys, options in INDEXES:
        await get_collection(collection).create_index(keys, **options)


def get_collection(name: str) -> AsyncIOMotorCollection:
    """Any named collection — situations, evidence, clusters, or whatever a
    future layer needs — without adding a new module-level binding here each time."""
    return db[name]


async def insert_document(collection_name: str, document: dict[str, Any]) -> str:
    await get_collection(collection_name).insert_one(document)
    return document["id"]


async def find_documents(
    collection_name: str,
    query: Optional[dict[str, Any]] = None,
    limit: int = 200,
    projection: Optional[dict[str, Any]] = None,
) -> list[dict[str, Any]]:
    """`projection` e.g. {"embedding": 0} to skip large fields."""
    cursor = get_collection(collection_name).find(query or {}, projection)
    return await cursor.to_list(length=limit)


async def find_one_document(collection_name: str, query: dict[str, Any]) -> Optional[dict[str, Any]]:
    return await get_collection(collection_name).find_one(query)


async def update_document(collection_name: str, query: dict[str, Any], update: dict[str, Any]) -> bool:
    result = await get_collection(collection_name).update_one(query, {"$set": update})
    return result.modified_count > 0


async def delete_document(collection_name: str, query: dict[str, Any]) -> bool:
    result = await get_collection(collection_name).delete_one(query)
    return result.deleted_count > 0
