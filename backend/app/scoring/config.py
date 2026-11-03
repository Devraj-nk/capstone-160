"""
All tunable numbers live here.

LOCKED   = team's agreed formula weights (from pipeline decisions). Don't change
           without the whole team agreeing.
HEURISTIC = our own starting values. Report them honestly as heuristics in the
           viva/report, not as paper-validated numbers.
"""
import os


# ---------------------------------------------------------------------------
# LOCKED: top-level formulas
# ---------------------------------------------------------------------------
PRIORITY_WEIGHTS = {
    "severity": 0.30,
    "actionability": 0.25,
    "corroboration": 0.20,
    "credibility": 0.15,
    "recency": 0.10,
}

FAKE_WEIGHTS = {
    "model": 0.35,               # fake-news model probability (optional input)
    "inv_credibility": 0.25,     # 1 - Credibility
    "content_risk": 0.15,
    "amplification_risk": 0.25,
}

CREDIBILITY_WEIGHTS = {
    "cluster_consistency": 0.35,
    "text_quality": 0.30,
    "model_confidence": 0.20,
    "specificity": 0.15,
}

# (band name, minimum score) — checked top to bottom
PRIORITY_BANDS = [("Critical", 0.75), ("High", 0.55), ("Medium", 0.35), ("Low", 0.0)]

# ---------------------------------------------------------------------------
# HEURISTIC: per-tweet combine step (Severity / Actionability)
# ---------------------------------------------------------------------------
# True  -> always recompute Severity/Actionability here (multilingual keywords).
# False -> if a record already has "severity"/"actionability", keep those.
RECOMPUTE_COMBINE = True

SEVERITY_WEIGHTS = {
    "disaster_confidence": 0.40,   # calibrated per language
    "sentiment_negativity": 0.30,
    "severity_keywords": 0.30,     # casualties / damage words, all languages
}

ACTIONABILITY_WEIGHTS = {
    "need_confidence": 0.40,
    "urgency_keywords": 0.35,      # help / urgent / rescue words, all languages
    "specificity": 0.25,
}

# ---------------------------------------------------------------------------
# HEURISTIC: sub-component weights
# ---------------------------------------------------------------------------
TEXT_QUALITY_WEIGHTS = {"length": 0.40, "clean": 0.35, "script": 0.25}
SPECIFICITY_WEIGHTS = {"location": 0.40, "number": 0.25, "infrastructure": 0.20, "time": 0.15}
CONTENT_RISK_WEIGHTS = {"forward_chain": 0.50, "hearsay": 0.25, "style": 0.25}
AMPLIFICATION_WEIGHTS = {"duplicate_ratio": 0.45, "copy_burst": 0.30, "forward_ratio": 0.25}
CORROBORATION_WEIGHTS = {"volume": 0.70, "language_diversity": 0.30}

# keyword score = 1 - BASE ** (distinct terms matched)  -> 1 hit 0.60, 2 hits 0.84, 3 hits 0.94
KEYWORD_SATURATION_BASE = 0.4

# ---------------------------------------------------------------------------
# HEURISTIC: language-aware settings
# ---------------------------------------------------------------------------
# Kannada/Tamil/Telugu are agglutinative: one word carries what English needs
# 2-3 words for ("ಸಿಲುಕಿಕೊಂಡಿದ್ದಾರೆ" = "they are stuck"). So a complete
# Kannada tweet has fewer tokens, and we must not call it "too short".
IDEAL_TOKENS = {
    "en": 6, "hi": 6, "kn": 4, "ta": 4, "te": 4,
    "romanized": 6, "code_mixed": 6, "default": 5,
}

# Model-confidence calibration reference (median confidence per language on the
# VALIDATION set). Leave as {} until you run fit_calibration.py — then the
# fitted file in calibration/ is loaded automatically and overrides this.
# Without it, raw confidences are used (no language adjustment).
LANG_CONFIDENCE_REF = {}
# Resolved next to this package so it loads no matter which directory the
# backend is started from.
CALIBRATION_FILE = os.path.join(os.path.dirname(__file__), "calibration", "lang_confidence_ref.json")
MIN_REF = 0.05                     # guard against dividing by ~0
MIN_SAMPLES_FOR_CALIBRATION = 20   # per language, else that language stays raw

# ---------------------------------------------------------------------------
# HEURISTIC: cluster-level settings
# ---------------------------------------------------------------------------
CONSISTENCY_LOW = 0.32     # = clustering similarity threshold -> maps to 0
CONSISTENCY_HIGH = 0.85    # cosine at/above this -> maps to 1
# If a cluster has only ONE independent report (all others are copies), being
# "close to the centroid" proves nothing — copies are trivially consistent.
# Use a neutral value instead.
CONSISTENCY_NO_EVIDENCE = 0.5
NEAR_DUP_COSINE = 0.92     # same message (incl. translated copies) if cosine >= this
VOLUME_SATURATION = 10     # 10 independent reports -> volume score 1.0
LANG_DIVERSITY_SATURATION = 3  # reports in 3+ different languages -> 1.0
COPY_BURST_WINDOW_SEC = 300    # copies posted within 5 min of the original
RECENCY_HALF_LIFE_HOURS = 6.0
CLUSTER_TOP_K = 3          # cluster Severity/Actionability = mean of top-3 tweets
FAKE_FLAG_THRESHOLD = 0.60 # flag cluster as likely_fake for the review console

# ---------------------------------------------------------------------------
# HEURISTIC: step 10 — summary & evidence (summary_evidence.py)
# ---------------------------------------------------------------------------
# EvidenceScore = 0.6 * Similarity + 0.4 * PostStrength   (per post)
EVIDENCE_WEIGHTS = {"similarity": 0.6, "strength": 0.4}
POST_STRENGTH_WEIGHTS = {"specificity": 0.4, "actionability": 0.3, "credibility": 0.3}
EVIDENCE_MAX = 5           # k = min(EVIDENCE_MAX, independent reports)
EVIDENCE_PER_LANG = 2      # while other languages are still available
MAIN_DEPT_MIN = 0.3        # "Main need" only stated when the top need reaches this
SECOND_DEPT_MIN = 0.5      # "; also DEPT_2" only when the second need reaches this
SUMMARY_METHOD = "template_v1"
EVIDENCE_VERSION = "v1"
