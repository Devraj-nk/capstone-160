# Cluster Scoring Module — Setup & Usage

## 1. Setup (once)

```bash
# inside the unzipped capstone_scoring folder, in the VS Code terminal
python -m venv .venv

# Windows (PowerShell)
.venv\Scripts\Activate.ps1
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```
In VS Code: Ctrl+Shift+P → "Python: Select Interpreter" → choose `.venv`.

## 2. Check everything works

```bash
pytest -q                      # expect: 43 passed
python run_scoring.py --input sample_data/clustered_sample.json --out-dir outputs
```

## 3. Plug in your real clustering output

At the end of your clustering notebook/script, dump every tweet with its cluster:

```python
import json
records = []
for t in clustered_tweets:                 # whatever your structure is
    records.append({
        "tweet_id": t["tweet_id"],
        "origin_id": t.get("origin_id"),   # original tweet id for IndicTrans2 copies
        "text": t["text"],
        "cluster_id": int(t["cluster_id"]),
        "lang": t["lang"], "is_romanized": t["is_romanized"], "is_code_mixed": t["is_code_mixed"],
        "disaster_confidence": t["disaster_confidence"],
        "needs": t["needs"], "need_confidence": t["need_confidence"],
        "sentiment_confidence": t.get("sentiment_confidence"),
        "sentiment_negativity": t["sentiment_negativity"],
        "created_at": t["created_at"],
        "embedding": t["embedding"].tolist(),   # IndicSBERT vector
    })
with open("clustered_tweets.jsonl", "w", encoding="utf-8") as f:
    for r in records:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
```
Then: `python run_scoring.py --input clustered_tweets.jsonl --out-dir outputs`

Or call it directly from Python:
```python
from scoring import load_calibration, score_clusters
clusters, tweet_scores = score_clusters(records, load_calibration())
```

## 4. Fit language calibration (important for fairness)

Run your models on the **validation** split, save predictions as JSONL with
`lang, is_romanized, is_code_mixed, disaster_confidence, need_confidence,
sentiment_confidence`, then:
```bash
python fit_calibration.py --input val_predictions.jsonl
```
This writes `calibration/lang_confidence_ref.json`, which is loaded automatically.

## 5. Outputs
- `outputs/clusters_scored.json` — per cluster: priority, band, fake_score,
  likely_fake, all terms, languages, departments, matched keywords (for the console)
- `outputs/tweets_scored.jsonl` — per tweet: every sub-score
- Terminal: a language fairness table (mean scores per language)

## Where language is handled
| Term | How it stays fair across languages |
|---|---|
| TextQuality | ideal length per language (kn/ta/te are agglutinative → fewer words); Latin allowed in any tweet; no spelling checks |
| Specificity | location/place/infrastructure/time words in 9 forms; Indic digits count as numbers |
| ModelConfidence | divided by each language's median validation confidence |
| ContentRisk | "forward this" and hearsay markers in 9 forms |
| Severity / Actionability | casualty and urgency words in 9 forms |
| ClusterConsistency | IndicSBERT is multilingual — same event, any language, sits near the centroid |
| Corroboration | independent reports in more languages score higher; copies/translations count once |
| AmplificationRisk | cross-language copies (high embedding similarity) are caught as duplicates |
