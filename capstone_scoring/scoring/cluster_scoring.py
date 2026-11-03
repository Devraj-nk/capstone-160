"""
Cluster-level scoring (step 8 of the pipeline):

  per tweet : ClusterConsistency -> Credibility
  per cluster: Corroboration, AmplificationRisk, Fake-Score, Recency, Priority, Band

Input: list of tweet records that already have `cluster_id` (from clustering)
and ideally `embedding` (IndicSBERT vector) and `created_at` (unix seconds).
"""
import math
from collections import defaultdict

import numpy as np

from . import config
from .text_utils import normalize
from .tweet_features import compute_tweet_features, weighted_sum


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _unit(v):
    v = np.asarray(v, dtype=float)
    n = np.linalg.norm(v)
    return v / n if n > 0 else v


def _scale(x, lo, hi):
    return float(min(1.0, max(0.0, (x - lo) / (hi - lo))))


def top_k_mean(values, k):
    vals = sorted((v for v in values if v is not None), reverse=True)[:k]
    return sum(vals) / len(vals) if vals else None


def priority_band(score: float) -> str:
    for name, lo in config.PRIORITY_BANDS:
        if score >= lo:
            return name
    return "Low"


class _UnionFind:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, i):
        while self.p[i] != i:
            self.p[i] = self.p[self.p[i]]
            i = self.p[i]
        return i

    def union(self, a, b):
        self.p[self.find(a)] = self.find(b)


# ---------------------------------------------------------------------------
# Cluster consistency (per tweet)
# ---------------------------------------------------------------------------
def cluster_consistency(members: list) -> list:
    """cosine(tweet embedding, cluster centroid) scaled to [0,1].
    IndicSBERT is multilingual, so a Kannada and an English report of the same
    flood both sit close to the centroid — this term is language-fair."""
    if all(m.get("sim_to_centroid") is not None for m in members):
        return [_scale(m["sim_to_centroid"], config.CONSISTENCY_LOW, config.CONSISTENCY_HIGH)
                for m in members]
    embs = [m.get("embedding") for m in members]
    if any(e is None for e in embs):
        return [None] * len(members)          # term skipped, weights re-normalized
    E = np.vstack([_unit(e) for e in embs])
    centroid = _unit(E.mean(axis=0))
    sims = E @ centroid
    return [_scale(float(s), config.CONSISTENCY_LOW, config.CONSISTENCY_HIGH) for s in sims]


def credibility(f: dict):
    return weighted_sum({
        "cluster_consistency": f.get("cluster_consistency"),
        "text_quality": f.get("text_quality"),
        "model_confidence": f.get("model_confidence"),
        "specificity": f.get("specificity"),
    }, config.CREDIBILITY_WEIGHTS)


# ---------------------------------------------------------------------------
# Report grouping: translations of one source + near-duplicate copies
# ---------------------------------------------------------------------------
def group_reports(members: list):
    """
    Step 1 — collapse dataset translation variants: tweets sharing `origin_id`
             (IndicTrans2 copies of the same source tweet) are ONE report.
             Not amplification — just how our replay data was built.
    Step 2 — near-duplicates among those reports (same text after
             normalization, or embedding cosine >= NEAR_DUP_COSINE, which also
             catches a message translated and re-forwarded across languages).
    Returns (report_idx, dup_groups): member indices kept after step 1, and
    groups of member indices that are copies of each other.
    """
    seen_origin, reports = {}, []
    for i, m in enumerate(members):
        oid = m.get("origin_id")
        if oid is not None:
            if oid in seen_origin:
                continue
            seen_origin[oid] = i
        reports.append(i)

    uf = _UnionFind(len(reports))
    texts = [normalize(members[i].get("text", "")) for i in reports]
    embs = [members[i].get("embedding") for i in reports]
    have_emb = all(e is not None for e in embs)
    E = np.vstack([_unit(e) for e in embs]) if (have_emb and reports) else None

    for a in range(len(reports)):
        for b in range(a + 1, len(reports)):
            same_text = texts[a] == texts[b] and texts[a] != ""
            close = E is not None and float(E[a] @ E[b]) >= config.NEAR_DUP_COSINE
            if same_text or close:
                uf.union(a, b)

    groups = defaultdict(list)
    for a in range(len(reports)):
        groups[uf.find(a)].append(reports[a])
    return reports, list(groups.values())


# ---------------------------------------------------------------------------
# Corroboration & amplification
# ---------------------------------------------------------------------------
def corroboration(members, feats, dup_groups) -> dict:
    """More INDEPENDENT reports -> stronger. Independent reports in DIFFERENT
    languages -> stronger still (different communities saw the same event).
    Copies and translations count once."""
    n_unique = len(dup_groups)
    volume = min(1.0, math.log1p(n_unique) / math.log1p(config.VOLUME_SATURATION))
    # one language per independent report; Hinglish counts as Hindi,
    # romanized Kannada as Kannada (same community, different keyboard)
    langs = {feats[g[0]]["lang"] for g in dup_groups}
    langs.discard("unknown")
    lang_div = min(1.0, max(0, len(langs) - 1) / max(1, config.LANG_DIVERSITY_SATURATION - 1))
    score = weighted_sum({"volume": volume, "language_diversity": lang_div},
                         config.CORROBORATION_WEIGHTS)
    return {"corroboration": score, "n_reports_unique": n_unique,
            "languages": sorted(langs), "co_volume": volume, "co_language_diversity": lang_div}


def amplification_risk(members, feats, report_idx, dup_groups) -> dict:
    """Copy-paste spread: many near-identical posts, posted fast, with
    'forward this' markers — in any language."""
    n = len(report_idx)
    dup_ratio = 1.0 - len(dup_groups) / n if n else 0.0

    copies_fast = 0
    for g in dup_groups:
        times = sorted(members[i].get("created_at") for i in g
                       if members[i].get("created_at") is not None)
        if len(times) > 1:
            copies_fast += sum(1 for t in times[1:] if t - times[0] <= config.COPY_BURST_WINDOW_SEC)
    copy_burst = copies_fast / n if n else 0.0

    forward_ratio = (sum(1 for i in report_idx if feats[i]["has_forward_marker"]) / n) if n else 0.0
    parts = {"duplicate_ratio": dup_ratio, "copy_burst": copy_burst, "forward_ratio": forward_ratio}
    return {"amplification_risk": weighted_sum(parts, config.AMPLIFICATION_WEIGHTS),
            **{f"am_{k}": v for k, v in parts.items()}}


def recency(latest_ts, now) -> float | None:
    if latest_ts is None or now is None:
        return None
    age_h = max(0.0, (now - latest_ts) / 3600.0)
    return 0.5 ** (age_h / config.RECENCY_HALF_LIFE_HOURS)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def score_clusters(tweets: list, cal: dict, now: float | None = None):
    """Returns (cluster_results, tweet_results)."""
    by_cluster = defaultdict(list)
    for t in tweets:
        cid = t.get("cluster_id")
        if cid is None or cid == -1:                  # HDBSCAN noise -> own singleton
            cid = f"single_{t.get('tweet_id')}"
        by_cluster[cid].append(t)

    if now is None:                                   # simulator time: latest post seen
        stamps = [t["created_at"] for t in tweets if t.get("created_at") is not None]
        now = max(stamps) if stamps else None

    cluster_results, tweet_results = [], []
    for cid, members in by_cluster.items():
        feats = [compute_tweet_features(m, cal) for m in members]
        report_idx, dup_groups = group_reports(members)
        consistency = cluster_consistency(members)
        if len(dup_groups) <= 1:                      # nothing independent to agree with
            consistency = [config.CONSISTENCY_NO_EVIDENCE] * len(members)
        for f, c in zip(feats, consistency):
            f["cluster_consistency"] = c
            f["credibility"] = credibility(f)
            f["cluster_id"] = cid

        # One vote per independent report: copies/translations don't vote twice
        rep_feats = [feats[g[0]] for g in dup_groups]

        sev = top_k_mean([f["severity"] for f in feats], config.CLUSTER_TOP_K)
        act = top_k_mean([f["actionability"] for f in feats], config.CLUSTER_TOP_K)
        cred_vals = [f["credibility"] for f in rep_feats if f["credibility"] is not None]
        cred = sum(cred_vals) / len(cred_vals) if cred_vals else None
        # Risk markers count in every report (a Hindi copy may add hearsay
        # words the English copy lacks), so use all reports here.
        cr_vals = [feats[i]["content_risk"] for i in report_idx]
        c_risk = sum(cr_vals) / len(cr_vals) if cr_vals else None
        fake_vals = [f["fake_prob"] for f in rep_feats if f["fake_prob"] is not None]
        fake_model = sum(fake_vals) / len(fake_vals) if fake_vals else None

        corr = corroboration(members, feats, dup_groups)
        amp = amplification_risk(members, feats, report_idx, dup_groups)
        latest = max((m.get("created_at") for m in members if m.get("created_at") is not None),
                     default=None)
        rec = recency(latest, now)

        fake_score = weighted_sum({
            "model": fake_model,
            "inv_credibility": None if cred is None else 1.0 - cred,
            "content_risk": c_risk,
            "amplification_risk": amp["amplification_risk"],
        }, config.FAKE_WEIGHTS)

        priority = weighted_sum({
            "severity": sev, "actionability": act, "corroboration": corr["corroboration"],
            "credibility": cred, "recency": rec,
        }, config.PRIORITY_WEIGHTS) or 0.0

        dept_scores = defaultdict(list)
        for m in members:
            for d, v in (m.get("needs") or {}).items():
                dept_scores[d].append(v)

        terms = defaultdict(set)
        for f in feats:
            for k, v in f["matched_terms"].items():
                terms[k].update(v)

        cluster_results.append({
            "cluster_id": cid,
            "n_tweets": len(members),
            "priority": round(priority, 4),
            "band": priority_band(priority),
            "fake_score": None if fake_score is None else round(fake_score, 4),
            "likely_fake": fake_score is not None and fake_score >= config.FAKE_FLAG_THRESHOLD,
            "fake_model_used": fake_model is not None,
            "terms": {
                "severity": sev, "actionability": act, "corroboration": corr["corroboration"],
                "credibility": cred, "recency": rec,
                "content_risk": c_risk, "amplification_risk": amp["amplification_risk"],
            },
            "details": {**{k: v for k, v in corr.items() if k != "corroboration"},
                        **{k: v for k, v in amp.items() if k != "amplification_risk"}},
            "departments": {d: round(sum(v) / len(v), 4) for d, v in dept_scores.items()},
            "matched_terms": {k: sorted(v) for k, v in terms.items()},
            "tweet_ids": [m.get("tweet_id") for m in members],
        })
        tweet_results.extend(feats)

    cluster_results.sort(key=lambda c: c["priority"], reverse=True)
    return cluster_results, tweet_results


def language_fairness_report(tweet_results: list) -> dict:
    """Mean of each tweet-level score per language. If one language is
    consistently lower on the SAME kind of content, a term is biased."""
    keys = ["text_quality", "specificity", "model_confidence", "credibility",
            "severity", "actionability"]
    acc = defaultdict(lambda: defaultdict(list))
    for f in tweet_results:
        for k in keys:
            if f.get(k) is not None:
                acc[f["lang_key"]][k].append(f[k])
    return {lang: {"n": max(len(v) for v in d.values()) if d else 0,
                   **{k: round(sum(v) / len(v), 3) for k, v in d.items()}}
            for lang, d in acc.items()}
