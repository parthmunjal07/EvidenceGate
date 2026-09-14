# Code Explainer: The EvidenceGate Lifecycle
**Contract Authority:** `MVP_IMPLEMENTATION_CONTRACT_v1.1.md`

The EvidenceGate Runtime executes a strict, linear progression ensuring that all observations are causally valid, governable, and safely persisted. This document traces the pipeline lifecycle stage by stage.

---

## Pipeline Order (Exact)

```
InputSource
→ pure Canonicalizer
→ NetworkObservations + RuntimeControlEvents
→ quality/visibility (QualityGap)
→ zero-to-many relevance router
→ bounded lane ingress queue
→ ingest admission (IngestAdmissionDecision — Phase 1)
→ state-key calculation
→ deterministic shard dispatch
→ factual state update
→ evaluation readiness (EvaluationReadinessDecision — Phase 2)
→ analytic/scaffold
→ result validator
→ atomic SQLite persistence
→ REST/WebSocket/UI
```

---

## Stage-by-Stage Explanation

### 1. InputSource (`ingest/source.py`)
External components feed raw records into the system via the `InputSource` protocol. Each source has a `source_id`, `source_kind`, and emits `RawSourceRecord` objects with a timestamp and position. The source is opened to produce a `SourceManifest` that declares capture bounds.

### 2. Pure Canonicalizer (`ingest/canonicalizer.py`)
The `FlowCanonicalizer` transforms `RawSourceRecord` → `CanonicalizationResult`.

Key properties (IC-15):
- **Pure**: no I/O, no logging calls, no queue writes
- **Deterministic**: same `source_id + position` → same `observation_id`
- **Side-effect-free**: result is a frozen `CanonicalizationResult` with `tuple[NetworkObservation, ...]` and `tuple[RuntimeControlEvent, ...]`
- **Causal time**: `causal_available_time = max(record.timestamp, export_time)` for terminal flows (IC-04)
- **Field presence**: `present_fields: frozenset[str]` computed from actual payload values (never fabricated)

### 3. Separate Event Unions (`domain/events.py`)
`NetworkObservation` and `RuntimeControlEvent` are distinct types. Control events never enter the relevance router (IC-01). They reach a lane only through its declared lifecycle hooks (`on_quality_gap`, `on_watermark`, etc.).

### 4. Quality / Visibility (`domain/quality.py`)
`QualityGap` is an immutable record with `gap_id`, `scope`, time interval, `count`, `gap_types`, and `reason`. Created for: upstream loss, router/lane loss, parser failures, queue saturation. Never discarded silently (IC-06).

### 5. Relevance Router (`routing/router.py`)
`RelevanceRouter` compiles `ObservationType → candidate lanes` at registration. For each observation, invokes only candidates' pure `route()` predicates. Returns `tuple[LaneTarget, ...]` (zero to many). No state mutation, no I/O, no confidence calculation.

### 6. Bounded Lane Ingress Queue (`runtime/dispatcher.py`)
Each lane has a bounded `asyncio.Queue(maxsize=)`. On saturation: `_handle_queue_saturation()` creates a typed `QualityGap`, updates `LaneHealthRecord`, calls `gap_sink`, and invokes the declared `GapAction` from the plugin manifest. No silent discard.

### 7. Ingest Admission — Phase 1 (`admission/evaluator.py:AdmissionEvaluator`)
`IngestAdmissionDecision` is computed before any state mutation. Checks:
- `governance.ingest_permitted`
- Observation type ∈ `manifest.accepted_observation_types`

**MUST NOT** check or set `WARMING_UP`, `INSUFFICIENT_HISTORY`, or `STATE_EVICTED` — those are Phase 2 evaluation readiness states (IC-16). A rejection produces a typed `IngestAdmissionDecision` with `admitted=False` and explicit `AdmissionReason` values. Never silently reinterpreted as benign.

### 8. State-Key Calculation
`plugin.state_key(observation)` returns a `StateKey | None`. Stateless plugins return `None` (shard 0).

### 9. Deterministic Shard Dispatch (`runtime/shard.py:compute_shard`)
`shard = SHA256(plugin_id || "||" || state_key) mod shard_count`

Uses SHA-256, not Python's randomised `hash()`. Same key → same shard in every run (IC-05). Different keys may land on different shards that process concurrently.

### 10. Factual State Update (`runtime/shard.py:LaneShard._consume`)
`StateStore.get(key)` fetches current state. `ShardKeyState.record_observation()` increments the observation count for this key. **This always runs for admitted observations** — readiness state never blocks the factual update (IC-16).

### 11. Evaluation Readiness — Phase 2 (`admission/evaluator.py:EvaluationReadinessEvaluator`)
`EvaluationReadinessDecision` computed after factual state update. States:
- `WARMING_UP`: count ≤ warmup_threshold (first observation)
- `READY`: count > warmup_threshold (second+ observations)
- `STATE_EVICTED`: key was evicted by TTL/resource pressure
- `TERMINAL_EVIDENCE_PENDING`: waiting for terminal evidence

Passed to plugin via `context["readiness"]`.

### 12. Analytic / Scaffold (`plugins/scaffolds/basic_scaffold.py`)
`plugin.process(observation, context, state)` returns `Sequence[ResultDraft]`. The scaffold emits `ReviewFinding` only — no `ThreatAlert`, no confidence, no severity (IC-08).

### 13. Result Validator (`results/validator.py`)
`ResultValidator.validate(result, governance)` enforces:
- `result.result_type ∈ governance.allowed_result_types` (IC-17 — enum-vs-enum, never inferred from status names)
- No `ThreatAlert` from scaffold lane (IC-08)
- `ThreatAlert` must have `confidence` defined
- Non-alert results cannot carry `confidence` or `severity`
- 3-level taxonomy and version strings required

### 14. Atomic SQLite Persistence (`persistence/sqlite.py`)
`SqliteWriter._write_result_sync()` wraps a single `BEGIN` / `COMMIT` / `ROLLBACK`:
1. `INSERT OR IGNORE INTO results` — idempotent parent row
2. `rowcount == 0` check → if duplicate, skip children (no-op)
3. `INSERT INTO evidence_items` (mandatory)
4. `INSERT INTO provenance_references` (mandatory)
5. `INSERT INTO missing_prerequisites`
6. `INSERT INTO result_links` (CorrelationFinding only)
7. `COMMIT`

On any exception: `ROLLBACK` entire transaction; no partial row (IC-18).

### 15. REST / WebSocket / UI
FastAPI skeleton (`api/`) exposes durable cursor REST endpoints and a bounded `/live` WebSocket queue. Slow WebSocket clients receive `QueueFull` and must reload via REST cursor — they cannot block the analytic path (IC-12).

---

## What This Runtime Does NOT Do

- Decide that a threat occurred
- Compute confidence, severity, or threat scores in the shared runtime
- Implement DDoS, DGA, DNS tunnelling, C2, encrypted-session, reconnaissance, or unusual-transfer detectors
- Infer result permissions from scientific status names
- Create gaps and silently discard them
- Allow partial SQLite result rows to persist on failure
- Emit `ThreatAlert` from scaffold or governance-unavailable lanes
