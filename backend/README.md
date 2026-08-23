# Backend

Single FastAPI app (a "modular monolith") implementing every HLD layer as its own router,
rather than a separate process per layer. One process, one port.

## Run

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Set `MONGO_URI` (default `mongodb://127.0.0.1:27017`) if MongoDB isn't running locally on the
default port. `CORS_ORIGINS` defaults to `http://localhost:5173` (the Vite dev server) — set it
to a comma-separated list if the frontend runs elsewhere.

## Router map

| Router | Prefix | Purpose |
|---|---|---|
| `app/routers/ingestion.py` | `/ingestion` | Receives raw posts, enriches with metadata, pushes to the queue |
| `app/routers/queue.py` | `/queue` | In-memory FIFO buffer between ingestion and preprocessing |
| `app/routers/preprocessing.py` | `/preprocessing` | Text cleaning + language detection |
| `app/routers/analysis.py` | `/analysis` | Sentiment, need detection, fake-news, priority scoring (helpers in `app/analysis/`) |
| `app/routers/summarization.py` | `/summarization` | Situation summary generation |
| `app/routers/evidence.py` | `/evidence` | Top-post / evidence selection |
| `app/routers/situations.py` | `/situations`, `/analytics` | What the **frontend** calls: list pending/confirmed situations, record review decisions, analytics summary |

`app/db.py` holds the shared MongoDB (motor) client and the `situations` / `evidence`
collections. `app/schemas/` holds the shared Pydantic models.

Because everything runs in one process, `ingestion.py` calls into `queue.py`'s
`enqueue_item()` directly as a function call — no HTTP hop between them, unlike the earlier
two-process prototype this was migrated from.

## Tools

Standalone scripts, not part of the API process — run them against a live backend:

- `tools/simulator/csv_producer.py` — streams `ingestion_ds.csv` rows into `/ingestion/ingest`
- `tools/consumer/print_consumer.py` — polls `/queue/dequeue` and prints what it gets

```bash
# terminal 1
uvicorn app.main:app --reload --port 8000
# terminal 2
python tools/simulator/csv_producer.py --limit 20
# terminal 3 (optional)
python tools/consumer/print_consumer.py --max-messages 20
```
