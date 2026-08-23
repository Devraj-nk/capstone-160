# Multilingual Sentiment & Need Detection for Real-Time Crisis Monitoring and Departmental Routing

**Capstone Project 160** · UE23CS320A/B · Guide: Dr. Saritha

A real-time, multilingual system that analyzes social media posts during crises and emergencies to detect **sentiment**, **urgent needs**, and **fake/misleading content**, then routes verified, prioritized alerts to the appropriate government department (Disaster Management, Healthcare, Law & Order, Public Safety, Transportation, and Public Municipal).

## Problem Statement

During crises, people share information, emotions, and help requests on social media in multiple languages — often with sarcasm, code-mixing, and mixed sentiment that make automated analysis hard. Existing sentiment analysis tools are largely English-only, don't detect actual *needs*, can't tell credible posts from misinformation, and offer no automated routing to the departments that need to act. This leads to delayed, inefficient crisis response.

This project builds a real-time multilingual pipeline that detects sentiment and needs from social media data, scores posts for credibility and priority, and routes them to the relevant department for timely action — with a human reviewer in the loop before anything is dispatched.

## Objectives

- Real-time multilingual social media analysis (including low-resource and code-mixed languages)
- Joint sentiment and need detection
- Sarcasm and complex-language handling that can flip a post's meaning
- Fake news / misinformation detection and credibility scoring
- Priority and severity scoring so the most urgent posts surface first
- Situation summarization and evidence extraction (top supporting posts + metadata)
- Human-validated automatic departmental routing
- Dashboard-based monitoring, trends, heatmaps, and reports

## Architecture

The system is organized into five layers: **Ingestion → Preprocessing → AI Analysis → Evidence & Human Validation → Routing & Analytics**.

![High-Level Design](docs/HLD.png)

**Layers**

| Layer | Responsibility |
|---|---|
| Ingestion Layer | Pulls real-time posts from social media APIs into a streaming queue |
| Preprocessing Module | Text cleaning (URLs, mentions, hashtags, emojis) and language detection |
| Situation Analysis Engine | Situation/disaster classification, fake-news risk scoring, priority/severity scoring |
| Summarization Engine | Generates a concise summary of the detected situation |
| Evidence Extractor | Selects top supporting posts and extracts metadata |
| Human Review Interface | Reviewer confirms or rejects the AI-generated result before routing |
| Situation Routing Dashboard | Routes confirmed cases to the correct department; shows trends, heatmaps, daily reports |
| Metadata Catalog / Evidence Store | Persists processed metadata and supporting evidence |

**End-to-end data flow**

![Data Flow](docs/data_flow_swimlanes.jpg)

1. **Ingestion** — fetch/simulate social media posts, push to a streaming queue.
2. **Preprocessing** — clean text, detect language.
3. **AI Analysis** — sentiment analysis → need detection → summarization → fake-news risk scoring → priority scoring → critical/normal classification.
4. **Evidence & Validation** — extract top posts and metadata, store evidence, human review (approve/reject).
5. **Routing & Analytics** — route confirmed events to the owning department, update the dashboard, generate reports.

## Models & Methods

| Task | Approach |
|---|---|
| Sentiment analysis | Fine-tuned **XLM-RoBERTa**; zero-shot fallback via **mDeBERTa-v3-base-mnli-xnli** / **BART-large-MNLI** |
| Disaster / crisis classification | Fine-tuned **BERTweet-base** |
| Need detection | Multi-label **XLM-R** classifier (Healthcare, Law, Public Services, Tourism, …), zero-shot NLI fallback |
| Department routing | Zero-shot **BART-large-MNLI**, and an **SBERT**-based semantic similarity + keyword-boost classifier |
| Fake news / credibility | Hybrid: XLM-R fake-probability model + credibility score (account age, followers, verified) + content-risk detection |
| Summarization | **mT5** |
| Evidence ranking | Sentence embeddings (Sentence-BERT / LaBSE) + similarity-to-priority weighted ranking |

**Scoring formulas**

- **Priority score** = 0.35 × Need Severity + 0.25 × Sentiment + 0.2 × Urgency (keyword-based) + 0.1 × Credibility + 0.1 × Recency
- **Fake score** = 0.5 × Model Prediction + 0.3 × (1 − Credibility) + 0.2 × Content Risk
- **Credibility** = 0.4 × Account Age + 0.4 × Followers + 0.2 × Verified

**Stack:** Python, PyTorch, Hugging Face Transformers, Sentence-Transformers, scikit-learn, Pandas/NumPy, FastAPI (ingestion/queue services), MongoDB (storage).

## Datasets

| Dataset | Purpose |
|---|---|
| [XNLI](https://github.com/facebookresearch/XNLI) | Multilingual semantic foundation / cross-lingual pretraining |
| [CrisisLex T15](https://crisislex.org/data-collections.html) | Actionable need detection (disaster-related labeled tweets) |
| [News Headlines Sarcasm Dataset](https://www.kaggle.com/datasets/rmisra/news-headlines-dataset-for-sarcasm-detection) | Sarcasm detection |
| [DravidianCodeMix](https://github.com/bharathichezhiyan/DravidianCodeMix-Dataset) | Code-mixed language identification (Tamil/Malayalam/Kannada-English) |
| SentiMix (SemEval-2020) | Code-mixed sentiment (Hinglish) |
| Disaster Tweets (Kaggle) | Disaster vs. non-disaster tweet classification |
| AI4Bharat multilingual sentiment | Indic-language sentiment (Hindi, Kannada, Tamil, Telugu) |
| TweetEval | Large-scale real-world sentiment/keyword extraction |

## Project Status

Currently in the data preprocessing, base model training, and evaluation stage (Capstone Phase 2). Design docs and architecture diagrams live in [docs/](docs/).

## Project Structure

Standard 3-tier split: **React** (presentation) → **FastAPI** (application/API) → **MongoDB** (storage), in explicit `backend/` / `frontend/` folders. The backend is a *modular monolith* — a single FastAPI app, one process — with every HLD layer as its own router (`backend/app/routers/<layer>.py`) so a member can own a layer's code without needing to run or coordinate a separate service for it. The frontend covers the two human-facing HLD screens. Full rationale in [docs/TECH_STACK.md](docs/TECH_STACK.md).

```
capstone-160/
├── backend/                  # single FastAPI app (modular monolith)
│   ├── app/
│   │   ├── main.py            # app instance, CORS, router registration
│   │   ├── db.py               # MongoDB (motor) client
│   │   ├── schemas/             # shared Pydantic models
│   │   ├── analysis/             # sentiment / need_detection / fake_news / priority_scoring helpers
│   │   └── routers/
│   │       ├── ingestion.py      # done — POST /ingestion/ingest
│   │       ├── queue.py           # done — in-memory FIFO queue
│   │       ├── preprocessing.py    # scaffold — text cleaning, language detection
│   │       ├── analysis.py          # scaffold — sentiment, need detection, fake-news, priority
│   │       ├── summarization.py      # scaffold — situation summarization
│   │       ├── evidence.py            # scaffold — evidence extraction + evidence store
│   │       └── situations.py           # scaffold — API the frontend calls (review + analytics)
│   └── tools/                 # simulator / consumer scripts (not part of the API process)
├── frontend/                  # React + Vite
│   └── src/pages/
│       ├── ReviewPage.jsx      # scaffold — Human Review Interface
│       └── DashboardPage.jsx   # scaffold — Situation Routing Dashboard
└── docs/                     # architecture diagrams, tech stack notes, ESA decks
```

Run:

```bash
# backend — one process, one port
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# frontend — separate dev server, proxies API calls to the backend
cd frontend
npm install
npm run dev   # http://localhost:5173
```

Endpoint stubs currently pass data through unchanged or return placeholder values — swap in the real model/logic per router's TODOs. `backend/app/routers/situations.py` is the one new piece with no earlier equivalent: it's the API contract the React frontend actually calls (`GET /situations`, `POST /situations/{id}/decision`, `GET /analytics/summary`), backed by MongoDB.

## Team

Project ID 160 — Guide: **Dr. Saritha**

| Name | SRN | Contribution |
|---|---|---|
| Akshata Udaganve | PES2UG23CS043 | AI4Bharath dataset preprocessing, sentiment model training |
| Christananda B | PES2UG23CS158 | Tweepy dataset preprocessing and class extraction |
| Devraj Ishwar Naik | PES2UG23CS167 | SentiMix dataset preprocessing and reconstruction, data ingestion layer |
| Favaz Ahmed Alam | PES2UG23CS190 | Disaster dataset preprocessing, class extraction |

## Docs

- [docs/HLD.png](docs/HLD.png) — High-level architecture diagram
- [docs/data_flow_swimlanes.jpg](docs/data_flow_swimlanes.jpg) — End-to-end data flow (swimlane view)
- [docs/160_Phase1_ESA_PPT.pptx](docs/160_Phase1_ESA_PPT.pptx) — Phase 1 End Semester Assessment
- [docs/160_Phase_2_ESA.pptx](docs/160_Phase_2_ESA.pptx) — Phase 2 End Semester Assessment
