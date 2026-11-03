"""End-to-end pipeline: one ingested event in, posts/situations/evidence out.

    2 preprocess (clean, validate, repost dedup)
    4 language detection        3 disaster gate (needs the language)
    5 sentiment + need detection
    6 combine (severity, actionability)
    7-8 embedding + incremental clustering
    9-10 cluster scoring, summary + evidence, routing  (situation_builder)
    11 privacy-masked storage: tweets, dropped_tweets, situations (with their
       evidence + score history); open routing tickets follow rescoring

Steps 12-15 (review, routing tickets, dashboard) read what this writes.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from ..analysis import clustering, disaster_classification
from ..analysis.combine import combine_tweet_record
from ..analysis.disaster_classification import classify_disaster
from ..analysis.need_detection import detect_needs
from ..analysis.sentiment import analyze_sentiment
from ..config import DROPPED_RETENTION_DAYS
from ..db import DROPPED_TWEETS, SITUATIONS, TWEETS, find_one_document, get_collection, insert_document
from ..evidence.privacy import mask_metadata, mask_personal_details, pseudonymize_attributes
from ..preprocessing import deduplication
from ..preprocessing.cleaning import clean_text, is_valid_post
from ..preprocessing.language import detect_language_final
from ..schemas.situations import SCORE_HISTORY_LIMIT, Situation
from .cluster_store import (
    cluster_document,
    current_embedding_model,
    deactivate_stale,
    drop_stale_in_memory,
    load_clusters,
    pack_vector,
    save_cluster,
)
from .escalation import next_due
from .situation_builder import build_situation, to_unix
from .tickets import sync_ticket_priority

logger = logging.getLogger(__name__)

# Check for clusters past their time window every N processed posts.
PRUNE_EVERY = 100

# Pipeline stage -> dropped_tweets reason.
_DROP_REASON = {"invalid": "invalid", "repost": "repost", "non_disaster": "not_disaster"}
DROP_REASONS = tuple(_DROP_REASON.values())

# Fields a pipeline re-score may overwrite on an existing situation. Review
# state (status, decided_at, routed_*) and identity are never touched.
_RESCORED_FIELDS = (
    "text", "language", "languages", "post_count", "n_reports_unique", "tweet_ids", "first_report_at",
    "last_report_at", "location", "sentiment", "needs", "fake_news",
    "priority", "department", "summary", "summary_i18n", "summary_method", "representative", "evidence_posts",
    "evidence_version", "signals",
)


def _post_id(event: dict[str, Any]) -> str:
    attributes = (event.get("metadata") or {}).get("attributes") or {}
    for key in ("tweet_id", "post_id"):
        if attributes.get(key) not in (None, ""):
            return str(attributes[key])
    return str(event["id"])


class PipelineOrchestrator:
    def __init__(self, cluster_manager: clustering.ClusterManager | None = None) -> None:
        self.manager = cluster_manager or clustering.manager
        self.stats: Counter[str] = Counter()
        self.last_error: str | None = None
        self.model_backend = "hf"
        # Model calls and cluster mutation run in a worker thread; one post at
        # a time keeps the in-memory ClusterManager consistent.
        self._lock = threading.Lock()
        # Simulation clock for Recency: the newest post time seen so far, so
        # replayed historic data scores the same as live data.
        self._clock: float | None = None

    # -- sync part: steps 2-11 ------------------------------------------------

    def analyze(self, event: dict[str, Any]) -> dict[str, Any]:
        post_id = _post_id(event)
        outcome: dict[str, Any] = {"post_id": post_id, "ingested_id": event.get("id")}

        cleaned = clean_text(event["text"])
        if not is_valid_post(cleaned):
            return {**outcome, "stage": "invalid"}

        with self._lock:
            repost_count = deduplication.register_repost(cleaned)
            if repost_count > 1:
                return {**outcome, "stage": "repost", "repost_count": repost_count}

            lang_info = detect_language_final(cleaned)
            disaster = classify_disaster(cleaned, lang_info["lang"])
            created_at = event.get("created_at", time.time())
            base = {
                "tweet_id": post_id,
                "text": cleaned,
                "created_at": created_at,
                **lang_info,
                **disaster,
                # usernames / user ids never go further than this line
                "metadata": pseudonymize_attributes((event.get("metadata") or {}).get("attributes") or {}),
            }
            if not disaster["is_disaster"]:
                threshold = disaster_classification.PER_LANG_THRESHOLDS.get(
                    lang_info["lang"], disaster_classification.DEFAULT_THRESHOLD
                )
                return {**outcome, "stage": "non_disaster", "record": base, "threshold": threshold}

            sentiment = analyze_sentiment(cleaned)
            needs = detect_needs(cleaned)
            combined = combine_tweet_record(
                tweet_id=post_id,
                text=cleaned,
                lang=lang_info["lang"],
                is_disaster=disaster["is_disaster"],
                disaster_confidence=disaster["disaster_confidence"],
                created_at=created_at,
                sentiment=sentiment,
                needs=needs,
            )
            record = {
                **base,
                **combined,
                "sentiment_label": sentiment["sentiment_label"],
                "sentiment_confidence": sentiment["sentiment_confidence"],
            }

            cluster, action, similarity = self.manager.assign_record(record)
            ts = to_unix(created_at)
            self._clock = ts if self._clock is None else max(self._clock, ts)
            outcome.update(
                record=record,
                cluster_id=cluster.cluster_id,
                cluster_action=action,
                similarity=similarity,
                cluster_size=cluster.size,
                # snapshots for persistence, taken under the lock
                cluster_doc=cluster_document(cluster),
                embedding=pack_vector(cluster.embeddings[-1]),  # this post's vector
            )
            if cluster.size < self.manager.min_cluster_size:
                return {**outcome, "stage": "holding"}

            built = build_situation(cluster, now=self._clock)
            return {**outcome, "stage": "situation", **built}

    # -- async part: step 12 persistence --------------------------------------

    async def _store_tweet(self, event: dict[str, Any], outcome: dict[str, Any]) -> None:
        """A post that passed both gates. Upsert by id, so a re-run (e.g.
        replaying the CSV after a restart) never creates a duplicate."""
        record = outcome["record"]
        doc = {
            **record,
            "id": record["tweet_id"],
            "text": mask_personal_details(record["text"]),
            "text_raw": mask_personal_details(event["text"]),
            "metadata": mask_metadata(record.get("metadata") or {}),
            "ingested_at": event.get("ingested_at"),
            "cluster_id": outcome.get("cluster_id"),
            "embedding": outcome.get("embedding"),  # float32 bytes; removed once the cluster goes stale
            "embedding_model": current_embedding_model(),
            "processed_at": time.time(),
        }
        await get_collection(TWEETS).replace_one({"id": doc["id"]}, doc, upsert=True)
        await save_cluster(outcome["cluster_doc"])

    async def _store_dropped(self, event: dict[str, Any], outcome: dict[str, Any]) -> None:
        """A post removed before analysis, with the reason (dashboard gate
        statistics). Expires after DROPPED_RETENTION_DAYS via a TTL index."""
        stage = outcome["stage"]
        record = outcome.get("record") or {}
        detail: dict[str, Any] = {}
        if stage == "repost":
            detail = {"repost_count": outcome["repost_count"]}
        elif stage == "non_disaster":
            detail = {
                "lang": record.get("lang"),
                "disaster_confidence": record.get("disaster_confidence"),
                "threshold": outcome.get("threshold"),
            }
        now = datetime.now(timezone.utc)
        await insert_document(
            DROPPED_TWEETS,
            {
                "id": str(event.get("id") or uuid.uuid4()),
                "tweet_id": outcome["post_id"],
                "text": mask_personal_details(event["text"]),
                "reason": _DROP_REASON[stage],
                "detail": detail,
                "dropped_at": now.timestamp(),
                "expires_at": now + timedelta(days=DROPPED_RETENTION_DAYS),
            },
        )

    async def _upsert_situation(self, built: dict[str, Any]) -> tuple[str, str]:
        """One document per cluster. Summary, representative and evidence live
        inside it (`evidence_posts`; `evidence` = their tweet ids), so a
        rescore replaces them in the same write."""
        fields = built["situation"]
        cluster_id = fields["cluster_id"]
        existing = await find_one_document(SITUATIONS, {"cluster_id": cluster_id})
        situation_id = existing["id"] if existing else str(uuid.uuid4())

        evidence_ids = [item.post_id for item in built["evidence"]]
        now = time.time()
        history_entry = {
            "at": now,
            "priority": fields["priority"]["priority_score"],
            "band": fields["priority"]["band"],
            "post_count": fields["post_count"],
            "n_unique": fields["n_reports_unique"],
        }
        band = fields["priority"]["band"]
        if existing:
            update = {k: fields[k] for k in _RESCORED_FIELDS}
            update.update(
                evidence=evidence_ids,
                updated_at=now,
                escalation_due_at=next_due(existing.get("escalation_due_at"), band, now),
            )
            await get_collection(SITUATIONS).update_one(
                {"id": situation_id},
                {
                    "$set": update,
                    # keep only the last SCORE_HISTORY_LIMIT rescorings
                    "$push": {"score_history": {"$each": [history_entry], "$slice": -SCORE_HISTORY_LIMIT}},
                },
            )
            if existing.get("status") in ("confirmed", "auto_routed"):
                await sync_ticket_priority({**fields, "id": situation_id})
            action = "updated"
        else:
            situation = Situation(
                **fields, id=situation_id, evidence=evidence_ids,
                score_history=[history_entry], updated_at=now,
                escalation_due_at=next_due(None, band, now),
            )
            await insert_document(SITUATIONS, situation.model_dump())
            action = "created"
        return situation_id, action

    async def process_event(self, event: dict[str, Any]) -> dict[str, Any]:
        """Never raises — failures are counted and reported as stage "error"
        so the background worker keeps draining the queue."""
        self.stats["received"] += 1
        try:
            outcome = await asyncio.to_thread(self.analyze, event)
            if outcome["stage"] in _DROP_REASON:
                await self._store_dropped(event, outcome)
            else:
                await self._store_tweet(event, outcome)
            if outcome["stage"] == "situation":
                situation_id, action = await self._upsert_situation(outcome)
                outcome.update(situation_id=situation_id, situation_action=action)
                self.stats[f"situations_{action}"] += 1
            self.stats[outcome["stage"]] += 1
            if self.stats["received"] % PRUNE_EVERY == 0:
                await self.prune_stale_clusters()
            return outcome
        except Exception as exc:  # noqa: BLE001 — one bad post must not stop the stream
            logger.exception("Pipeline failed for event %s", event.get("id"))
            self.stats["error"] += 1
            self.last_error = f"{type(exc).__name__}: {exc}"
            return {"post_id": event.get("id"), "stage": "error", "error": self.last_error}

    # -- cluster persistence --------------------------------------------------

    async def restore_clusters(self) -> int:
        """Startup: reload active clusters (same ids) from MongoDB, so posts
        about an already-tracked event join it and update its situation."""
        clusters, newest = await load_clusters(self.manager.time_window_hours)
        with self._lock:
            known = {c.cluster_id for c in self.manager.clusters}
            self.manager.clusters.extend(c for c in clusters if c.cluster_id not in known)
            if newest is not None:
                self._clock = newest if self._clock is None else max(self._clock, newest)
        self.stats["clusters_restored"] += len(clusters)
        if clusters:
            logger.info("Restored %d active clusters from MongoDB", len(clusters))
        return len(clusters)

    async def prune_stale_clusters(self) -> int:
        """Clusters past their time window can't grow: free their stored member
        embeddings and drop them from memory (situations stay)."""
        if self._clock is None:
            return 0
        cutoff = self._clock - self.manager.time_window_hours * 3600
        with self._lock:
            drop_stale_in_memory(self.manager, cutoff)
        return await deactivate_stale(cutoff)

    def reset(self) -> None:
        """Clear in-memory state (clusters, repost counts, stats). Stored
        documents in MongoDB are left alone."""
        with self._lock:
            self.manager.clear()
            deduplication._repost_counts.clear()
            self.stats.clear()
            self.last_error = None
            self._clock = None


orchestrator = PipelineOrchestrator()


def summarize_outcome(outcome: dict[str, Any]) -> dict[str, Any]:
    """JSON-friendly view of an outcome (drops the bulky built situation)."""
    keys = (
        "post_id", "ingested_id", "stage", "repost_count", "cluster_id", "cluster_action",
        "similarity", "cluster_size", "situation_id", "situation_action", "error",
    )
    summary = {k: outcome[k] for k in keys if k in outcome}
    record = outcome.get("record")
    if record:
        summary["record"] = {k: v for k, v in record.items() if k != "metadata"}
    if "situation" in outcome:
        situation = outcome["situation"]
        summary["situation"] = {
            k: situation[k] for k in ("department", "summary", "priority", "fake_news", "post_count")
        }
    return summary
