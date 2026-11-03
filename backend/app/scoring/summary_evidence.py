"""
Step 10 — summary & evidence for one scored cluster.

Runs after cluster scoring (step 9) and reuses its per-tweet features and copy
groups (`dup_groups`), so nothing is computed twice. No model is used:

  summary        template filled only from computed fields (summary_slots),
                 written in en/hi/kn/ta/te (summary_templates); a slot with no
                 data is left out, so it never states something unsupported
                 (an abstractive model can invent places/counts).
  representative the original report closest to the cluster centre.
  evidence       3-5 independent posts: EvidenceScore = 0.6·Similarity +
                 0.4·PostStrength, one per copy group, forward-chain posts
                 skipped, languages spread, each with a `why`.
"""
import time
from collections import Counter

from . import config
from .lexicons import EVENT, IMPACT, PLACE_NAMES
from .summary_templates import SUMMARY_LANGUAGES, render_summary
from .text_utils import CompiledLexicon, tokenize
from .translate import translate_to_en
from .tweet_features import weighted_sum

EVENT_LEX = {name: CompiledLexicon(forms) for name, forms in EVENT.items()}
IMPACT_LEX = {phrase: CompiledLexicon(forms) for phrase, forms in IMPACT.items()}
PLACE_LEX = CompiledLexicon(PLACE_NAMES)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _originals(members: list, dup_groups: list) -> list[int]:
    """One member index per copy group: the earliest post (input order breaks ties)."""
    inf = float("inf")
    return [min(g, key=lambda i: (members[i].get("created_at") or inf, i)) for g in dup_groups]


def _clean_reports(members, feats, dup_groups) -> list[int]:
    """Originals without forward-chain words, unless every report has them
    (then all are kept, so the reviewer sees the rumour pattern)."""
    originals = _originals(members, dup_groups)
    clean = [i for i in originals if not feats[i].get("has_forward_marker")]
    return clean or originals


def _evidence_score(f: dict) -> tuple:
    strength = weighted_sum({k: f.get(k) for k in config.POST_STRENGTH_WEIGHTS},
                            config.POST_STRENGTH_WEIGHTS)
    score = weighted_sum({"similarity": f.get("similarity"), "strength": strength},
                         config.EVIDENCE_WEIGHTS)
    return (None if score is None else round(score, 4)), strength


def _most_frequent(lexicons: dict, texts: list[str]):
    """Key of the lexicon matched by the most texts (dict order breaks ties)."""
    counts = Counter()
    for text in texts:
        tokens = tokenize(text)
        for key, lex in lexicons.items():
            if lex.match(tokens):
                counts[key] += 1
    if not counts:
        return None
    top = max(counts.values())
    return next(key for key in lexicons if counts[key] == top)


def _location(texts: list[str]):
    """Most frequent place-name token; Latin spellings preferred for the
    English sentence, native-script ones used only if nothing else matched."""
    latin, native = Counter(), Counter()
    for text in texts:
        for tok in dict.fromkeys(tokenize(text)):          # each place once per report
            if PLACE_LEX.match([tok]):
                (latin if tok.isascii() else native)[tok] += 1
    for counts, fmt in ((latin, str.title), (native, str)):
        if counts:
            top = max(counts.values())
            return fmt(next(t for t in counts if counts[t] == top))
    return None


def _span(members: list, report_idx: list):
    stamps = [members[i]["created_at"] for i in report_idx
              if isinstance(members[i].get("created_at"), (int, float))]
    if len(stamps) < 2 or max(stamps) == min(stamps):
        return None
    hours = (max(stamps) - min(stamps)) / 3600
    if hours < 1.5:
        return ("hour", 1)
    if hours < 36:
        return ("hours", round(hours))
    return ("days", round(hours / 24))


# ---------------------------------------------------------------------------
# Spec functions
# ---------------------------------------------------------------------------
def select_evidence(members: list, feats: list, dup_groups: list) -> list[dict]:
    """Apply the selection rules; return evidence items with tweet_id, lang,
    score, text, why. Same input -> same output."""
    candidates = _clean_reports(members, feats, dup_groups)
    scores = {i: _evidence_score(feats[i]) for i in candidates}
    ranked = sorted(candidates, key=lambda i: (scores[i][0] is None, -(scores[i][0] or 0.0), i))
    k = min(config.EVIDENCE_MAX, len(ranked))
    # "closest to event" goes to exactly one post (scaled similarity caps at 1.0, so ties
    # are common): the most similar, best-ranked among ties.
    with_sim = [i for i in ranked if feats[i].get("similarity") is not None]
    closest = max(with_sim, key=lambda i: feats[i]["similarity"]) if len(with_sim) > 1 else None

    items, picked, lang_count = [], set(), Counter()
    while len(items) < k:
        remaining = [i for i in ranked if i not in picked]
        # Rule 3: best score first, then prefer a language not yet shown,
        # at most EVIDENCE_PER_LANG per language while others remain.
        unseen = [i for i in remaining if lang_count[feats[i]["lang"]] == 0]
        under_cap = [i for i in remaining if lang_count[feats[i]["lang"]] < config.EVIDENCE_PER_LANG]
        choice = (unseen or under_cap or remaining)[0]
        f = feats[choice]
        new_language = bool(items) and lang_count[f["lang"]] == 0
        picked.add(choice)
        lang_count[f["lang"]] += 1

        why = []
        if choice == closest:
            why.append("closest to event")
        if new_language:
            why.append("different language")
        if f.get("sp_location") and f.get("sp_number"):
            why.append("location + number")
        elif f.get("sp_location"):
            why.append("location")
        if f.get("urgency_kw"):
            why.append("urgency words")
        items.append({
            "tweet_id": members[choice].get("tweet_id"),
            "lang": f["lang"],
            "score": scores[choice][0],
            "text": members[choice].get("text", ""),
            "why": (why or ["highest score" if not items else "supporting report"])[:2],
        })
    return items


def pick_representative(members: list, feats: list, dup_groups: list) -> dict:
    """Report with the highest sim_to_centroid, skipping copies and
    forward-chain posts (best evidence score when there are no embeddings)."""
    candidates = _clean_reports(members, feats, dup_groups)
    best = min(candidates, key=lambda i: (
        -(feats[i]["similarity"] if feats[i].get("similarity") is not None else -1.0),
        -(_evidence_score(feats[i])[0] or 0.0),
        i,
    ))
    return {"tweet_id": members[best].get("tweet_id"), "text": members[best].get("text", ""),
            "lang": feats[best]["lang"]}


def summary_slots(cluster: dict, feats: list, members: list) -> dict:
    """The language-neutral facts the summary states; None/False/0 = no data."""
    dup_groups = cluster["dup_groups"]
    originals = _originals(members, dup_groups)
    texts = [members[i].get("text", "") for i in originals]
    n_unique = len(dup_groups)

    needs = sorted((cluster.get("departments") or {}).items(), key=lambda kv: kv[1], reverse=True)
    main = needs[0][0] if needs and needs[0][1] >= config.MAIN_DEPT_MIN else None
    second = needs[1][0] if main and len(needs) > 1 and needs[1][1] >= config.SECOND_DEPT_MIN else None
    all_copies = len(members) > 1 and n_unique == 1

    return {
        "event": _most_frequent(EVENT_LEX, texts),
        "location": _location(texts),
        "impact": _most_frequent(IMPACT_LEX, texts),
        "urgent": sum(1 for i in originals if feats[i].get("urgency_kw")) * 2 >= len(originals) > 0,
        "n_unique": n_unique,
        "n_langs": len(cluster.get("details", {}).get("languages") or []),
        "span": _span(members, cluster.get("report_idx") or list(range(len(members)))),
        "main_dept": main,
        "second_dept": second,
        "warning": bool(cluster.get("likely_fake") or all_copies),
    }


def build_summary(cluster: dict, feats: list, members: list, now: float | None = None) -> dict:
    """Fill the template from cluster fields in every summary language; drop
    slots with no data. `text_en` is the English text (spec field)."""
    slots = summary_slots(cluster, feats, members)
    return {
        "text_en": render_summary(slots, "en"),
        "text": {lang: render_summary(slots, lang) for lang in SUMMARY_LANGUAGES},
        "slots": slots,  # the facts themselves (location, event, ...) for analytics
        "method": config.SUMMARY_METHOD,
        "generated_at": time.time() if now is None else now,
    }


def summarise_cluster(cluster: dict, members: list, feats: list, dup_groups: list,
                      translate: bool = True, now: float | None = None) -> dict:
    """Return the full step-10 output record for one cluster."""
    cluster = {**cluster, "dup_groups": dup_groups}
    representative = pick_representative(members, feats, dup_groups)
    representative["text_en"] = translate_to_en(representative["text"], representative["lang"], translate)
    evidence = select_evidence(members, feats, dup_groups)
    for item in evidence:
        item["text_en"] = translate_to_en(item["text"], item["lang"], translate)
    return {
        "cluster_id": cluster.get("cluster_id"),
        "summary": build_summary(cluster, feats, members, now=now),
        "representative": representative,
        "evidence": evidence,
        "evidence_version": config.EVIDENCE_VERSION,
    }
