# SIH26145 — MVP IMPLEMENTATION CONTRACT v1.1

**Status:** `IMPLEMENTATION-AUTHORITATIVE`  
**Scope:** shared EvidenceGate product/runtime infrastructure only  
**Authority:** `MVP_SYSTEM_RESEARCH_HANDOFF_v1.2`, Amendment A1, and `DEC-SYS-01`–`DEC-SYS-27`  
**Non-authority:** this contract does not admit a detector, threshold, feature, state key, history horizon, model, label, confidence meaning, severity mapping, or correlation score.

---

## 1. Build objective and hard boundaries

Build one single-host Python application that accepts passive/replay inputs, converts them into immutable network observations, routes each observation to zero or more relevant lanes, performs independent lane admission, runs bounded entity-affine state where declared, persists immutable results, and exposes generic REST/WebSocket/UI data.

The application must preserve this separation:

```text
InputSource
  ↓
Pure Canonicalizer
  ├── NetworkObservations
  └── RuntimeControlEvents
  ↓
Quality / Visibility
  ↓
Zero-to-many Relevance Router
  ↓
Bounded Lane Ingress Queue
  ↓
Ingest Admission
  ↓
State-Key Calculation
  ↓
Deterministic Shard Dispatch
  ↓
Factual State Update
  ↓
Evaluation Readiness
  ↓
Analytic / Scaffold Plugin
  ↓
Result Validator
  ↓
Atomic SQLite Persistence
  ↓
REST / WebSocket / UI
```

The runtime must not decide that a threat occurred. It must not silently turn absence, loss, or an unavailable analytic into a benign result.

---

## 2. Required package boundaries

```text
evidencegate/
  domain/          immutable data objects and enums only
  ingest/          InputSource adapters and canonicalizers
  quality/         source manifests, snapshots, gaps
  governance/      read-only versioned scientific snapshots
  registry/        static lane/plugin registry and manifest validation
  routing/         relevance router only
  admission/       lane admission only
  runtime/         queues, shards, state, lifecycle supervision
  plugins/         scaffold/transparent/ML implementations behind contracts
  results/         result union, validator, evidence references
  persistence/     SQLite repositories and migrations
  api/             REST and WebSocket DTOs
  metrics/         Prometheus instrumentation and snapshots
  ui/              generic client; no analytic logic
  tests/           contract, integration, replay, and benchmark fixtures
```

Dependencies flow inward: `api`, `persistence`, `runtime`, and `plugins` may depend on `domain`; `domain` must depend on none of them. A plugin must not import FastAPI, SQLite repositories, UI code, or another plugin's private state.

---

## 3. Domain model

### 3.1 Implementation conventions

- Hot-path domain objects are `@dataclass(frozen=True, slots=True)` or immutable equivalents.
- All IDs are opaque strings/UUIDs; no ID embeds an IP, domain, or threat conclusion.
- UTC-aware timestamps are required. Performance timings use a monotonic clock and are not network facts.
- Field absence is explicit: `present_fields` is authoritative for whether a field was observed. `None` means the field was absent or not supplied. `UNKNOWN` means the field was observed, but its factual value could not be determined. Canonicalization never manufactures an observation.
- API DTO validation may use Pydantic. Do not require Pydantic objects on the hot path.

### 3.2 Core enums

```text
ObservationType = PACKET | FLOW | DNS | TLS | QUIC

ControlType = SOURCE_STARTED | SOURCE_PAUSED | SOURCE_ENDED | SOURCE_FAILED |
              WATERMARK_ADVANCED | QUALITY_GAP_OPENED | QUALITY_GAP_CLOSED |
              PARSER_ERROR_OBSERVED | LANE_HEALTH_CHANGED |
              SCIENTIFIC_STATUS_IMPORTED | INTEGRATION_STATUS_CHANGED |
              OPERATIONAL_HEALTH_CHANGED

OfficialPsCategory = DDOS | C2_BEACONING | DGA_AND_DNS_TUNNELLING |
                     ENCRYPTED_SESSIONS | RECONNAISSANCE_AND_PORT_SCANNING |
                     DATA_EXFILTRATION

AnalyticFamily = DDOS | C2 | DGA | DNS_TUNNELLING | ENCRYPTED_SESSION |
                 RECON | UNUSUAL_TRANSFER

IntegrationStatus = RESEARCHING | OBSERVATION_CONTRACT_READY |
                    RUNTIME_SCAFFOLD_READY | BASELINE_IMPLEMENTED | DEMO_READY

OperationalHealth = HEALTHY | BACKPRESSURED | STALLED | FAILED | DISABLED |
                    SHUTTING_DOWN

ScientificStatus = ANALYTIC_UNAVAILABLE | EVIDENCE_CONSTRUCTION |
                   BASELINE_UNDER_VALIDATION | ANALYTIC_VALIDATING | MODEL_VALIDATED

AdmissionReason = PREREQUISITE_MISSING | UNSUPPORTED_OBSERVATION_CONTRACT |
                  INSUFFICIENT_VISIBILITY | ANALYTIC_UNAVAILABLE |
                  INSUFFICIENT_HISTORY | STATE_EVICTED

GapAction = CONTINUE_WITH_QUALITY_FLAG | RESET_AFFECTED_STATE |
            REENTER_WARMUP | ABSTAIN_UNTIL_RECOVERED | DISABLE_LANE

ResultType = THREAT_ALERT | REVIEW_FINDING | ANALYTIC_UNAVAILABLE |
             PREREQUISITE_MISSING | INSUFFICIENT_EVIDENCE |
             QUALITY_DEGRADED | PLUGIN_STATUS | CORRELATION_FINDING
```

`analytic_lane`, `scientific_phase`, `scientific_blockers`, observation-contract identifiers, and plugin IDs are versioned strings/enums supplied through configuration. Do not infer them from names or packet content.

### 3.3 Separate event unions

```python
NetworkObservation = PacketObservation | FlowObservation | DNSObservation | TLSObservation | QUICObservation
CanonicalEvent = NetworkObservation | RuntimeControlEvent
```

`NetworkObservationEnvelope` contains:

```text
observation_id, schema_version, observation_type,
event_time, causal_available_time, ingest_time,
source_id, source_kind, source_position, observation_contract,
wire_direction, direction_basis, finality, availability_basis,
provenance_ref, quality_ref, present_fields, typed_payload
```

`RuntimeControlEvent` uses a distinct envelope:

```text
control_event_id, schema_version, control_type,
event_time? , ingest_time, source_id?, lane_id?,
provenance_ref?, quality_ref?, typed_payload
```

The relevance router accepts `NetworkObservation` only. Control events reach a lane only through its declared lifecycle hook.

### 3.4 Typed payload minimums

The implementation must define separate immutable payload classes. It may add a field only when the adapter can state its provenance and availability basis.

| Type | Minimum payload contract |
|---|---|
| `PacketObservation` | lengths, observed L2/L3/L4 facts, addresses/ports where applicable, flags/sequence facts where observed, fragmentation, raw reference |
| `FlowObservation` | flow-ID basis, endpoints, protocol, start/end/export times, supplied directional counters, finality, exporter semantics, sampling, documented end state |
| `DNSObservation` | flow reference, observed direction, QR state when decoded, transaction ID, QNAME/QTYPE/QCLASS/RCODE/answers only when present, transport, truncation, clear-DNS visibility |
| `TLSObservation` | flow/session reference, observed direction, TCP reassembly state, parser version, visibly parsed handshake/record metadata, indexes, prefix time, gaps |
| `QUICObservation` | only permitted public/header facts: flow reference, direction, version, header type, length, visible connection IDs, parser version, index, timing, visibility flags |

TLS payloads never contain decrypted content. QUIC richer Initial/handshake processing is not implemented until a field-by-field observability decision exists.

---

## 4. Input, canonicalization, and quality

```python
class InputSource(Protocol):
    source_id: str
    source_kind: SourceKind
    async def open(self) -> SourceManifest: ...
    async def records(self) -> AsyncIterator[RawSourceRecord]: ...
    async def pause(self) -> None: ...          # supported only when source can pause
    async def close(self) -> None: ...
```

```python
@dataclass(frozen=True, slots=True)
class CanonicalizationResult:
    observations: tuple[NetworkObservation, ...]
    control_events: tuple[RuntimeControlEvent, ...]
```

`Canonicalizer.canonicalize(raw_record, manifest, quality) -> CanonicalizationResult` is factual and side-effect-free. The canonicalizer must:
- be deterministic;
- perform no queue writes;
- perform no database writes;
- perform no asynchronous publishing;
- perform no logging-dependent behavior;
- return observations and control events as data.

A runtime component may publish the returned control events. It must attach:

- `event_time`: underlying event time;
- `causal_available_time`: earliest time the complete emitted fact could be known;
- `finality` and `availability_basis`;
- source position and parser/provenance version;
- a field-presence set and quality reference.

Each adapter must declare its input observation contract, direction basis, timestamp meaning, sampling/drop visibility, and derived-record availability rules. A terminal flow cannot claim its final counters were available at flow start.

`QualityGap` is an immutable interval with source/lane scope, first/last known event time, count, types, reason, and detection time. It is emitted for observed upstream loss, router/lane loss, parser failures that invalidate facts, and declared capture gaps.

---

## 5. Governance configuration

Scientific governance is a read-only, versioned input loaded at run start. It is not plugin code.

```python
@dataclass(frozen=True, slots=True)
class LaneGovernance:
    analytic_lane: str
    scientific_status: ScientificStatus
    scientific_phase: str
    scientific_blockers: tuple[str, ...]
    claim_ceiling: str
    governance_version: str
    effective_at: datetime
    allowed_result_types: tuple[ResultType, ...]
    ingest_permitted: bool
```

Result permissions must come from governance configuration. Never infer permissions from `scientific_status == MODEL_VALIDATED`. A scaffold lane may explicitly allow `AnalyticUnavailable`, `PrerequisiteMissing`, `QualityDegraded`, `PluginStatus`, or `ReviewFinding`, but must not emit `ThreatAlert` unless governance explicitly permits it.

The initial snapshot must preserve the active blockers from Amendment A1, including data/admission/audit blockers for DDoS, data/validation blockers for Recon, information-mechanism/data blockers for C2, and the known DNS/TLS/QUIC/unusual-transfer blockers. A missing configuration entry disables the lane with `AnalyticUnavailable(reason_code=GOVERNANCE_DISABLED)`.

Optional `demo_capability`/`enabled_mode` may describe an engineering demonstration. It must not change `scientific_status` or claim ceiling.

---

## 6. Plugin registry, routing, and admission

### 6.1 Static registry and manifest

Plugins are compiled/explicitly registered by application configuration. Dynamic third-party discovery is out of scope.

```python
class AnalyticPlugin(Protocol):
    def manifest(self) -> PluginManifest: ...
    def route(self, observation: NetworkObservation) -> bool: ...
    def state_key(self, observation: NetworkObservation) -> StateKey | None: ...
    async def process(self, observation, context, state) -> Sequence[ResultDraft]: ...
    async def on_quality_gap(self, gap, context, state) -> Sequence[ResultDraft]: ...
    async def on_watermark(self, watermark, context, state) -> Sequence[ResultDraft]: ...
    async def on_expire(self, key, context, state) -> Sequence[ResultDraft]: ...
```

`PluginManifest` must include IDs/versions; three-level taxonomy; accepted observation types; routing predicate version; admission requirements; state-key declaration; separate scientific-history and resource-retention declarations; gap action; allowed result types; integration status; profiling hooks; and governing claim/decision IDs.

The manifest contains no DDoS rate, DNS feature, DGA lexical feature, TCP outcome rule, TLS/QUIC feature, history duration, or model parameter unless separately approved by the analytic owner.

### 6.2 Relevance router

At registration, compile `ObservationType -> candidate lanes`. For an observation, invoke only each candidate's pure, bounded `route()` predicate. A predicate must not mutate state, perform I/O, calculate confidence, or emit a result.

```python
def route(observation: NetworkObservation) -> tuple[LaneTarget, ...]
```

The router records candidate, relevant, delivered, zero-route, exception, and predicate-duration metrics. It does not check scientific eligibility.

### 6.3 Admission

The runtime explicitly distinguishes two phases of admission.

#### Phase 1 — Ingest admission
Runs before state mutation. May check:
- supported observation type;
- required factual fields;
- observation-contract compatibility;
- minimum quality/visibility needed to safely update state;
- finality/availability compatibility;
- governance ingest permission.

Must not reject because of `WARMING_UP`, `INSUFFICIENT_HISTORY`, `STATE_EVICTED`, or terminal evidence still pending.

```python
@dataclass(frozen=True, slots=True)
class IngestAdmissionDecision:
    admitted: bool
    reasons: tuple[AdmissionReason, ...]
    quality_ref: str | None
    governance_version: str
```

#### Phase 2 — Evaluation readiness
Runs after factual state update. Checks:
- warm-up state;
- insufficient history;
- state eviction;
- terminal evidence pending;
- lateness/window completion;
- other declared readiness conditions.

```python
@dataclass(frozen=True, slots=True)
class EvaluationReadinessDecision:
    readiness: EvidenceReadiness
    reason: str | None
```

A rejection must create a typed diagnostic/result when configured for user visibility; it must never be reinterpreted as benign or erased as a router miss.

---

## 7. Lane runtime, state, and backpressure

Each lane has its own bounded mailbox, health record, and one or more FIFO shards. For a declared state key:

```text
shard = stable_hash(plugin_id || normalized_state_key) mod configured_shard_count
```

Use a deterministic hash, not Python's randomized `hash()`. Shard count is fixed for a run and stored in the run manifest. Per-key processing is serial; lanes and distinct shards may proceed concurrently.

`StateStore` is plugin-owned logically and runtime-owned operationally. It requires declared key normalization, scientific history horizon, warm-up/lateness behavior, event/byte/key caps, resource TTL, eviction behavior, dedup/update rules, and gap behavior. TTL/eviction is never treated as scientific history. Eviction that makes evidence incomplete emits `STATE_EVICTED` and follows the lane's declared recovery path.

All asynchronous boundaries are bounded:

```text
source → canonicalizer/router
router → lane shard
plugin → result writer
result writer → each live client
```

Replay/validation mode pauses a pausable source when required to preserve observations. A non-pausable live source may drop lane-local observations only with `QualityGap` accounting. On every gap, invoke the lane's declared `GapAction`; the default is to avoid continuing scientific state across the gap. Result persistence is lossless: a saturated result sink pauses/marks unhealthy rather than silently dropping emitted results. A slow browser receives bounded notifications and reloads durable data by cursor.

---

## 8. Results and validation

Use one immutable tagged union. `AnalyticUnavailable` is the only unavailable/not-ready result type.

```python
Result = (
    ThreatAlert | ReviewFinding | AnalyticUnavailable | PrerequisiteMissing |
    InsufficientEvidence | QualityDegraded | PluginStatus | CorrelationFinding
)
```

Every result has immutable ID/type, created time, evidence interval where meaningful, entity reference, three-level taxonomy, plugin/analytic versions, structured status snapshot, claim ceiling, quality/provenance references, evidence items, missing prerequisites, and governing IDs.

`AnalyticUnavailable.reason_code` is one of:

```text
SCIENTIFIC_NOT_READY | SEMANTIC_TARGET_UNDEFINED | DATA_NOT_ADMITTED |
UNSUPPORTED_OBSERVATION_CONTRACT | IMPLEMENTATION_NOT_READY | GOVERNANCE_DISABLED
```

`ResultValidator` must reject:

- any `ThreatAlert` from a governance-unavailable or scaffold lane;
- a `ThreatAlert` with absent/undefined confidence semantics;
- confidence/severity/threat score on a scaffold or inappropriate non-alert result;
- a result whose taxonomy/version/governance snapshot is missing;
- mutation of an existing result.

Correlation is disabled by default. When later enabled, it reads immutable result references and writes a new `CorrelationFinding`; it never overwrites source results.

---

## 9. Persistence and APIs

Use a single application-owned SQLite writer in WAL mode. The SQLite runtime version must be pinned, contain the upstream WAL-reset fix, pass WAL/concurrent-reader tests, and be recorded in each run/benchmark manifest.

Minimum tables:

```text
runs, source_manifests, governance_snapshots, plugin_manifests,
network_observation_index (optional/reference-only), control_events,
quality_gaps, lane_health_history, results, evidence_items,
result_links, metric_snapshots, schema_migrations
```

Do not persist all packet payloads by default. Persist source hashes and source positions sufficient to trace stored evidence to the source artifact.

REST resources:

```text
GET /runs, /sources, /results, /results/{id}, /quality,
GET /plugins, /performance, /correlations, /metrics
WS  /live
```

`/live` sends IDs and bounded summaries only. Durable REST/SQLite cursor queries are the source of truth after reconnect. API DTOs must expose status axes separately and never render a missing confidence as a numeric score.

---

## 10. Metrics and lifecycle

Expose bounded-cardinality metrics for input/routed/admitted/processed/dropped rates; queue depth/capacity/oldest age/full events; p50/p95/p99 queue and plugin timings; persistence time; state count/bytes/evictions; CPU/RSS/event-loop lag; active quality gaps; and control/lane health transitions.

Metric labels may include bounded source class, observation type, plugin ID, analytic family/lane, and outcome. They must not include flow ID, IP address, domain, entity key, raw source position, or result ID.

Record these distinct timing definitions:

```text
structural_time_to_signal = causal availability of final required evidence
                            - event time of first relevant evidence
processing_latency        = monotonic result commit - monotonic ingest
replay_wall_clock_latency = reported separately with replay pacing
live_end_to_end_latency   = only when source clock quality supports it
```

---

## 11. Required invariants and acceptance tests

| ID | Acceptance criterion |
|---|---|
| IC-01 | A control event cannot enter the normal relevance router. |
| IC-02 | One immutable network observation can be delivered to zero, one, or several lanes without copying/mutating its payload. |
| IC-03 | A relevant but inadmissible observation produces a typed admission reason, never a benign outcome. |
| IC-04 | A terminal flow's causal availability cannot precede its export/final time. |
| IC-05 | A fixed state key always reaches the same lane shard in one run; two different shards can make progress concurrently. |
| IC-06 | Queue saturation creates visible gap/health evidence and invokes declared `GapAction`. |
| IC-07 | Restart creates a new run/state epoch unless a later approved recovery contract exists. |
| IC-08 | A scaffold cannot persist `ThreatAlert`, confidence, severity, or a threat score. |
| IC-09 | Governance status/blockers are loaded read-only from a versioned snapshot; plugin code cannot change them. |
| IC-10 | `AnalyticUnavailable`, `PrerequisiteMissing`, `QualityDegraded`, and `ReviewFinding` never imply no threat or benign. |
| IC-11 | Result rows are append-only; correlation writes linked new records only. |
| IC-12 | A slow WebSocket client cannot block the analytic path and can recover via durable cursor query. |
| IC-13 | SQLite version/fix gate and concurrent-reader/WAL test pass before the database is accepted for the MVP. |
| IC-14 | Metrics expose only bounded labels and omit entity identifiers. |
| IC-15 | Canonicalization is pure and returns observations plus control events without side effects. |
| IC-16 | Ingest admission does not reject WARMING_UP, INSUFFICIENT_HISTORY, or STATE_EVICTED. |
| IC-17 | Governance owns allowed_result_types; result permissions are never inferred from status names. |
| IC-18 | Result plus mandatory evidence/provenance/link rows are atomic and idempotent in SQLite. |

---

## 12. Explicitly deferred

Do not implement or freeze: per-threat features, thresholds, windows, state keys, models, labels, confidence/severity meanings, multi-lane threat scoring, blockchain/Merkle mechanisms, Kafka/Flink/Akka, distributed state, external plugin loading, fixed queue capacities/shard count, persistent analytic-state recovery, payload decryption, or automatic response/mitigation.

The next artifacts after this contract are `TEST_PLAN` and `BENCHMARK_PLAN`. No sustained-rate, latency, or detection-quality claim is authorized until those plans and their measurements are accepted.
