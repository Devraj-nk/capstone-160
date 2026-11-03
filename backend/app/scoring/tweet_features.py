"""
Per-tweet scores. Every score is in [0, 1].

Input record (one tweet, after the combine step) — fields used:
  tweet_id, text, lang, is_romanized, is_code_mixed,
  disaster_confidence, need_confidence, sentiment_confidence (optional),
  sentiment_negativity, fake_prob (optional), severity/actionability (optional)
"""
from . import config
from .calibration import calibrate, lang_key
from .lexicons import ALL_CATEGORIES
from .text_utils import (CompiledLexicon, LANG_SCRIPT, has_number, noise_signals,
                         saturating_score, script_profile, tokenize)

LEX = {name: CompiledLexicon(lists) for name, lists in ALL_CATEGORIES.items()}


def weighted_sum(values: dict, weights: dict):
    """Weighted sum that skips missing (None) terms and re-normalizes the
    remaining weights so they still add up to 1."""
    total, wsum = 0.0, 0.0
    for k, w in weights.items():
        v = values.get(k)
        if v is None:
            continue
        total += w * float(v)
        wsum += w
    return total / wsum if wsum > 0 else None


def kw_score(hits: set) -> float:
    return saturating_score(len(hits), config.KEYWORD_SATURATION_BASE)


# ---------------------------------------------------------------------------
# Text quality — language-aware, never penalizes romanized/code-mixed spelling
# ---------------------------------------------------------------------------
def text_quality(raw_text: str, tokens: list, key: str, lang: str) -> dict:
    if key == "code_mixed":
        ideal = config.IDEAL_TOKENS["code_mixed"]
    elif key.endswith("_rom"):
        ideal = config.IDEAL_TOKENS["romanized"]
    else:
        ideal = config.IDEAL_TOKENS.get(lang, config.IDEAL_TOKENS["default"])
    length = min(1.0, len(tokens) / ideal)

    n = noise_signals(raw_text)
    noise = (0.3 * min(n["repeat_runs"], 2)          # "helppppp"
             + 0.3 * min(n["punct_runs"], 2)         # "!!!!"
             + 0.4 * (1.0 if n["caps_ratio"] > 0.6 else 0.0))  # SHOUTING (Latin only)
    clean = 1.0 - min(1.0, noise)

    # Script consistency: letters should be in the tweet's own script OR Latin
    # (Latin always allowed, because code-mixing is normal, not low quality).
    prof = script_profile(raw_text)
    allowed = {"latin", LANG_SCRIPT.get(lang, "latin")}
    script_ok = sum(v for s, v in prof.items() if s in allowed) if prof else 0.0

    score = weighted_sum({"length": length, "clean": clean, "script": script_ok},
                         config.TEXT_QUALITY_WEIGHTS)
    return {"text_quality": score, "tq_length": length, "tq_clean": clean, "tq_script": script_ok}


# ---------------------------------------------------------------------------
# Specificity — where / what / when / how many, in every language
# ---------------------------------------------------------------------------
def specificity(tokens: list, matches: dict) -> dict:
    location = 1.0 if (matches["location"] or matches["place_names"]) else 0.0
    parts = {
        "location": location,
        "number": 1.0 if has_number(tokens) else 0.0,
        "infrastructure": kw_score(matches["infrastructure"]),
        "time": 1.0 if matches["time"] else 0.0,
    }
    return {"specificity": weighted_sum(parts, config.SPECIFICITY_WEIGHTS),
            **{f"sp_{k}": v for k, v in parts.items()}}


# ---------------------------------------------------------------------------
# Content risk — "forward this", hearsay, shouting style
# ---------------------------------------------------------------------------
def content_risk(raw_text: str, matches: dict) -> dict:
    n = noise_signals(raw_text)
    style = min(1.0, 0.5 * (n["caps_ratio"] > 0.6) + 0.25 * min(n["punct_runs"], 2))
    parts = {
        "forward_chain": kw_score(matches["forward_chain"]),
        "hearsay": kw_score(matches["hearsay"]),
        "style": style,
    }
    return {"content_risk": weighted_sum(parts, config.CONTENT_RISK_WEIGHTS),
            **{f"cr_{k}": v for k, v in parts.items()}}


# ---------------------------------------------------------------------------
# Main per-tweet function
# ---------------------------------------------------------------------------
def compute_tweet_features(rec: dict, cal: dict) -> dict:
    raw = rec.get("text", "") or ""
    tokens = tokenize(raw)
    lang = (rec.get("lang") or "unknown").lower()
    key = lang_key(lang, rec.get("is_romanized"), rec.get("is_code_mixed"))

    matches = {name: lex.match(tokens) for name, lex in LEX.items()}

    feats = {"tweet_id": rec.get("tweet_id"), "lang": lang, "lang_key": key}
    feats.update(text_quality(raw, tokens, key, lang))
    feats.update(specificity(tokens, matches))
    feats.update(content_risk(raw, matches))

    # Calibrated model confidences
    cal_conf = {f: calibrate(rec.get(f), f, key, cal)
                for f in ("disaster_confidence", "need_confidence", "sentiment_confidence")}
    available = [v for v in cal_conf.values() if v is not None]
    feats["model_confidence"] = sum(available) / len(available) if available else None
    feats.update({f"cal_{k}": v for k, v in cal_conf.items()})

    feats["severity_kw"] = kw_score(matches["severity"])
    feats["urgency_kw"] = kw_score(matches["urgency"])
    feats["has_forward_marker"] = bool(matches["forward_chain"])

    # Combine step: Severity / Actionability
    if not config.RECOMPUTE_COMBINE and rec.get("severity") is not None:
        feats["severity"] = float(rec["severity"])
    else:
        feats["severity"] = weighted_sum({
            "disaster_confidence": cal_conf["disaster_confidence"],
            "sentiment_negativity": rec.get("sentiment_negativity"),
            "severity_keywords": feats["severity_kw"],
        }, config.SEVERITY_WEIGHTS)

    if not config.RECOMPUTE_COMBINE and rec.get("actionability") is not None:
        feats["actionability"] = float(rec["actionability"])
    else:
        feats["actionability"] = weighted_sum({
            "need_confidence": cal_conf["need_confidence"],
            "urgency_keywords": feats["urgency_kw"],
            "specificity": feats["specificity"],
        }, config.ACTIONABILITY_WEIGHTS)

    feats["fake_prob"] = rec.get("fake_prob")
    # Explainability: which words fired (show these in the review console)
    feats["matched_terms"] = {k: sorted(v) for k, v in matches.items() if v}
    return feats
