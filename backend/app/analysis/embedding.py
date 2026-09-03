from __future__ import annotations

# Step 7 (Akshata) — IndicSBERT vectors generated from the combined record's
# `text` field, feeding Clustering (Step 8). The handoff doc names the model
# family (IndicSBERT) but doesn't hand off a model repo id, pooling strategy,
# or vector dimension the way every other step here does — so this is left
# as an explicit gap rather than guessed at. Fill in once that's available.


def generate_embedding(text: str) -> list[float]:
    raise NotImplementedError(
        "Step 7 embedding generation not yet specified — no IndicSBERT model "
        "id/config was included in the pipeline handoff. Needed before "
        "Clustering (Step 8) can run."
    )
