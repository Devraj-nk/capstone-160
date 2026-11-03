from __future__ import annotations

from collections import defaultdict

from ..schemas.evidence import EvidenceItem, EvidencePost


def select_representative_posts(posts: list[EvidencePost], top_k: int = 3) -> list[EvidenceItem]:
    """Per cluster, keep the top_k highest-scoring posts as evidence. Ties and
    unscored posts keep their input order (unscored posts rank last), so
    callers that don't score posts still get the first top_k. The pipeline
    itself uses the step-10 rules in app.scoring.summary_evidence."""
    clusters: dict[str, list[tuple[int, EvidencePost]]] = defaultdict(list)
    for index, post in enumerate(posts):
        clusters[post.cluster_id].append((index, post))

    evidence: list[EvidenceItem] = []
    for cluster_id, indexed_posts in clusters.items():
        ranked = sorted(
            indexed_posts,
            key=lambda pair: (pair[1].score is None, -(pair[1].score or 0.0), pair[0]),
        )
        for _, post in ranked[:top_k]:
            evidence.append(
                EvidenceItem(
                    post_id=post.id,
                    cluster_id=cluster_id,
                    text=post.text,
                    metadata=post.metadata,
                    score=post.score,
                )
            )
    return evidence
