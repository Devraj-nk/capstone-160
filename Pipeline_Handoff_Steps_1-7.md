# Capstone 160 — Pipeline Handoff (Steps 1–7)
### What's built and working, before Clustering (Step 8)

This covers everything from Ingestion through the Combine step — fully working, tested code for each piece, with the exact JSON schema each step outputs. Clustering (Step 8) is next, using the output of the Combine step as input.

---

## Full Pipeline (for reference)

1. Ingestion (Devraj)
2. Preprocessing — cleaning + dedup (Devraj)
3. Disaster Classification gate (Favaz)
4. Language Detection (Favaz)
5. Sentiment Analysis (Akshata) + Need Detection (Favaz) — parallel
6. Combine step (Devraj) — merges 3, 4, 5 → adds severity, actionability
7. Embedding Generation (Akshata) — IndicSBERT vectors
8. **Clustering (Akshata) ← current step**
9. Fake-News Scoring (Christa) + Priority Scoring (Akshata) — uses clusters from step 8
10. Evidence Extraction (Christa/Devraj) — needs step 8 + step 9
11. Summarization (Akshata)
12. Store Evidence + privacy masking (Christa/Devraj)
13. Human Review (Christa)
14. Confirm/Reject → Feedback loop / Route to Department (Devraj)
15. Dashboard/Reports (Devraj)

---

## Step 3 — Disaster Classification (Favaz)

**Model:** `Favaz-07/diaster-classifier-xlmr` (XLM-RoBERTa, fine-tuned, per-language decision thresholds)

Applies a per-language probability threshold (tuned separately for each language rather than one fixed 0.5 cutoff) to decide whether a tweet is disaster-relevant at all. Everything downstream only runs on tweets that pass this gate.

```python
final_preds = (test_probs >= np.array(
    [per_lang_thresholds.get(l, DEFAULT_THRESHOLD) for l in test_langs]
)).astype(bool)

output_records = []
for i in range(len(test_df)):
    row = test_df.iloc[i]
    output_records.append({
        "tweet_id": row['tweet_id'],
        "text": row['text'],
        "is_disaster": bool(final_preds[i]),
        "disaster_confidence": round(float(test_probs[i]), 4),
        "lang": row['lang'],
    })

with open("/kaggle/working/disaster_predictions.json", "w", encoding="utf-8") as f:
    json.dump(output_records, f, ensure_ascii=False, indent=2)
```

**Output schema (per tweet):**
```json
{
  "tweet_id": "tw_00981",
  "text": "flood in my area need help urgently",
  "is_disaster": true,
  "disaster_confidence": 0.87,
  "lang": "en"
}
```

---

## Step 4 — Language Detection (Favaz)

**Model:** `Favaz-07/language-detection-xlmr` (XLM-RoBERTa) + a deterministic Unicode script-range check that runs first.

**Why two stages:** plain `langdetect` (character n-gram statistics) can't recognize romanized Indian languages — e.g. `"nan yen madte"` (Kannada written in Latin letters) always gets misclassified as English, since `langdetect` has no concept of "this is Kannada spelled phonetically." Fix:
- **Case 1 — native script** (Devanagari / Kannada / Tamil / Telugu Unicode ranges): caught instantly and 100% reliably by a regex check, no model needed. Catches ~50–58% of real tweet data on its own.
- **Case 2 — Latin-script text** (English or romanized Hindi/Kannada/Tamil/Telugu): falls through to the trained XLM-RoBERTa classifier.

**Test results:** 99.24% overall accuracy, macro-F1 0.983 across all 5 languages (en=0.991, hi=0.997, kn=0.946, ta=0.985, te=0.998 — Kannada lowest since it has the fewest examples, but still strong).

```python
SCRIPT_RANGES = {
    'hi': r'[ऀ-ॿ]',   # Devanagari (Hindi)
    'kn': r'[ಀ-೿]',   # Kannada script
    'ta': r'[஀-௿]',   # Tamil script
    'te': r'[ఀ-౿]',   # Telugu script
}

def detect_by_script(text, min_chars=3):
    counts = {lang: len(re.findall(p, text)) for lang, p in SCRIPT_RANGES.items()}
    best_lang = max(counts, key=counts.get)
    return best_lang if counts[best_lang] >= min_chars else None

def check_code_mixed(text, min_native=3, min_latin=5):
    counts = {lang: len(re.findall(p, text)) for lang, p in SCRIPT_RANGES.items()}
    has_native = counts and max(counts.values()) >= min_native
    has_latin = len(re.findall(r'[A-Za-z]', text)) >= min_latin
    return bool(has_native and has_latin)

def predict_with_classifier(text):
    enc = tokenizer(text, max_length=96, padding='max_length', truncation=True, return_tensors='pt').to(device)
    with torch.no_grad():
        logits = model(**enc).logits
    return id2lang[int(torch.argmax(logits, dim=1)[0])]

def detect_language_final(text):
    script_lang = detect_by_script(text)
    if script_lang is not None:
        lang, is_romanized = script_lang, False
    else:
        lang = predict_with_classifier(text)
        is_romanized = (lang != 'en')
    return {"lang": lang, "is_romanized": is_romanized, "is_code_mixed": check_code_mixed(text)}
```

**Output schema (per tweet):**
```json
{
  "text": "nan yen madthidini gottilla",
  "lang": "kn",
  "is_romanized": true,
  "is_code_mixed": false
}
```

**Known, documented limitation:** true code-mixing *within* a single tweet (e.g. "office jaana hai, traffic is crazy") is flagged with a lightweight heuristic, not a full token-level model — same scope limitation AI4Bharat treats as separate research. The dominant language per tweet is what gets tagged.

---

## Step 5a — Sentiment Analysis (Akshata)

**Model:** XLM-RoBERTa-base, fine-tuned (binary positive/negative), hosted at `akshataudaganve/xlmr-sentiment-disaster` on Hugging Face Hub. Selected over MuRIL after a head-to-head comparison (XLM-R: 82.75% accuracy, F1 0.8523 vs MuRIL: 82.06% accuracy, F1 0.8486). Per-language F1 ranges 0.82–0.91 across all 5 languages.

```python
def add_sentiment_to_tweet(tweet_record: dict) -> dict:
    """
    Input: a dict already containing at least {"tweet_id", "text", "lang", "is_disaster", ...}
           — whatever fields the earlier pipeline steps already attached.
    Output: the SAME dict, with sentiment fields added on top. Nothing removed.
    """
    text = tweet_record["text"]
    inputs = sentiment_tokenizer(text, truncation=True, padding="max_length",
                                  max_length=128, return_tensors="pt").to(device)
    with torch.no_grad():
        logits = sentiment_model(**inputs).logits
        probs = torch.softmax(logits, dim=1).squeeze().tolist()
    pred_class = int(torch.argmax(logits, dim=1).item())

    tweet_record["sentiment_label"] = LABEL_MAP[pred_class]
    tweet_record["sentiment_confidence"] = round(probs[pred_class], 4)
    tweet_record["sentiment_probabilities"] = {LABEL_MAP[i]: round(p, 4) for i, p in enumerate(probs)}
    tweet_record["sentiment_negativity"] = round(probs[0], 4)   # feeds into Severity formula
    tweet_record["sentiment_model"] = SENTIMENT_MODEL_PATH
    tweet_record["sentiment_predicted_at"] = datetime.now(timezone.utc).isoformat()
    return tweet_record

def add_sentiment_to_tweets_batch(tweet_records: list, batch_size: int = 32) -> list:
    """Processes a list of tweet JSON records efficiently, all at once per batch."""
    texts = [r["text"] for r in tweet_records]
    all_probs = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i+batch_size]
        inputs = sentiment_tokenizer(batch, truncation=True, padding=True,
                                      max_length=128, return_tensors="pt").to(device)
        with torch.no_grad():
            logits = sentiment_model(**inputs).logits
            probs = torch.softmax(logits, dim=1).cpu().tolist()
        all_probs.extend(probs)
    for record, probs in zip(tweet_records, all_probs):
        pred_class = int(np.argmax(probs))
        record["sentiment_label"] = LABEL_MAP[pred_class]
        record["sentiment_confidence"] = round(probs[pred_class], 4)
        record["sentiment_probabilities"] = {LABEL_MAP[i]: round(p, 4) for i, p in enumerate(probs)}
        record["sentiment_negativity"] = round(probs[0], 4)
        record["sentiment_model"] = SENTIMENT_MODEL_PATH
        record["sentiment_predicted_at"] = datetime.now(timezone.utc).isoformat()
    return tweet_records
```

**Loading the model (from Hugging Face — no local files needed):**
```python
from transformers import AutoTokenizer, AutoModelForSequenceClassification

SENTIMENT_MODEL_PATH = "akshataudaganve/xlmr-sentiment-disaster"
sentiment_tokenizer = AutoTokenizer.from_pretrained(SENTIMENT_MODEL_PATH)
sentiment_model = AutoModelForSequenceClassification.from_pretrained(SENTIMENT_MODEL_PATH)
sentiment_model.eval()
LABEL_MAP = {0: "negative", 1: "positive"}
```

**Output schema (per tweet):**
```json
{
  "tweet_id": "tw_00981",
  "text": "flood in my area need help urgently",
  "lang": "en",
  "is_disaster": true,
  "sentiment_label": "negative",
  "sentiment_confidence": 0.9943,
  "sentiment_probabilities": {"negative": 0.9943, "positive": 0.0057},
  "sentiment_negativity": 0.9943,
  "sentiment_model": "akshataudaganve/xlmr-sentiment-disaster",
  "sentiment_predicted_at": "2026-09-02T00:59:30.427018+00:00"
}
```

**Known limitation:** training data (Sentiment140 translated via NLLB-200 for Hindi/Telugu, curated IndicSentiment-style data for Kannada/Tamil) is clean, single-script text — not organic code-mixed social media text. Real-world accuracy on heavily code-mixed/romanized tweets is expected to be somewhat lower than the reported per-language F1 scores.

---

## Step 5b — Need Detection (Favaz)

**Model:** `Favaz-07/need-detection-xlmr` (XLM-RoBERTa-base, multi-label, sigmoid output — a tweet can hit 0, 1, or several departments at once: healthcare, municipal, tourism, law).

Trained with `BCEWithLogitsLoss` + per-label `pos_weight` (capped at 10) to handle label imbalance — `is_tourism` is rare. Per-label decision thresholds tuned on a held-out validation set (not the test set, avoiding overfitting the reported numbers).

**Test results:** exact-match accuracy 92.66% overall. Per-language macro-F1: en=0.919, hi=0.553, kn=0.376, ta=0.421, te=0.415 — English is strong; non-English is real but noticeably weaker (translated training data doesn't carry the exact keywords the original English labels were built from, so the model has to actually infer meaning — a harder task, and one worth flagging in your report as still-improving, not yet as strong as English).

**Final per-label thresholds:** `is_healthcare`: 0.65, `is_municipal`: 0.80, `is_tourism`: 0.75, `is_law`: 0.65

```python
def predict_needs(text):
    enc = tokenizer(text, max_length=128, padding='max_length', truncation=True, return_tensors='pt').to(device)
    with torch.no_grad():
        probs = torch.sigmoid(model(**enc).logits).cpu().numpy()[0]
    return {name: float(probs[i]) for i, name in enumerate(LABEL_COLS)}

# Applied per tweet:
needs = {name.replace('is_', ''): round(float(probs[j]), 4) for j, name in enumerate(LABEL_COLS)}
output_record = {
    "tweet_id": row['tweet_id'],
    "text": row['text'],
    "lang": row['lang'],
    "needs": needs,
    "need_confidence": round(float(max(needs.values())), 4),
}
```

**Output schema (per tweet):**
```json
{
  "tweet_id": "tw_00981",
  "text": "flood in my area need help urgently",
  "lang": "en",
  "needs": {"healthcare": 0.011, "municipal": 0.998, "tourism": 0.015, "law": 0.013},
  "need_confidence": 0.998
}
```

---

## Step 6 — Combine Step (Devraj)

Merges the Sentiment output and Need Detection output (steps 5a/5b) into one final record per tweet, and computes two new fields that don't need any additional model:

- **`actionability`** — rule-based keyword-tier scoring (1.0 for urgent/rescue-type phrases, 0.6 for softer help requests, 0.2 for sympathy-only text with no actual request).
- **`severity`** — `0.6 × need_confidence + 0.4 × sentiment_negativity` (using `need_confidence` directly as the NeedSeverity proxy, per the Priority/Severity formula agreed earlier).

```python
ACTION_KEYWORDS = {
    1.0: ["send help", "need rescue", "trapped", "urgent", "immediately", "sos", "please send", "need medical help"],
    0.6: ["please help", "someone check", "worried about", "not sure what to do", "need assistance"],
    0.2: ["this is sad", "can't believe", "thoughts and prayers", "hope everyone"]
}

def actionability_score(text: str) -> float:
    text_lower = text.lower()
    best_score = 0.0
    for tier_score, phrases in ACTION_KEYWORDS.items():
        for phrase in phrases:
            if phrase in text_lower:
                best_score = max(best_score, tier_score)
    return best_score

def compute_severity(sentiment_negativity: float, need_confidence: float) -> float:
    severity = 0.6 * need_confidence + 0.4 * sentiment_negativity
    return round(severity, 4)

def combine_tweet_record(sentiment_json: dict, need_json: dict, created_at: str) -> dict:
    text = sentiment_json["text"]
    actionability = actionability_score(text)
    severity = compute_severity(
        sentiment_negativity=sentiment_json["sentiment_negativity"],
        need_confidence=need_json["need_confidence"]
    )
    return {
        "tweet_id": sentiment_json["tweet_id"],
        "text": text,
        "lang": sentiment_json["lang"],
        "is_disaster": need_json["is_disaster"],
        "disaster_confidence": need_json["disaster_confidence"],
        "created_at": created_at,                      # from ingestion, must be passed in
        "sentiment_negativity": sentiment_json["sentiment_negativity"],
        "needs": need_json["needs"],
        "need_confidence": need_json["need_confidence"],
        "actionability": actionability,
        "severity": severity,
        "combined_at": datetime.now(timezone.utc).isoformat()
    }
```

**Final combined output schema — this is what feeds into Clustering (Step 8):**
```json
{
  "tweet_id": "tw_00981",
  "text": "flood in my area need help urgently",
  "lang": "en",
  "is_disaster": true,
  "disaster_confidence": 0.87,
  "created_at": "2026-09-02T00:58:10.000000+00:00",
  "sentiment_negativity": 0.9943,
  "needs": {"healthcare": 0.011, "municipal": 0.998, "tourism": 0.015, "law": 0.013},
  "need_confidence": 0.998,
  "actionability": 1.0,
  "severity": 0.9966,
  "combined_at": "2026-09-02T01:02:44.000000+00:00"
}
```

---

## Step 7 — Embedding Generation (Akshata)

IndicSBERT vectors, generated from the combined record's `text` field — feeds directly into Step 8 (Clustering), grouping semantically similar tweets together regardless of language.

---

## Model Registry (for anyone integrating the pipeline)

| Step | Model | Hosted at |
|---|---|---|
| Disaster Classification | XLM-RoBERTa (fine-tuned) | `Favaz-07/diaster-classifier-xlmr` |
| Language Detection | Script-range + XLM-RoBERTa | `Favaz-07/language-detection-xlmr` |
| Need Detection | XLM-RoBERTa (multi-label) | `Favaz-07/need-detection-xlmr` |
| Sentiment Analysis | XLM-RoBERTa-base | `akshataudaganve/xlmr-sentiment-disaster` |

All four load the same way — `AutoTokenizer.from_pretrained(repo_id)` / `AutoModelForSequenceClassification.from_pretrained(repo_id)` — no manual downloads needed by anyone integrating these into the shared backend.
