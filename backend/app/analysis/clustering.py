from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
import uuid

import numpy as np

from ..scoring.lexicons import PLACE_NAMES
from ..scoring.text_utils import CompiledLexicon, tokenize
from .embedding import generate_embedding


DEFAULT_SIMILARITY_THRESHOLD = 0.32
DEFAULT_TIME_WINDOW_HOURS = 48.0
DEFAULT_MIN_CLUSTER_SIZE = 3
DEFAULT_DEPT_OVERLAP_THRESHOLD = 0.3


def _parse_timestamp(value: str | float | int) -> datetime:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


# Place guard: a post that names a place joins a cluster only if the cluster
# names the same place (or names none). Latin spellings only; native-script
# posts and posts without a place are matched on meaning alone.
_PLACE_LEX = CompiledLexicon({"all_latin": PLACE_NAMES["all_latin"]})
_PLACE_ALIASES = {"bengaluru": "bangalore", "mysuru": "mysore", "mangaluru": "mangalore", "vizag": "visakhapatnam"}


def place_names(text: str) -> set[str]:
    """Place names a post mentions, one spelling per place (Mysuru = Mysore)."""
    return {
        _PLACE_ALIASES.get(tok, tok)
        for tok in dict.fromkeys(tokenize(text or ""))
        if tok.isascii() and _PLACE_LEX.match([tok])
    }


def _needs(record: dict[str, Any]) -> dict[str, float]:
    values = record.get("needs", {})
    return {str(key): float(value) for key, value in values.items()}


@dataclass
class Cluster:
    cluster_id: str
    members: list[dict[str, Any]]
    embeddings: list[np.ndarray]
    centroid: np.ndarray
    created_at: str | float | int
    last_updated_at: str | float | int
    dept_relevance: dict[str, float] = field(default_factory=dict)
    _places: set[str] | None = field(default=None, repr=False, compare=False)  # cache, not stored

    @classmethod
    def from_record(cls, record: dict[str, Any], embedding: np.ndarray) -> Cluster:
        return cls(
            cluster_id=str(uuid.uuid4()),
            members=[record],
            embeddings=[embedding],
            centroid=embedding.copy(),
            created_at=record["created_at"],
            last_updated_at=record["created_at"],
            dept_relevance=_needs(record),
        )

    def add_member(self, record: dict[str, Any], embedding: np.ndarray) -> None:
        self.members.append(record)
        self.embeddings.append(embedding)
        self.centroid = np.mean(self.embeddings, axis=0)
        if _parse_timestamp(record["created_at"]) > _parse_timestamp(self.last_updated_at):
            self.last_updated_at = record["created_at"]
        for department, score in _needs(record).items():
            self.dept_relevance[department] = max(self.dept_relevance.get(department, 0.0), score)
        if self._places is not None:
            self._places |= place_names(record.get("text", ""))

    @property
    def places(self) -> set[str]:
        if self._places is None:
            self._places = set().union(*(place_names(m.get("text", "")) for m in self.members))
        return self._places

    @property
    def size(self) -> int:
        return len(self.members)


class ClusterManager:
    def __init__(
        self,
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        time_window_hours: float = DEFAULT_TIME_WINDOW_HOURS,
        min_cluster_size: int = DEFAULT_MIN_CLUSTER_SIZE,
        dept_overlap_threshold: float = DEFAULT_DEPT_OVERLAP_THRESHOLD,
    ) -> None:
        self.clusters: list[Cluster] = []
        self.similarity_threshold = similarity_threshold
        self.time_window_hours = time_window_hours
        self.min_cluster_size = min_cluster_size
        self.dept_overlap_threshold = dept_overlap_threshold

    def _department_overlap(self, cluster: Cluster, record: dict[str, Any]) -> bool:
        for department, score in _needs(record).items():
            if (
                score > self.dept_overlap_threshold
                and cluster.dept_relevance.get(department, 0.0) > self.dept_overlap_threshold
            ):
                return True
        return False

    def assign_record(
        self,
        record: dict[str, Any],
        embedding: np.ndarray | None = None,
    ) -> tuple[Cluster, str, float | None]:
        if not record.get("text"):
            raise ValueError("A record must contain non-empty text")
        if "created_at" not in record:
            raise ValueError("A record must contain created_at")

        vector = np.asarray(embedding if embedding is not None else generate_embedding(record["text"]), dtype=float)
        norm = np.linalg.norm(vector)
        if norm == 0:
            raise ValueError("Embedding must have a non-zero norm")
        vector = vector / norm

        best_cluster: Cluster | None = None
        best_similarity = -1.0
        record_time = _parse_timestamp(record["created_at"])
        record_places = place_names(record["text"])

        for cluster in self.clusters:
            similarity = float(np.dot(vector, cluster.centroid))
            time_gap = abs((record_time - _parse_timestamp(cluster.last_updated_at)).total_seconds()) / 3600
            if similarity < self.similarity_threshold or time_gap > self.time_window_hours:
                continue
            if not self._department_overlap(cluster, record):
                continue
            if record_places and cluster.places and not (record_places & cluster.places):
                continue  # names a different place: a different event
            if similarity > best_similarity:
                best_cluster = cluster
                best_similarity = similarity

        if best_cluster is None:
            cluster = Cluster.from_record(record, vector)
            self.clusters.append(cluster)
            return cluster, "new_cluster", None

        best_cluster.add_member(record, vector)
        return best_cluster, "joined_existing", round(best_similarity, 4)

    def periodic_recluster(self) -> int:
        if len(self.clusters) < 2:
            return 0

        try:
            import hdbscan
        except ImportError as exc:
            raise RuntimeError("Install hdbscan to use periodic reclustering") from exc

        centroids = np.asarray([cluster.centroid for cluster in self.clusters])
        labels = hdbscan.HDBSCAN(min_cluster_size=2, metric="euclidean").fit_predict(centroids)
        groups: dict[int, list[int]] = {}
        for index, label in enumerate(labels):
            if label != -1:
                groups.setdefault(int(label), []).append(index)

        merged_indices: set[int] = set()
        merges = 0
        for indices in groups.values():
            if len(indices) < 2:
                continue
            base = self.clusters[indices[0]]
            for index in indices[1:]:
                other = self.clusters[index]
                for record, embedding in zip(other.members, other.embeddings):
                    base.add_member(record, embedding)
                merged_indices.add(index)
                merges += 1

        self.clusters = [
            cluster for index, cluster in enumerate(self.clusters) if index not in merged_indices
        ]
        return merges

    def situations(self) -> tuple[list[Cluster], list[Cluster]]:
        situations = [cluster for cluster in self.clusters if cluster.size >= self.min_cluster_size]
        holding = [cluster for cluster in self.clusters if cluster.size < self.min_cluster_size]
        return situations, holding

    def clear(self) -> None:
        self.clusters.clear()


manager = ClusterManager()
