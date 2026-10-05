from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ClusterPost(BaseModel):
    id: str
    text: str
    created_at: str | float | int
    needs: dict[str, float] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ClusterAssignment(BaseModel):
    id: str
    text: str
    created_at: str | float | int
    cluster_id: str
    cluster_action: str
    similarity: float | None = None
    needs: dict[str, float] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ClusterResponse(BaseModel):
    posts: list[ClusterAssignment]
    cluster_count: int
    situation_count: int
    holding_count: int


class ReclusterResponse(BaseModel):
    merges: int
    cluster_count: int
