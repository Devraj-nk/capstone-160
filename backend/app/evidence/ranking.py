from __future__ import annotations

from collections import defaultdict

from ..schemas.evidence import EvidenceItem, EvidencePost


def select_representative_posts(posts: list[EvidencePost], top_k: int = 3) -> list[EvidenceItem]:
    """Per cluster, keep the first top_k posts as evidence. Clustering has
    already grouped similar posts together, so no extra ranking is needed here."""
    clusters: dict[str, list[EvidencePost]] = defaultdict(list)
    for post in posts:
        clusters[post.cluster_id].append(post)

    evidence: list[EvidenceItem] = []
    for cluster_id, cluster_posts in clusters.items():
        for post in cluster_posts[:top_k]:
            evidence.append(
                EvidenceItem(
                    post_id=post.id,
                    cluster_id=cluster_id,
                    text=post.text,
                    metadata=post.metadata,
                )
            )
    return evidence
