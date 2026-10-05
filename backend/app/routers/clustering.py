from __future__ import annotations

from fastapi import APIRouter

from ..analysis.clustering import manager
from ..schemas.clustering import ClusterAssignment, ClusterPost, ClusterResponse, ReclusterResponse

router = APIRouter(prefix="/clustering", tags=["clustering"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/assign", response_model=ClusterResponse)
def assign(posts: list[ClusterPost]) -> ClusterResponse:
    assignments: list[ClusterAssignment] = []
    for post in posts:
        cluster, action, similarity = manager.assign_record(post.model_dump())
        assignments.append(
            ClusterAssignment(
                **post.model_dump(),
                cluster_id=cluster.cluster_id,
                cluster_action=action,
                similarity=similarity,
            )
        )

    situations, holding = manager.situations()
    return ClusterResponse(
        posts=assignments,
        cluster_count=len(manager.clusters),
        situation_count=len(situations),
        holding_count=len(holding),
    )


@router.post("/recluster", response_model=ReclusterResponse)
def recluster() -> ReclusterResponse:
    merges = manager.periodic_recluster()
    return ReclusterResponse(merges=merges, cluster_count=len(manager.clusters))
