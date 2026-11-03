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

## Model Registry (for anyone integrating the pipeline)

| Step | Model | Hosted at |
|---|---|---|
| Disaster Classification | XLM-RoBERTa (fine-tuned) | `Favaz-07/diaster-classifier-xlmr` |
| Language Detection | Script-range + XLM-RoBERTa | `Favaz-07/language-detection-xlmr` |
| Need Detection | XLM-RoBERTa (multi-label) | `Favaz-07/need-detection-xlmr` |
| Sentiment Analysis | XLM-RoBERTa-base | `akshataudaganve/xlmr-sentiment-disaster` |

All four load the same way — `AutoTokenizer.from_pretrained(repo_id)` / `AutoModelForSequenceClassification.from_pretrained(repo_id)` — no manual downloads needed by anyone integrating these into the shared backend.
