"""Steps 9-10 for one cluster: cluster scoring (fake-news + priority), then
summary, representative post and evidence (app.scoring.summary_evidence), plus
department routing. Pure/sync — the orchestrator persists what this returns."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

import numpy as np

from ..analysis.clustering import Cluster
from ..evidence.privacy import mask_metadata, mask_personal_details
from ..schemas.evidence import EvidenceItem
from ..scoring import load_calibration, score_clusters, summarise_cluster
from .routing import route_department


@lru_cache(maxsize=1)
def _calibration() -> dict:
    return load_calibration()


def to_unix(value: str | float | int) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).timestamp()


def _round(value: float | None) -> float | None:
    return None if value is None else round(float(value), 4)


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _mask(text: str | None) -> str | None:
    return None if text is None else mask_personal_details(text)


def build_situation(cluster: Cluster, *, now: float | None = None) -> dict[str, Any]:
    """Returns {"situation": <Situation fields>, "evidence": [EvidenceItem]}.
    Text and metadata in both are already privacy-masked."""
    records = [
        {
            **member,
            "cluster_id": cluster.cluster_id,
            "embedding": np.asarray(embedding, dtype=float).tolist(),
            "created_at": to_unix(member["created_at"]),
        }
        for member, embedding in zip(cluster.members, cluster.embeddings)
    ]
    scored_clusters, tweet_feats = score_clusters(records, _calibration(), now=now)
    scored = scored_clusters[0]
    terms = scored["terms"]

    step10 = summarise_cluster(scored, records, tweet_feats, scored["dup_groups"])
    metadata_by_id = {str(r["tweet_id"]): r.get("metadata") or {} for r in records}
    evidence = [
        EvidenceItem(
            post_id=str(item["tweet_id"]),
            cluster_id=cluster.cluster_id,
            text=_mask(item["text"]),
            text_en=_mask(item["text_en"]),
            lang=item["lang"],
            score=item["score"],
            why=item["why"],
            metadata=mask_metadata(metadata_by_id.get(str(item["tweet_id"]), {})),
        )
        for item in step10["evidence"]
    ]
    representative = {
        **step10["representative"],
        "text": _mask(step10["representative"]["text"]),
        "text_en": _mask(step10["representative"]["text_en"]),
    }

    department, active_needs = route_department(scored["departments"])
    lang_counts = Counter(r.get("lang") for r in records if r.get("lang"))
    negativity = _mean([r["sentiment_negativity"] for r in records if r.get("sentiment_negativity") is not None])

    situation = {
        "cluster_id": cluster.cluster_id,
        "text": representative["text"],
        "language": lang_counts.most_common(1)[0][0] if lang_counts else None,
        "languages": scored["details"]["languages"],
        "post_count": len(records),
        "n_reports_unique": scored["details"]["n_reports_unique"],  # copies/translations count once
        "tweet_ids": [str(r["tweet_id"]) for r in records],
        "first_report_at": min(r["created_at"] for r in records),
        "last_report_at": max(r["created_at"] for r in records),
        "location": step10["summary"]["slots"]["location"],  # place name from the text, if any
        "sentiment": {
            "negativity": _round(negativity),
            "label": None if negativity is None else ("negative" if negativity >= 0.5 else "positive"),
        },
        "needs": {**scored["departments"], "active": active_needs},
        "fake_news": {
            "fake_score": scored["fake_score"],
            "likely_fake": scored["likely_fake"],
            "model_used": scored["fake_model_used"],
            "credibility": _round(terms["credibility"]),
            "content_risk": _round(terms["content_risk"]),
            "amplification_risk": _round(terms["amplification_risk"]),
        },
        "priority": {
            "priority_score": scored["priority"],
            "band": scored["band"],
            **{k: _round(terms[k]) for k in ("severity", "actionability", "corroboration", "credibility", "recency")},
        },
        "department": department,
        "summary": step10["summary"]["text_en"],
        "summary_i18n": step10["summary"]["text"],
        "summary_method": step10["summary"]["method"],
        "representative": representative,
        "evidence_posts": [item.model_dump() for item in evidence],
        "evidence_version": step10["evidence_version"],
        "signals": {"matched_terms": scored["matched_terms"], "details": scored["details"]},
    }
    return {"situation": situation, "evidence": evidence}
