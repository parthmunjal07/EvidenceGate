# Architecture & Data Flow

EvidenceGate is a brokering pipeline connecting raw ingest sources to independent analytic lanes.

## Core Concepts

- **Observation**: An immutable factual record mapped from physical network traffic (e.g., a packet or flow) via a `Canonicalizer`. Not yet subjected to analytics.
- **Evidence**: Cryptographically or causally linked observations that have been explicitly processed and cited by an `AnalyticPlugin`.
- **Result**: The typed output of a lane's processing (e.g., `ThreatAlert`, `ReviewFinding`, `AnalyticUnavailable`).

## Data Flow Pipeline

1. **Input Source**: Network events are consumed from external sources (`evidencegate/ingest/source.py`).
2. **Canonicalization**: The `Canonicalizer` transforms raw vendor payloads into a pure, immutable `NetworkObservationEnvelope` without persisting to the database.
3. **Relevance Routing**: The `RelevanceRouter` examines the `ObservationType` and routes the observation to zero or more statically configured lane plugins.
4. **Admission**: For each relevant lane, the `AdmissionEvaluator` verifies required fields and checks the read-only `LaneGovernance` snapshot. If inadmissible, processing halts for that lane and a typed rejection may be emitted.
5. **State Sharding**: Admitted observations are assigned a deterministic `StateKey` and routed to a specific `LaneShard` (`asyncio.Queue`).
6. **Analytic Processing**: The FIFO shard consumer executes the `AnalyticPlugin.process()` hook, passing in the observation and the lane's bounded state block.
7. **Validation & Persistence**: The plugin yields `ResultDraft` sequences. The `ResultValidator` verifies structural constraints (e.g., scaffolds cannot emit `ThreatAlert`). Valid drafts are promoted to `Result` objects and appended to SQLite idempotently by the `SqliteWriter`.

## Queue Saturation & Backpressure
If the `LaneShard` queue is full (saturation), the runtime immediately catches `asyncio.QueueFull`, drops the observation for that specific lane, and generates a `QualityGap` record. This protects system integrity without halting other independent lanes.
