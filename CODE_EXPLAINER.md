# Code Explainer: The EvidenceGate Lifecycle

The EvidenceGate Runtime executes a strict, linear progression ensuring that all observations are causally valid, governable, and safely persisted. This document traces the pipeline lifecycle.

### 1. Input Source
External components feed raw data into the system via `InputSource` adapters. These raw buffers hold vendor-specific metadata.

### 2. Canonical Observation / Control Event
The `Canonicalizer` transforms raw buffers into immutable `NetworkObservationEnvelope` objects. It computes critical time boundaries (like `causal_available_time`) purely and deterministically without DB side-effects.

### 3. Quality & Canonicalization
Any malformed inputs at the canonicalization stage yield `QualityGap` records rather than halting the pipeline, protecting subsequent lanes.

### 4. Router
The `RelevanceRouter` examines the envelope's `ObservationType`. It evaluates static, pure `route()` predicates registered by plugins to produce a list of relevant targets. Control events never enter this router.

### 5. Lane Ingress & Ingest Admission
For each relevant target, the `AdmissionEvaluator` verifies the observation against the `PluginManifest` requirements and the `LaneGovernance` snapshot. If a lane is marked `ANALYTIC_UNAVAILABLE`, admission yields a typed rejection reason.

### 6. State / Shard
If admitted, the plugin computes a `StateKey`. The Runtime hashes the key against the plugin ID to dispatch the observation to a deterministic `LaneShard` (`asyncio.Queue`). This isolates entity processing sequentially, avoiding race conditions. 
*Note: If the queue is saturated, the router drops the event and emits a QueueFull `QualityGap`.*

### 7. Evaluation Readiness
The shard consumer pulls the payload, fetching the current memory state from the `StateStore`. 

### 8. Analytic / Scaffold
The `AnalyticPlugin.process()` hook fires. It executes synchronous/asynchronous analytic logic against the payload and state, returning one or more `ResultDraft` sequences. Scaffold implementations are used here during testing.

### 9. Validator
Before persistence, the `ResultValidator` intercepts the draft. It verifies that pipelines in `EVIDENCE_CONSTRUCTION` (like scaffolds) are not illegally attempting to emit `ThreatAlert` results.

### 10. Atomic Persistence
Valid drafts are converted to full `Result` unions. The `SqliteWriter` atomically inserts them using `INSERT OR IGNORE` in WAL-mode, ensuring that linked relationships are safely ignored if the parent ID duplicates.

### 11. API / UI
The FastAPI layer (`app.py`) exposes a durable HTTP cursor for reading these immutable SQLite records, and a bounded WebSocket `/live` queue that safely drops frames for slow clients to protect server event-loop health.
