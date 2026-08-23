from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from .config import MONGO_DB_NAME, MONGO_URI

_client: AsyncIOMotorClient = AsyncIOMotorClient(MONGO_URI)
db: AsyncIOMotorDatabase = _client[MONGO_DB_NAME]

situations_collection = db["situations"]
evidence_collection = db["evidence"]
