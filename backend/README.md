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

| Env var | Default | Meaning |
|---|---|---|
| `MODEL_BACKEND` | `auto` | `hf` = fine-tuned Hugging Face models; `offline` = keyword/hashing heuristics (no downloads, **not** trained models); `auto` = `hf` if torch/transformers/sentence-transformers are installed, else `offline` |
| `PIPELINE_WORKER_ENABLED` | `true` | Background task that drains the ingestion queue through the full pipeline |
| `PIPELINE_POLL_INTERVAL` | `0.5` | Seconds the worker sleeps when the queue is empty |
| `AUTO_ROUTE_CRITICAL_MINUTES` | `2` | Unreviewed Critical situations are auto-routed (unverified) after this; `0` = never |
| `AUTO_ROUTE_HIGH_MINUTES` | `10` | Same for High. Medium/Low and likely-fake ones always wait for a reviewer |
| `ESCALATION_CHECK_SECONDS` | `10` | How often the worker checks for overdue situations |
| `AUTHOR_HASH_SALT` | `change-me` | Secret salt for `author_ref` hashes — set your own |
| `DROPPED_RETENTION_DAYS` | `7` | How long `dropped_tweets` are kept (TTL index) |

## End-to-end pipeline

`app/pipeline/orchestrator.py` chains every step for each queued post; the background
worker (`app/pipeline/worker.py`) runs it continuously:

```
/ingestion/ingest -> queue -> clean/validate -> repost dedup -> language -> disaster gate
  -> sentiment + needs -> combine -> embedding + incremental clustering
  -> (cluster has >= 3 posts) cluster scoring: credibility, fake score, priority + band (app/scoring)
  -> step 10 summary + evidence (app/scoring/summary_evidence.py) -> department routing
  -> MongoDB: tweets / dropped_tweets, situations (upserted per cluster, evidence inside)
  -> /situations review: approve = routing ticket per needed department; reject / mark fake
     cancels tickets; every decision stored as a verdict
  -> no reviewer in time (Critical 2 min, High 10 min, not likely-fake): auto_routed with
     unverified tickets, still in the review queue for a human verdict
```

**Auto-escalation.** Routing normally waits for a human, but an urgent situation must not
wait forever if nobody is at the console. Each pending High/Critical situation gets an
`escalation_due_at` (the earliest deadline is kept if it rises from High to Critical; it is
cleared if it drops to Medium/Low). The worker routes overdue ones as `auto_routed`: tickets are
marked `verified: false` and the situation stays in the review queue. A reviewer's approve then
verifies the tickets; reject / mark fake cancels them. Likely-fake situations are never
auto-routed (acting on a rumour is worse than waiting), and escalation writes no verdict —
verdicts are human labels only. The band and fake flag are the scoring module's heuristic
tags, so this routes on machine judgement; the per-band confirmation rate from the verdicts is
how that gets checked.

Step 10 uses no model (see `docs/Step 10 — Summary & Evidence Spec.pdf`): the summary is a
template filled only from computed fields (event, place, impact, report/language counts, time
span, main need, rumour warning), and a slot with no data is left out. The same slots are
rendered in English, Hindi, Kannada, Tamil and Telugu (`app/scoring/summary_templates.py`;
situations and tickets carry `summary_i18n`, the console has a language selector). The
non-English phrases are a first draft pending native-speaker review. Evidence is 3–5
independent posts ranked by `0.6·Similarity + 0.4·PostStrength`, one per copy group,
forward-chain posts skipped, at most 2 per language, each with a `why`. `text_en` (English
translation for reviewers) is a hook for IndicTrans2 and is null for non-English posts until
that model is added; mT5/IndicBART abstractive summaries are future work.

Posts stop early (logged in `dropped_tweets` with the reason) when invalid, a repost, or
rejected by the disaster gate. A cluster below 3 posts is "holding" until more reports arrive.
New posts re-score an existing situation but never overwrite its review decision.

### Storage (MongoDB)

Collection names live in `app/db.py`; `ensure_indexes()` creates the indexes at startup.

| Collection | One document = | Written by | Read by |
|---|---|---|---|
| `tweets` | a post that passed both gates, with model outputs, `cluster_id` and its `embedding` (float32 bytes, removed once its cluster is past the 48 h window) (upserted by id) | pipeline | cluster restore, rescoring |
| `dropped_tweets` | a post removed before analysis: `reason` (`invalid` / `repost` / `not_disaster`) + `detail`; deleted after 7 days | pipeline | dashboard gate counts |
| `clusters` | clustering state of one live cluster, including small "holding" ones: `centroid` (float32 bytes, ~3 KB at 768-d), `tweet_ids`, `dept_relevance`, `created_at` / `last_updated_at`, `embedding_model`, `active` | pipeline | startup restore |
| `situations` | the reviewable view of a cluster with 3+ posts: scores, band, summary, representative post, ranked privacy-masked evidence (`evidence_posts`), `tweet_ids`, review `status` (`pending` / `auto_routed` / `confirmed` / `rejected` / `fake`), `escalation_due_at`, `score_history` (last 20 rescorings) | pipeline, review | console, dashboard |
| `verdicts` | each review decision (`true` / `not_relevant` / `fake`) with a frozen snapshot of the scores at that moment | review | evaluation / retraining |
| `routing_tickets` | one situation in one department queue: `routed` → `acknowledged` → `resolved` (or `cancelled`), with `history`; `queue_priority` follows rescoring | review, departments | department queues |
| `daily_reports` | one day's situation report (local date), stored automatically once the day ends | worker, on demand | reports page |

Evidence is kept inside its situation, so a rescore replaces summary and evidence in one write
and they can never disagree. The separate `evidence` collection is only used by the standalone
`POST /evidence/store` endpoint, not by the pipeline.

Clusters survive restarts: at startup the active clusters (same ids) are rebuilt from
`clusters` + their tweets' embeddings, so new posts about a tracked event join it and update
the same situation. Member embeddings stay on the tweets (not in the cluster document, which a
large cluster would push past Mongo's 16 MB limit). A cluster whose last post is older than the
48 h window can't grow any more, so it is marked inactive and its tweets' embeddings are removed —
stored vectors stay bounded to about two days of posts. Clusters made with a different embedding
model (e.g. offline vs IndicSBERT) are not restored, since their vectors aren't comparable.

Not stored on purpose: per-reviewer votes (single reviewer, no login — the decision is the
verdict) and a `config_versions` collection (git history records which weights were live). Privacy: phone numbers
are masked in all stored text, location metadata is redacted in evidence, and usernames / user
ids are replaced by a salted `author_ref` hash before anything is stored.

| Endpoint | Purpose |
|---|---|
| `GET /pipeline/stats` | Model backend, worker state, queue size, cluster counts, per-stage counts, last error |
| `POST /pipeline/process` | Run one raw post through the whole pipeline now, bypassing the queue |
| `POST /pipeline/drain?max_items=N` | Process queued posts now (when the worker is disabled) |
| `POST /pipeline/reset` | Clear in-memory clusters / repost counts / stats (MongoDB untouched) |
| `POST /pipeline/escalate` | Run the auto-escalation check now (the worker runs it every 10 s) |
| `GET /situations/{id}`, `GET /situations/{id}/evidence` | One situation / its stored evidence |
| `POST /situations/{id}/decision` | `approve` / `reject` / `fake` (+ optional `note`) |
| `GET /tickets?department=&status=` | A department's queue, highest priority first |
| `POST /tickets/{id}/status` | `acknowledged` / `resolved` (invalid transitions → 409) |
| `GET /analytics/response` | Median time to acknowledge / resolve per band and department, overdue open tickets, reviewer wait |
| `GET /analytics/trends` | Live board by band, Growing / Stable / Fading per active situation, posts per hour (24 h) |
| `GET /analytics/heatmaps` | Department × hour of day and need × language (last 7 days) |
| `GET /reports/daily`, `GET /reports/daily/{YYYY-MM-DD}`, `GET /reports/daily/today`, `POST /reports/daily/{day}` | List / read / today so far / rebuild the daily report |

### Analytics (`app/analytics/`)

`metrics.py` holds pure functions over the stored documents; `service.py` loads them.

- **Response:** from each ticket's `history` — time from routed to first acknowledgement
  (resolving counts) and to resolution, medians per band and per department; open tickets not
  acknowledged within `ACK_LIMIT_MINUTES` (Critical 15, High 60, Medium 240, Low 1440) are counted
  as overdue (display only); reviewer wait = situation created → human decision.
- **Trends:** reports of each active situation in the last hour vs the hour before:
  `change = (last − previous) / max(1, previous)`, ≥ +20 % growing, ≤ −20 % fading, else stable,
  none in either hour = quiet. "Now" is the newest post time, so replayed data behaves like live
  data. Exact reposts never count (dropped in preprocessing); near-copies do.
- **Heatmaps** (general, not geographic — posts rarely carry reliable locations): reports per
  department (same routing rule as tickets) and local hour of day; mean need score per language
  (romanized and code-mixed shown separately).
- **Daily report:** situations active that day (wall clock), ordered by peak priority, with
  location, languages, departments and time from detection to first acknowledgement; a
  department table (opened / acknowledged / resolved / cancelled / unverified); counts of pending,
  fake and rejected. The worker stores yesterday's report once the day has ended; the reports page
  prints to PDF from the browser.

Hours of day and report days use `ANALYTICS_TZ_OFFSET_MINUTES` (default 330 = IST).

The queue and repost counts live in process memory only: posts still queued at shutdown are
lost, and a repost of a pre-restart post is not recognised as one.

## Router map

| Router | Prefix | Purpose |
|---|---|---|
| `app/routers/ingestion.py` | `/ingestion` | Receives raw posts, enriches with metadata, pushes to the queue |
| `app/routers/queue.py` | `/queue` | In-memory FIFO buffer between ingestion and preprocessing |
| `app/routers/preprocessing.py` | `/preprocessing` | Text cleaning + language detection |
| `app/routers/analysis.py` | `/analysis` | Sentiment, need detection, fake-news, priority scoring (helpers in `app/analysis/`) |
| `app/routers/summarization.py` | `/summarization` | Situation summary generation |
| `app/routers/evidence.py` | `/evidence` | Top-post / evidence selection |
| `app/routers/clustering.py` | `/clustering` | Incremental clustering of combined records |
| `app/routers/pipeline.py` | `/pipeline` | Orchestrator controls and stats (see above) |
| `app/routers/situations.py` | `/situations`, `/analytics` | What the **frontend** calls: list pending/confirmed situations, record review decisions, analytics summary |

`app/db.py` holds the shared MongoDB (motor) client and the `situations` / `evidence`
collections. `app/schemas/` holds the shared Pydantic models.

Because everything runs in one process, `ingestion.py` calls into `queue.py`'s
`enqueue_item()` directly as a function call — no HTTP hop between them, unlike the earlier
two-process prototype this was migrated from.

## Tools

Standalone scripts, not part of the API process — run them against a live backend:

- `tools/simulator/csv_producer.py` — streams `ingestion.csv` rows into `/ingestion/ingest`
  (every column except the text is sent as an attribute; `--timestamp-column timestamp`
  replays the CSV's own times instead of "now")
- `tools/consumer/print_consumer.py` — polls `/queue/dequeue` and prints what it gets. It
  competes with the pipeline worker for queue items, so start the backend with
  `PIPELINE_WORKER_ENABLED=false` when using it.
- `tools/trace_pipeline.py` — offline input/output trace of the individual stage endpoints

```bash
# terminal 1
uvicorn app.main:app --reload --port 8000
# terminal 2
python tools/simulator/csv_producer.py --limit 20
# terminal 3 (optional)
python tools/consumer/print_consumer.py --max-messages 20
```
