# Capstone 160 — Cluster Scoring Module (step 8 of the pipeline)

Multilingual crisis-tweet system (en / hi / kn / ta / te, native script + romanized
+ code-mixed). This module takes CLUSTERED tweets and computes, per cluster:
Credibility → Fake-Score → Priority → Band (Critical/High/Medium/Low).

## Pipeline position
ingestion → preprocessing → disaster classifier → language detection →
[need detection ‖ sentiment] → combine → clustering (IndicSBERT + HDBSCAN)
→ **THIS MODULE** → summary/evidence → MongoDB → human review console → routing

## Commands
- Run tests: `pytest -q`  (must stay green; add a test for every change)
- Score sample: `python run_scoring.py --input sample_data/clustered_sample.json --out-dir outputs`
- Fit language calibration: `python fit_calibration.py --input <val_predictions.jsonl>`

## Files
- `scoring/config.py` — ALL weights/thresholds. LOCKED = team-agreed formula weights. HEURISTIC = our own.
- `scoring/lexicons.py` — multilingual keyword lists (9 forms per category).
- `scoring/text_utils.py` — Indic-safe tokenizer + lexicon matcher.
- `scoring/calibration.py` — per-language confidence calibration.
- `scoring/tweet_features.py` — per-tweet: TextQuality, Specificity, ContentRisk, ModelConfidence, Severity, Actionability.
- `scoring/cluster_scoring.py` — per-cluster: ClusterConsistency, Credibility, Corroboration, AmplificationRisk, Fake-Score, Recency, Priority.

## Formulas (LOCKED — do not change weights without asking)
- Priority = 0.30·Severity + 0.25·Actionability + 0.20·Corroboration + 0.15·Credibility + 0.10·Recency
- Fake = 0.35·Model + 0.25·(1−Credibility) + 0.15·ContentRisk + 0.25·AmplificationRisk
- Credibility = 0.35·ClusterConsistency + 0.30·TextQuality + 0.20·ModelConfidence + 0.15·Specificity
- Bands: Critical ≥0.75, High ≥0.55, Medium ≥0.35, Low <0.35
- Missing input term → skipped and remaining weights re-normalized (`weighted_sum`).

## Input schema (one dict per tweet, .json list or .jsonl)
Required: `tweet_id, text, cluster_id, lang, is_romanized, is_code_mixed`
Used if present: `disaster_confidence, need_confidence, sentiment_confidence,
sentiment_negativity, needs{healthcare,municipal,tourism,law}, created_at (unix sec),
embedding (IndicSBERT list) or sim_to_centroid, origin_id, fake_prob`
`cluster_id = -1` (HDBSCAN noise) → scored as its own singleton.

## Rules when editing
- Never use regex `\w` to tokenize — it breaks Indic words (vowel signs are not \w). Use `tokenize()`.
- Lexicon checks run on ALL languages for every tweet (language detection is advisory only).
- Never penalize romanized/code-mixed spelling. No English dictionary/spell checks.
- Lexicon terms: `word` exact, `stem*` prefix, `*end` suffix, `*mid*` inside word, multi-word = phrase.
  Avoid short Indic stems that cause false hits; add a positive AND a negative test for new terms.
- Calibration must be fitted on the VALIDATION split, never test.
- Keep outputs JSON-serializable (floats, lists, dicts) — they go to MongoDB.
