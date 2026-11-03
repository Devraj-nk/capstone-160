"""
Per-language confidence calibration.

Problem: our models are less confident on Kannada/Hindi/Tamil/Telugu than on
English (they saw less of it). If we feed raw confidence into Credibility, a
true Kannada report looks "less credible" only because it is in Kannada.

Fix: divide each confidence by that language's typical (median) confidence on
the validation set, capped at 1.0:

    calibrated = min(1, raw_confidence / median_confidence[model][language])

So "0.70 on Kannada" counts as strong if the model is usually ~0.70 on Kannada.
"""
import json
import os
from statistics import median

from . import config

CONFIDENCE_FIELDS = ("disaster_confidence", "need_confidence", "sentiment_confidence")


def lang_key(lang, is_romanized=False, is_code_mixed=False) -> str:
    """'kn' native, 'kn_rom' romanized Kannada, 'code_mixed', 'en', ..."""
    lang = (lang or "unknown").lower()
    if is_code_mixed:
        return "code_mixed"
    if is_romanized and lang != "en":
        return f"{lang}_rom"
    return lang


def base_lang(key: str) -> str:
    return key.split("_")[0] if key not in ("code_mixed",) else "code_mixed"


def load_calibration(path: str | None = None) -> dict:
    path = path or config.CALIBRATION_FILE
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return dict(config.LANG_CONFIDENCE_REF)


def fit_calibration(records: list[dict]) -> dict:
    """records = validation-set PREDICTIONS (same schema as pipeline output)."""
    buckets: dict = {f: {} for f in CONFIDENCE_FIELDS}
    for r in records:
        key = lang_key(r.get("lang"), r.get("is_romanized"), r.get("is_code_mixed"))
        for f in CONFIDENCE_FIELDS:
            v = r.get(f)
            if isinstance(v, (int, float)):
                buckets[f].setdefault(key, []).append(float(v))
    out = {}
    for f, by_lang in buckets.items():
        out[f] = {k: round(median(vals), 4) for k, vals in by_lang.items()
                  if len(vals) >= config.MIN_SAMPLES_FOR_CALIBRATION}
    return out


def calibrate(value, field: str, key: str, cal: dict):
    if value is None:
        return None
    ref = cal.get(field, {}).get(key)
    if ref is None:                          # e.g. 'kn_rom' not fitted -> try 'kn'
        ref = cal.get(field, {}).get(base_lang(key))
    if ref is None:
        return float(value)                  # uncalibrated: raw value
    return min(1.0, float(value) / max(ref, config.MIN_REF))


def is_calibrated(cal: dict) -> bool:
    return any(cal.get(f) for f in CONFIDENCE_FIELDS)
