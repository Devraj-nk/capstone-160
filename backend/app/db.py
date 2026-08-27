from __future__ import annotations

from typing import Any, Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection, AsyncIOMotorDatabase

from .config import MONGO_DB_NAME, MONGO_URI

_client: AsyncIOMotorClient = AsyncIOMotorClient(MONGO_URI)
db: AsyncIOMotorDatabase = _client[MONGO_DB_NAME]


def get_collection(name: str) -> AsyncIOMotorCollection:
    """Any named collection — situations, evidence, clusters, or whatever a
    future layer needs — without adding a new module-level binding here each time."""
    return db[name]


async def insert_document(collection_name: str, document: dict[str, Any]) -> str:
    await get_collection(collection_name).insert_one(document)
    return document["id"]


async def find_documents(
    collection_name: str, query: Optional[dict[str, Any]] = None, limit: int = 200
) -> list[dict[str, Any]]:
    cursor = get_collection(collection_name).find(query or {})
    return await cursor.to_list(length=limit)


async def find_one_document(collection_name: str, query: dict[str, Any]) -> Optional[dict[str, Any]]:
    return await get_collection(collection_name).find_one(query)


async def update_document(collection_name: str, query: dict[str, Any], update: dict[str, Any]) -> bool:
    result = await get_collection(collection_name).update_one(query, {"$set": update})
    return result.modified_count > 0


async def delete_document(collection_name: str, query: dict[str, Any]) -> bool:
    result = await get_collection(collection_name).delete_one(query)
    return result.deleted_count > 0
