# Recommended Technology Stack

Scope: recommendations sized for the **capstone prototype**, mapped to each layer in [HLD.png](HLD.png) / [data_flow_swimlanes.jpg](data_flow_swimlanes.jpg). Backend, storage, and models build on what the Phase-2 slides already committed to (FastAPI, MongoDB, Hugging Face Transformers/PyTorch models — XLM-RoBERTa, BERTweet, mDeBERTa, BART-large-MNLI, SBERT, mT5). The presentation layer is **React** (via [frontend/](../frontend/)), not the Streamlit option this doc previously suggested — the team wanted a standard React/FastAPI/MongoDB three-tier split with explicit `backend/`/`frontend/` folders. Heavier infrastructure (Kafka, Kubernetes, Airflow/Celery, dedicated model servers) is still intentionally left out: it solves scaling problems this prototype doesn't have yet.

## Shape: a FastAPI modular monolith, not one microservice per layer

Every layer below is a **router inside the single [backend/](../backend/) FastAPI app** (`app/routers/<layer>.py`), not a separate process on its own port. One `uvicorn app.main:app` process serves everything. This was a deliberate choice over N independent FastAPI services: it keeps each layer's code in its own module (so it's just as easy to hand a layer to a teammate) while avoiding the operational overhead of running/discovering multiple processes for a project this size. The one real process boundary is **frontend ↔ backend**, over HTTP/JSON, which is where React and FastAPI actually need an API contract.

## Layer by layer

**Ingestion** (`backend/app/routers/ingestion.py`)
Receives raw posts (from `tools/simulator/csv_producer.py` or a real API later), enriches with metadata, hands off to the queue.
- FastAPI route `POST /ingestion/ingest`, calls the queue router's `enqueue_item()` directly (same process, no HTTP hop)

**Streaming Queue** (`backend/app/routers/queue.py`)
Buffers events between ingestion and preprocessing.
- In-memory `asyncio`-friendly `collections.deque` FIFO (enqueue/dequeue, drop-oldest-when-full) — sufficient at prototype scale, no external broker needed
- Step-up option if the queue needs to survive a restart or be shared across multiple worker processes: **Redis** (`redis-py` lists/streams)

**Preprocessing** (`backend/app/routers/preprocessing.py`)
Cleans text and detects language before analysis.
- `re` / `emoji` / `ftfy` for text cleaning (URLs, mentions, hashtags, emoji-to-text)
- `langdetect` or fastText `lid.176` for language identification

**Situation Analysis Engine** (`backend/app/routers/analysis.py`, helpers in `backend/app/analysis/`)
Sentiment, need detection, fake-news risk, priority scoring.
- **Hugging Face Transformers + PyTorch** (already chosen) run as plain Python inference calls, in-process
- No dedicated model server (TorchServe/Triton) needed at this scale — load models once at app startup

**Summarization Engine** (`backend/app/routers/summarization.py`)
- HF `transformers` pipeline with **mT5** (already chosen)

**Evidence Extractor** (`backend/app/routers/evidence.py`)
Selects and ranks top supporting posts.
- `sentence-transformers` (SBERT / LaBSE, already chosen) for embeddings + cosine similarity ranking

**Metadata Catalog / Evidence Store** (`backend/app/db.py`)
- **MongoDB** via `motor` (async, matches the FastAPI app) — `situations` and `evidence` collections

**Human Review Interface + Situation Routing Dashboard** (`frontend/`)
The two human-facing HLD screens.
- **React + Vite** — a proper presentation layer talking to the backend's `situations`/`analytics` endpoints (`backend/app/routers/situations.py`) over `fetch`/JSON
- Why React over the Streamlit option considered earlier: Streamlit is faster to stand up but Python-only with no real frontend/backend separation; React matches the team's preferred 3-tier architecture and is the more standard "presentation layer," at the cost of a second toolchain (`npm`/`package.json`) and needing CORS configured on the backend (`backend/app/config.py` → `CORS_ORIGINS`)

**Dev / runtime**
- `uvicorn app.main:app --reload` to serve the backend (one port, 8000)
- `npm run dev` (Vite) to serve the frontend (one port, 5173)
- `docker-compose` (optional, not yet added) to run backend + frontend + MongoDB together for a local demo

## Summary table

| Layer | Tool | Why (prototype-appropriate) |
|---|---|---|
| Backend shape | FastAPI modular monolith (routers) | One process, module-per-layer; avoids N-microservice overhead |
| Ingestion | FastAPI router + tweepy/httpx (tools/) | Matches existing ingestion logic; simple REST endpoint |
| Streaming Queue | In-memory FIFO (deque) | Already implemented; no broker overhead for prototype traffic |
| Preprocessing | re / emoji / ftfy / langdetect | Lightweight, no training required |
| Situation Analysis | HF Transformers + PyTorch | Reuses already-chosen models; in-process inference is enough at this scale |
| Summarization | mT5 (HF pipeline) | Already chosen |
| Evidence Extraction | sentence-transformers (SBERT/LaBSE) | Already chosen; simple similarity ranking |
| Storage | MongoDB (motor) | Already chosen; flexible schema for evolving metadata |
| Presentation layer | React + Vite | Standard 3-tier split; talks to backend over REST/JSON |
| Frontend ↔ backend | fetch + CORS | The one real process boundary in this architecture |
| Runtime | uvicorn (backend), Vite dev server (frontend) | Standard for each stack; docker-compose optional later |
