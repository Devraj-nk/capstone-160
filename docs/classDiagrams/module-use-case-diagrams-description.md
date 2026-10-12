# Per-Module Use-Case Description

This document explains the use-case diagrams in
[`module-use-case-diagrams.puml`](./module-use-case-diagrams.puml). The module
boundaries follow [`ModulesRelation.png`](./classDiagrams/ModulesRelation.png):
Presentation, Orchestration, Input Processing, Analysis, Clustering,
Situation, Evidence, Persistent, and Review and Routing.

Each `@startuml ... @enduml` block is a separate diagram. Copy one block at a
time into draw.io using **Arrange → Insert → Advanced → PlantUML**.

The diagrams describe both the current prototype and the intended complete
system. A use case marked as planned in the table is shown to document the
future workflow; it does not mean that the functionality is already complete.

## Actors

| Actor | Description |
|---|---|
| Social Media Source / Simulator | External source that streams posts into the system. The current development implementation is the CSV producer. |
| Frontend Client | React/Vite client that calls the FastAPI API. |
| Human Reviewer | Reviews pending situations and approves or rejects them. |
| Department Officer | Handles situations routed to Healthcare, Municipal, Law and Policies, or Tourism. |
| Admin / Analyst | Monitors queues and analytics and configures future thresholds and evaluation functions. |
| Internal module actor | A neighboring module that invokes the module being documented. |
| Database / MongoDB | External persistence system used by the Persistent Module. |

## 1. Presentation Layer

### Purpose

The Presentation Layer is the React/Vite user interface. It presents
information returned by the backend and sends user decisions to the API. It
does not perform the analysis itself.

### Use cases

| Use case | Description | Status |
|---|---|---|
| Open Review Console | Opens the screen used to inspect pending situations. | Implemented |
| View Pending Situations | Retrieves situations whose status is pending. | Implemented |
| Approve Situation | Sends an approval decision for a selected situation. | Implemented |
| Reject Situation | Sends a rejection decision for a selected situation. | Implemented |
| Open Dashboard | Opens the situation-routing dashboard. | Implemented |
| View Situation Summary | Displays total, pending, confirmed, and rejected counts. | Implemented |
| View Department Counts | Displays counts grouped by department. | Implemented |

### Relationships

Approval and rejection include viewing the pending list because the reviewer
must select a situation before making a decision. The dashboard obtains
summary and department information through the API client.

## 2. Orchestration Layer

### Purpose

The Orchestration Layer is the FastAPI entry point. It contains routers inside
one process, matching the modular-monolith design in `ModulesRelation.png`.

### Use cases

| Use case | Description | Status |
|---|---|---|
| Receive Ingestion Request | Accepts an incoming raw post. | Implemented |
| Receive Processing Request | Accepts preprocessing or analysis requests. | Implemented |
| Receive Situation Request | Accepts situation and analytics requests. | Implemented |
| Register Routers | Registers the module routers with FastAPI. | Implemented |
| Return Health Status | Reports whether the application is available. | Implemented |

### Relationships

The FastAPI application registers the ingestion, processing, and situation
routers. The routers delegate work to the corresponding modules rather than
containing the complete business process themselves.

## 3. Input Processing Module

### Purpose

This module accepts raw posts and prepares them for analysis. It handles
validation, metadata, queueing, text cleaning, duplicate detection, and
language detection.

### Use cases

| Use case | Description | Status |
|---|---|---|
| Stream Posts | Reads records from a simulator and sends them to ingestion. | Implemented |
| Validate Incoming Post | Checks that the incoming post is usable and within input limits. | Implemented |
| Add Ingestion Metadata | Adds pipeline metadata and ingestion time. | Implemented |
| Enqueue Post | Places an ingested post in the FIFO queue. | Implemented |
| Drop Oldest Post When Full | Removes the oldest item when queue capacity is reached. | Implemented |
| Dequeue Post | Removes the oldest queue item for processing. | Implemented |
| Clean Text | Normalizes text before model processing. | Implemented |
| Detect Duplicate or Repost | Uses a text fingerprint to identify repeated content. | Implemented |
| Detect Language | Finds the language of a valid post. | Implemented |
| Detect Romanized Text | Identifies a language written in romanized form. | Implemented |
| Detect Code-Mixed Text | Identifies posts containing mixed languages or scripts. | Implemented |
| View Queue Health | Returns current queue size and configured maximum size. | Implemented |

### Relationships

Streaming leads to validation and metadata enrichment. Metadata enrichment
leads to queue insertion. If the queue is full, dropping the oldest post is
an extension of enqueueing. A dequeued post is cleaned, deduplicated, and
passed through language detection before analysis.

## 4. Analysis Module

### Purpose

The Analysis Module produces structured information about a post. It combines
the disaster classifier, departmental need detector, sentiment analyzer,
fake-news scorer, and severity/actionability calculations.

### Use cases

| Use case | Description | Status |
|---|---|---|
| Run Analysis Pipeline | Coordinates the analysis operations for a processed post. | Implemented |
| Classify Disaster | Determines whether the post is disaster-related. | Implemented |
| Detect Department Needs | Calculates needs for relevant departments. | Implemented |
| Analyze Sentiment | Calculates sentiment and negativity. | Implemented |
| Calculate Severity | Estimates how serious the post or event is. | Implemented |
| Calculate Actionability | Estimates whether an operational response is required. | Implemented |
| Combine Analysis Outputs | Merges model results into one analysis result. | Implemented |
| Use Zero-Shot Fallback | Uses fallback classification for low-confidence need detection. | Planned |
| Calculate Fake Score | Estimates misinformation or fake-news risk. | Partially implemented |
| Configure Model Thresholds | Allows an analyst to change model thresholds. | Planned |
| Evaluate Model Metrics | Measures model accuracy and other evaluation metrics. | Planned |

### Relationships

The analysis pipeline includes disaster, need, and sentiment analysis. Their
outputs are combined with severity and actionability. Zero-shot fallback
extends need detection when normal confidence is insufficient. The combined
result is sent to clustering.

## 5. Clustering Module

### Purpose

The Clustering Module groups related analyzed posts into event clusters. A
cluster represents posts that likely describe the same real-world event.

### Use cases

| Use case | Description | Status |
|---|---|---|
| Generate Text Embedding | Converts post text into a vector representation. | Implemented |
| Compare with Existing Clusters | Compares a post with cluster centroids. | Implemented |
| Assign Post to Cluster | Adds a post to the best matching cluster. | Implemented |
| Create New Cluster | Creates a cluster when no suitable match exists. | Implemented |
| Check Time Window | Verifies that related posts are close enough in time. | Implemented |
| Check Department Overlap | Verifies that department relevance overlaps. | Implemented |
| Recalculate Cluster Centroid | Updates the representative vector after a new member is added. | Implemented |
| Run Periodic Reclustering | Merges similar clusters during periodic maintenance. | Implemented with optional dependency |
| Identify Complete Situations | Finds clusters large enough to become situations. | Implemented |
| Clear Clusters | Clears the in-memory cluster state. | Implemented |

### Relationships

Assigning a post includes embedding generation and comparison. Comparison
includes time-window and department-overlap checks. Creating a new cluster is
an extension used when no existing cluster matches. Complete clusters are
passed to the Situation Module.

## 6. Situation Module

### Purpose

The Situation Module converts significant clusters into situation records and
manages their review lifecycle.

### Use cases

| Use case | Description | Status |
|---|---|---|
| Create Situation from Cluster | Creates a situation from a significant cluster. | Partially implemented |
| Generate Situation Summary | Produces a concise description of the cluster. | Partially implemented |
| Calculate Situation Priority | Adds priority information to the situation. | Implemented |
| List Situations | Retrieves situations for reviewers or administrators. | Implemented |
| Filter by Status | Filters situations by their lifecycle status. | Implemented |
| View Situation Details | Displays text, priority, department, summary, and status. | Implemented |
| Approve Situation | Changes a pending situation to confirmed. | Implemented |
| Reject Situation | Changes a pending situation to rejected. | Implemented |
| Update Situation Status | Changes the situation lifecycle state. | Partially implemented |
| Request Supporting Evidence | Requests representative posts from the Evidence Module. | Partially implemented |

### Relationships

Creating a situation uses a cluster, summary, priority, and supporting
evidence. Listing situations can include status filtering. Approval and
rejection include a status update. The currently used states are pending,
confirmed, and rejected; routed, acknowledged, and resolved are planned.

## 7. Evidence Module

### Purpose

The Evidence Module selects representative posts that support a situation and
protects private information before storage.

### Use cases

| Use case | Description | Status |
|---|---|---|
| Extract Evidence Posts | Starts evidence extraction for a cluster. | Implemented |
| Rank Representative Posts | Ranks posts by relevance or representativeness. | Implemented |
| Select Top Posts | Selects the configured number of best posts. | Implemented |
| Mask Personal Details | Masks personal information in evidence text. | Implemented |
| Mask Sensitive Metadata | Masks sensitive metadata values. | Implemented |
| Store Evidence | Stores protected evidence records. | Implemented |
| View Evidence | Retrieves evidence for reviewers or situation screens. | Partially implemented |

### Relationships

Extraction includes ranking, top-post selection, and privacy masking. Storing
and viewing evidence use the Persistent Module.

## 8. Persistent Module

### Purpose

The Persistent Module provides a shared MongoDB access boundary for situations,
evidence, and future persistent records.

### Use cases

| Use case | Description | Status |
|---|---|---|
| Open Database Collection | Obtains a MongoDB collection by name. | Implemented |
| Save Document | Inserts a situation or evidence document. | Implemented |
| Find Documents | Retrieves multiple documents matching a query. | Implemented |
| Find One Document | Retrieves one matching document. | Implemented |
| Update Document | Updates selected document fields. | Implemented |
| Delete Document | Deletes a document. | Implemented |

### Relationships

All database operations use a collection. Situation, evidence, and review
operations access MongoDB through this shared boundary instead of opening
independent database connections.

## 9. Review and Routing Module

### Purpose

This module supports human verification and the future departmental response
lifecycle.

### Use cases

| Use case | Description | Status |
|---|---|---|
| View Pending Situation | Opens a situation awaiting review. | Implemented |
| View Evidence | Examines supporting evidence before deciding. | Partially implemented |
| Vote True or Fake | Records a reviewer reliability vote. | Planned |
| Approve Situation | Confirms a situation for operational handling. | Implemented |
| Reject Situation | Rejects a situation. | Implemented |
| Auto-Demote Linked Situations | Reduces priority when fake votes dominate. | Planned |
| Route Confirmed Situation | Sends a confirmed situation to a department queue. | Planned |
| View Department Queue | Allows an officer to view assigned situations. | Planned |
| Acknowledge Situation | Records receipt by a department officer. | Planned |
| Mark Situation Resolved | Records completion of departmental work. | Planned |
| Monitor Routing Status | Allows an administrator to monitor routing progress. | Planned |

### Relationships

Reviewers view evidence before approving or rejecting a situation. Approval
includes routing in the intended complete workflow. True/fake voting can
extend to automatic demotion. Department officers work with department
queues, while administrators monitor routing status.

## 10. Cross-module processing flow

```text
Social Media Source / Simulator
              |
              v
     Receive Ingestion Request
              |
              v
      Validate and Enqueue Post
              |
              v
       Preprocess and Detect Language
              |
              v
        Run Analysis Pipeline
              |
              v
          Cluster Posts
              |
              v
        Create Situation
              |
              v
        Extract Evidence
              |
              v
       Store in MongoDB
              |
              v
       Human Review Decision
              |
              v
       Department Routing
```

The final routing, acknowledgement, resolution, voting, access control, and
evaluation stages are documented as planned behavior where they are not yet
fully implemented.

## 11. Complete use-case item description table

| ID | Module | Use case | Actor | Description | Status |
|---|---|---|---|---|---|
| P1 | Presentation | Open Review Console | Human Reviewer | Opens the review interface. | Implemented |
| P2 | Presentation | View Pending Situations | Human Reviewer | Displays pending situations. | Implemented |
| P3 | Presentation | Approve Situation | Human Reviewer | Sends an approval decision. | Implemented |
| P4 | Presentation | Reject Situation | Human Reviewer | Sends a rejection decision. | Implemented |
| P5 | Presentation | Open Dashboard | Admin / Analyst | Opens the dashboard. | Implemented |
| P6 | Presentation | View Situation Summary | Admin / Analyst | Displays situation counts. | Implemented |
| P7 | Presentation | View Department Counts | Admin / Analyst | Displays department totals. | Implemented |
| O1 | Orchestration | Receive Ingestion Request | Simulator | Receives a raw post. | Implemented |
| O2 | Orchestration | Receive Processing Request | Frontend Client | Receives processing requests. | Implemented |
| O3 | Orchestration | Receive Situation Request | Frontend Client | Receives situation requests. | Implemented |
| O4 | Orchestration | Register Routers | FastAPIApp | Registers backend routers. | Implemented |
| O5 | Orchestration | Return Health Status | Monitor | Returns API health. | Implemented |
| I1 | Input Processing | Stream Posts | Simulator | Sends posts into ingestion. | Implemented |
| I2 | Input Processing | Validate Incoming Post | System | Checks input validity. | Implemented |
| I3 | Input Processing | Add Ingestion Metadata | System | Adds timestamps and metadata. | Implemented |
| I4 | Input Processing | Enqueue Post | System | Adds a post to the FIFO queue. | Implemented |
| I5 | Input Processing | Dequeue Post | Analysis Module | Removes a post for processing. | Implemented |
| I6 | Input Processing | Drop Oldest Post When Full | System | Removes the oldest item at capacity. | Implemented |
| I7 | Input Processing | Clean Text | System | Normalizes post text. | Implemented |
| I8 | Input Processing | Detect Duplicate or Repost | System | Detects repeated content. | Implemented |
| I9 | Input Processing | Detect Language | System | Detects post language. | Implemented |
| I10 | Input Processing | Detect Romanized Text | System | Detects romanized language. | Implemented |
| I11 | Input Processing | Detect Code-Mixed Text | System | Detects mixed-language text. | Implemented |
| I12 | Input Processing | View Queue Health | Admin / Analyst | Displays queue statistics. | Implemented |
| A1 | Analysis | Run Analysis Pipeline | Input Processing | Coordinates model analysis. | Implemented |
| A2 | Analysis | Classify Disaster | System | Detects disaster-related posts. | Implemented |
| A3 | Analysis | Detect Department Needs | System | Detects required assistance. | Implemented |
| A4 | Analysis | Analyze Sentiment | System | Calculates sentiment. | Implemented |
| A5 | Analysis | Calculate Severity | System | Estimates seriousness. | Implemented |
| A6 | Analysis | Calculate Actionability | System | Estimates need for action. | Implemented |
| A7 | Analysis | Combine Analysis Outputs | System | Creates one analysis result. | Implemented |
| A8 | Analysis | Use Zero-Shot Fallback | System | Handles low-confidence need detection. | Planned |
| A9 | Analysis | Calculate Fake Score | System | Estimates fake-news risk. | Partially implemented |
| A10 | Analysis | Configure Model Thresholds | Admin / Analyst | Changes model thresholds. | Planned |
| A11 | Analysis | Evaluate Model Metrics | Admin / Analyst | Measures model quality. | Planned |
| C1 | Clustering | Generate Text Embedding | System | Creates a text vector. | Implemented |
| C2 | Clustering | Compare with Existing Clusters | System | Compares against cluster centroids. | Implemented |
| C3 | Clustering | Assign Post to Cluster | System | Assigns a post to an event cluster. | Implemented |
| C4 | Clustering | Create New Cluster | System | Creates a cluster when no match exists. | Implemented |
| C5 | Clustering | Check Time Window | System | Checks temporal proximity. | Implemented |
| C6 | Clustering | Check Department Overlap | System | Checks departmental similarity. | Implemented |
| C7 | Clustering | Recalculate Cluster Centroid | System | Updates a cluster vector. | Implemented |
| C8 | Clustering | Run Periodic Reclustering | Admin / Analyst | Merges or reorganizes clusters. | Implemented with optional dependency |
| C9 | Clustering | Identify Complete Situations | Situation Module | Finds clusters large enough for situations. | Implemented |
| C10 | Clustering | Clear Clusters | Admin / Analyst | Clears active clusters. | Implemented |
| S1 | Situation | Create Situation from Cluster | Clustering Module | Creates a situation from a cluster. | Partially implemented |
| S2 | Situation | Generate Situation Summary | System | Produces a concise summary. | Partially implemented |
| S3 | Situation | Calculate Situation Priority | System | Assigns priority information. | Implemented |
| S4 | Situation | List Situations | Reviewer / Admin | Retrieves situations. | Implemented |
| S5 | Situation | Filter by Status | Reviewer / Admin | Filters situation records. | Implemented |
| S6 | Situation | View Situation Details | Reviewer | Displays situation details. | Implemented |
| S7 | Situation | Approve Situation | Reviewer | Confirms a pending situation. | Implemented |
| S8 | Situation | Reject Situation | Reviewer | Rejects a situation. | Implemented |
| S9 | Situation | Update Situation Status | System | Changes lifecycle status. | Partially implemented |
| S10 | Situation | Request Supporting Evidence | Situation Module | Requests evidence for a situation. | Partially implemented |
| E1 | Evidence | Extract Evidence Posts | Situation Module | Starts evidence extraction. | Implemented |
| E2 | Evidence | Rank Representative Posts | System | Ranks supporting posts. | Implemented |
| E3 | Evidence | Select Top Posts | System | Selects the best evidence posts. | Implemented |
| E4 | Evidence | Mask Personal Details | System | Protects personal information. | Implemented |
| E5 | Evidence | Mask Sensitive Metadata | System | Protects metadata. | Implemented |
| E6 | Evidence | Store Evidence | Persistent Module | Stores evidence records. | Implemented |
| E7 | Evidence | View Evidence | Reviewer | Displays supporting evidence. | Partially implemented |
| D1 | Persistent | Open Database Collection | Internal module | Opens a MongoDB collection. | Implemented |
| D2 | Persistent | Save Document | Internal module | Inserts a document. | Implemented |
| D3 | Persistent | Find Documents | Internal module | Retrieves documents. | Implemented |
| D4 | Persistent | Find One Document | Internal module | Retrieves one document. | Implemented |
| D5 | Persistent | Update Document | Internal module | Updates document fields. | Implemented |
| D6 | Persistent | Delete Document | Internal module | Deletes a document. | Implemented |
| R1 | Review and Routing | View Pending Situation | Reviewer | Opens a situation for review. | Implemented |
| R2 | Review and Routing | View Evidence | Reviewer | Examines supporting evidence. | Partially implemented |
| R3 | Review and Routing | Vote True or Fake | Reviewer | Records a reliability vote. | Planned |
| R4 | Review and Routing | Approve Situation | Reviewer | Confirms a situation. | Implemented |
| R5 | Review and Routing | Reject Situation | Reviewer | Rejects a situation. | Implemented |
| R6 | Review and Routing | Auto-Demote Linked Situations | System | Lowers priority after fake votes. | Planned |
| R7 | Review and Routing | Route Confirmed Situation | Review Service | Sends a confirmed situation to a department. | Planned |
| R8 | Review and Routing | View Department Queue | Department Officer | Views assigned situations. | Planned |
| R9 | Review and Routing | Acknowledge Situation | Department Officer | Records receipt. | Planned |
| R10 | Review and Routing | Mark Situation Resolved | Department Officer | Records completion. | Planned |
| R11 | Review and Routing | Monitor Routing Status | Admin / Analyst | Monitors department handling. | Planned |