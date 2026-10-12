# Per-Module Class Diagram Description

This document explains the per-module class diagrams in [`module-class-diagrams.puml`](./module-class-diagrams.puml). The diagrams are based on [`ModulesRelation.png`](./classDiagrams/ModulesRelation.png) and the current FastAPI, React, and MongoDB project structure.

Each diagram is intentionally separated into its own PlantUML block. Copy one `@startuml ... @enduml` block at a time into draw.io:

**Arrange → Insert → Advanced → PlantUML**

The diagrams describe the architecture at module level. Some classes represent current Python modules, routers, Pydantic schemas, or helper functions rather than literal Python classes. This preserves the architectural meaning of the existing implementation while also showing the incomplete and planned parts of the system.

## Implementation labels

The diagrams do not use labels on every class because the module boundaries already indicate the implementation area. The current status is:

- **Implemented:** ingestion, in-memory queueing, preprocessing, language detection, analysis helpers, clustering, evidence ranking, privacy masking, situation APIs, dashboard analytics, and MongoDB helper functions.
- **Partially implemented:** situation management, summarization, review operations, and evidence presentation.
- **Planned:** complete true/fake voting, automatic demotion, department routing, department queues, acknowledgement and resolution, role-based access control, model feedback, and evaluation metrics.

## 1. Presentation Layer

### Responsibility

The Presentation Layer is the user-facing part of the application. It is implemented using React and Vite. It provides the human review interface and the situation dashboard.

### Classes

#### FrontEnd

`FrontEnd` represents the React pages and components.

It is responsible for:

- Displaying pending situations.
- Displaying confirmed situations.
- Showing priority and department information.
- Showing errors returned by the backend.
- Sending reviewer decisions through the API client.
- Displaying summary analytics on the dashboard.

Important state includes the current list of situations, dashboard summary data, and any request error.

#### APIClient

`APIClient` represents the frontend HTTP client in `frontend/src/api/client.js`.

It hides the details of HTTP requests from the React pages. It provides operations for:

- Getting pending situations.
- Getting confirmed situations.
- Submitting approval or rejection decisions.
- Retrieving analytics summary data.

### Relationship

`FrontEnd` depends on `APIClient`. `APIClient` communicates with the `FastAPIApp`. This is the main process boundary in the system: the React development server communicates with the FastAPI backend using HTTP and JSON.

## 2. Orchestration Layer

### Responsibility

The Orchestration Layer is the entry point for backend requests. It organizes the FastAPI application into routers rather than deploying each module as a separate service.

### Classes

#### FastAPIApp

`FastAPIApp` represents the main application in `backend/app/main.py`.

It:

- Creates the FastAPI application.
- Registers the ingestion, queue, preprocessing, analysis, clustering, evidence, summarization, and situation routers.
- Configures middleware such as CORS.
- Provides the application health endpoint.

#### IngestionRouter

`IngestionRouter` represents the `/ingestion` router.

It receives a raw event, enriches it with metadata, creates an ingested event, and places the event into the queue.

#### ProcessingRouter

`ProcessingRouter` represents the preprocessing and analysis endpoints.

It exposes operations for:

- Cleaning and validating text.
- Detecting language.
- Running individual analysis functions.
- Running the combined pipeline.

#### SituationRouter

`SituationRouter` represents the situation and analytics endpoints.

It supports:

- Listing situations by status.
- Approving a situation.
- Rejecting a situation.
- Returning situation counts and department statistics.

### Relationship

`FastAPIApp` aggregates the routers. The routers are separate modules, but they execute inside the same FastAPI process. This matches the modular-monolith structure shown in `ModulesRelation.png`.

## 3. Input Processing Module

### Responsibility

The Input Processing Module receives incoming posts and prepares them for analysis. It contains the simulator boundary, ingestion logic, queue, text cleaning, duplicate detection, and language detection.

### Classes

#### DataSimulator

`DataSimulator` represents the external CSV producer in `backend/tools/simulator/csv_producer.py`.

It:

- Reads records from a dataset.
- Sends records to the ingestion endpoint.
- Waits for the configured interval between records.

It is shown as an external tool because it is not part of the running FastAPI application.

#### IngestionService

`IngestionService` represents the logic inside the ingestion router.

It:

- Accepts a raw event.
- Validates the text and event fields.
- Adds pipeline metadata.
- Creates an ingested event identifier.
- Creates a queue item.
- Returns the queue result to the caller.

#### RawEvent

`RawEvent` is the input data-transfer object. It contains the original text, creation timestamp, and optional attributes.

#### IngestedEvent

`IngestedEvent` is the enriched event created after ingestion. It contains the generated identifier, original timestamps, ingestion timestamp, and metadata.

#### QueueItem

`QueueItem` is the object placed in the queue. It wraps the ingested event payload and records when it was queued.

#### QueueManager

`QueueManager` represents the in-memory queue in `backend/app/routers/queue.py`.

It:

- Maintains FIFO ordering.
- Adds new queue items.
- Removes items for processing.
- Removes the oldest item when the maximum size is reached.
- Reports queue size and maximum capacity.

The current queue is process-local. It is not persistent and is not shared between multiple backend workers.

#### Preprocessor

`Preprocessor` represents the functions in the cleaning and deduplication modules.

It:

- Removes unwanted text patterns.
- Validates whether the cleaned text can be analyzed.
- Registers repeated text fingerprints.
- Marks repeated or invalid posts as dropped.

#### PreprocessResult

`PreprocessResult` represents the result returned after preprocessing. It records cleaned text, validity, repost count, drop status, and language information.

#### LanguageDetector

`LanguageDetector` represents the language helpers in `backend/app/preprocessing/language.py`.

It:

- Detects language from the post.
- Uses script-based detection where possible.
- Identifies romanized text.
- Identifies code-mixed text.

#### LanguageInfo

`LanguageInfo` stores the detected language, romanization flag, and code-mixing flag.

### Relationships

The simulator sends raw events to the ingestion service. The ingestion service creates an ingested event and queue item. The queue supplies items to preprocessing. The preprocessor calls the language detector and returns a preprocessing result.

## 4. Analysis Module

### Responsibility

The Analysis Module performs machine-learning and rule-based analysis on processed text. It produces the information needed for clustering and situation creation.

### Classes

#### Model

`Model` is an architectural abstraction for prediction models. It defines the common `predict()` operation.

The current code uses standalone Python functions rather than a literal shared base class. The abstraction is shown to explain the common role of the three model components.

#### DisasterClassifier

`DisasterClassifier` determines whether a post is related to a disaster or emergency.

Its result includes:

- A boolean disaster decision.
- A disaster confidence value.

#### NeedDetector

`NeedDetector` identifies the department or assistance category suggested by a post.

Its responsibilities include:

- Producing department-specific scores.
- Applying configured thresholds.
- Returning active needs.
- Providing a future zero-shot fallback for low-confidence cases.

The departments can include healthcare, municipal services, law and policies, and tourism.

#### SentimentAnalyzer

`SentimentAnalyzer` determines the emotional characteristics of a post.

It produces:

- A sentiment label.
- A confidence value.
- A negativity score.

It can also process batches of texts.

#### AnalysisEngine

`AnalysisEngine` coordinates the model calls. It obtains the required model outputs and passes them to the combiner.

It represents the processing behavior exposed by the analysis router.

#### Combiner

`Combiner` merges the independent model results.

It calculates:

- Severity.
- Actionability.
- A combined analysis record.

The combiner is important because clustering should receive one consistent processed record rather than several unrelated model outputs.

#### ProcessedPost

`ProcessedPost` represents the cleaned post before or during analysis. It provides the identity, text, creation time, and detected language required by the analysis engine.

#### AnalysisResult

`AnalysisResult` represents the merged result used by later modules.

It contains:

- Post identity and text.
- Language.
- Disaster decision and confidence.
- Department needs.
- Sentiment result.
- Severity.
- Actionability.
- Embedding data when available.

### Relationships

The three model classes specialize the abstract `Model`. The analysis engine calls the disaster classifier, need detector, sentiment analyzer, and combiner. The combiner creates the analysis result, which is passed to the clustering module.

## 5. Clustering Module

### Responsibility

The Clustering Module groups related analysis results into event clusters. A cluster represents multiple posts that likely describe the same real-world situation.

### Classes

#### EmbeddingGenerator

`EmbeddingGenerator` converts post text into a numeric vector. The current implementation uses the embedding helper in `backend/app/analysis/embedding.py`.

Embeddings allow posts to be compared using vector similarity.

#### ClusterManager

`ClusterManager` manages active clusters.

It uses:

- Similarity threshold.
- Department overlap threshold.
- Time-window limit.
- Minimum cluster size.

Its operations include:

- Assigning a new analysis result to an existing cluster.
- Creating a new cluster when no suitable cluster exists.
- Periodically reclustering cluster centroids.
- Separating sufficiently large situations from small holding clusters.
- Clearing the in-memory cluster state.

#### Cluster

`Cluster` stores the posts and embeddings associated with one event.

It contains:

- A cluster identifier.
- Member analysis results.
- Member embeddings.
- A centroid vector.
- Creation and update times.
- Department relevance information.

When a member is added, the centroid and department relevance can be updated.

### Relationships

The cluster manager requests embeddings, manages multiple clusters, and assigns analysis results. Each cluster aggregates one or more analysis results. A sufficiently large cluster can be converted into a situation by the Situation Module.

## 6. Situation Module

### Responsibility

The Situation Module turns significant clusters into situations that can be reviewed, displayed, stored, and eventually routed.

### Classes

#### SituationManager

`SituationManager` manages situation records.

It is responsible for:

- Creating a situation from a cluster.
- Listing situations.
- Filtering situations by status.
- Approving situations.
- Rejecting situations.
- Updating lifecycle status.

In the current project, this behavior is partly represented by the situation router and situation schema.

#### Situation

`Situation` is the main report-like data object. It stores:

- Situation identifier.
- Text and language.
- Sentiment and need results.
- Fake-news information.
- Priority information.
- Department.
- Summary.
- Evidence identifiers or evidence records.
- Current status.
- Creation time.

The currently used statuses are pending, confirmed, and rejected. Routed, acknowledged, and resolved are included as planned lifecycle states.

#### Summarizer

`Summarizer` produces a short description of the cluster.

The current endpoint has a simple text-based fallback. A complete model-based summarizer is planned.

#### SituationStatus

`SituationStatus` describes the lifecycle of a situation:

- `Pending`: waiting for human review.
- `Confirmed`: accepted by a reviewer.
- `Rejected`: rejected by a reviewer.
- `Routed`: sent to a department.
- `Acknowledged`: received by a department officer.
- `Resolved`: handled by the department.

Only the first three states are currently active in the implementation.

### Relationships

The Situation Manager receives a cluster, uses the summarizer, and creates a situation. It manages multiple situations and later coordinates evidence, review, persistence, and routing.

## 7. Evidence Module

### Responsibility

The Evidence Module selects representative posts that support a situation and protects sensitive information before storage or display.

### Classes

#### EvidenceManager

`EvidenceManager` coordinates evidence extraction and storage.

It:

- Receives posts from a cluster.
- Selects the most representative posts.
- Applies privacy masking.
- Creates evidence records.
- Stores the evidence.

#### Evidence

`Evidence` represents a supporting post.

It contains:

- Evidence identifier.
- Original post identifier.
- Cluster identifier.
- Text.
- Metadata.

#### EvidenceRanker

`EvidenceRanker` selects the most useful posts from a cluster. It supports top-k selection and representative-post ranking.

#### PrivacyManager

`PrivacyManager` removes or masks sensitive information.

It:

- Masks personal details in text.
- Masks sensitive metadata.
- Helps prevent private information from being stored as evidence.

### Relationships

The evidence manager reads cluster members, asks the ranker to select representative posts, asks the privacy manager to protect them, and manages the resulting evidence records.

## 8. Persistent Module

### Responsibility

The Persistent Module provides a shared database abstraction for the rest of the application.

### Classes

#### DatabaseClient

`DatabaseClient` represents the helper functions in `backend/app/db.py`.

It provides:

- Collection access.
- Document insertion.
- Multiple-document queries.
- Single-document queries.
- Document updates.
- Document deletion.

The current implementation uses Motor, the asynchronous MongoDB driver for Python.

#### MongoDB

`MongoDB` represents the external database used by the application. The main collections currently include situations and evidence. The collection helper is flexible enough to support future collections such as clusters.

### Relationships

The database client uses MongoDB. MongoDB stores situation and evidence documents. Situation, review, routing, and evidence components use the client instead of connecting directly to the database.

## 9. Review and Routing Module

### Responsibility

The Review and Routing Module covers human verification and departmental handling. The review portion is partially implemented, while the full routing lifecycle is planned.

### Classes

#### ReviewService

`ReviewService` manages reviewer decisions.

It is intended to:

- Record true or fake votes.
- Approve a situation.
- Reject a situation.
- Automatically demote linked reports when fake votes dominate.

The current implementation supports basic approve and reject decisions through the situation endpoint.

#### ReviewVote

`ReviewVote` represents one reviewer decision.

It contains:

- Reviewer identifier.
- Vote value.
- Timestamp.

The separate vote model and vote aggregation are planned.

#### RoutingService

`RoutingService` sends confirmed situations to the appropriate department queue.

The routing decision can use the detected department and a queue multiplier or priority configuration.

#### DepartmentQueue

`DepartmentQueue` stores situations assigned to a department.

It is intended to support:

- Adding a situation.
- Viewing assigned situations.
- Acknowledging receipt.
- Updating a situation to resolved.

### Relationships

The review service acts on situations and can trigger routing after approval. The routing service places a situation in a department queue. Each department queue contains multiple situations.

## 10. Relationship with ModulesRelation.png

The per-module diagrams correspond to the areas shown in the reference image:

| Reference module | Detailed diagram |
|---|---|
| Presentation Layer | `PresentationLayer` |
| Orchestration Layer | `OrchestrationLayer` |
| InputProcessing | `InputProcessingModule` |
| Analysis Module | `AnalysisModule` |
| ClusteringModule | `ClusteringModule` |
| SituationModule | `SituationModule` |
| EvidenceModule | `EvidenceModule` |
| PersistentModule | `PersistentModule` |
| Review and Routing | `ReviewRoutingModule` |

The diagrams preserve the reference image's major flow:

```text
FrontEnd -> APIClient -> FastAPIApp
FastAPIApp -> Routers
Routers -> Input Processing
Input Processing -> Analysis
Analysis -> Clustering
Clustering -> Situation
Situation -> Evidence
Situation and Evidence -> DatabaseClient
```

The review and routing module is included as an extension of the situation workflow. It documents the intended complete system even though department routing, reviewer voting, and officer status updates are not yet fully implemented.

## 11. Current versus planned boundaries

The diagrams intentionally show both the current implementation and the intended architecture:

- The input, analysis, clustering, evidence, and persistence boundaries are already represented in the codebase.
- `SituationManager` is represented across the situation router and situation schema and is therefore marked conceptually rather than as one current Python class.
- `ReviewService` currently supports basic decisions but not the complete voting workflow.
- `RoutingService` and `DepartmentQueue` document the planned department lifecycle.
- `DataSimulator` is an external script, not a backend service class.
- The diagrams should not be interpreted as proof that every displayed class already exists as a standalone source-code class.
