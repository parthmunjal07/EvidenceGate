# EvidenceGate Code Traceability Handoff
**Contract Authority:** `MVP_IMPLEMENTATION_CONTRACT_v1.1.md` (de-authorized: none; v1 pre-dates this handoff)  
**Updated:** Corrective implementation commit (2026-09-15)

---

## Implementation Constraints — IC-01 through IC-18

| ID | Description | Source Enforcement | Test Validation |
|---|---|---|---|
| **IC-01** | Control event cannot enter router | [`routing/router.py`](evidencegate/routing/router.py): `route(observation: NetworkObservationEnvelope)` type annotation | `test_ic_01_router_typing` |
| **IC-02** | Zero-to-many routing | [`routing/router.py:RelevanceRouter.route()`](evidencegate/routing/router.py) | `test_ic_02_routing_zero_to_many` |
| **IC-03** | Typed admission rejection; never benign | [`admission/evaluator.py:AdmissionEvaluator.evaluate()`](evidencegate/admission/evaluator.py) → `IngestAdmissionDecision` | `test_ic_03_admission_unavailable` |
| **IC-04** | Terminal flow causal availability | [`ingest/canonicalizer.py:FlowCanonicalizer`](evidencegate/ingest/canonicalizer.py): `causal_time = max(record.timestamp, flow_obs.export_time)` | `test_ic_04_causal_availability` |
| **IC-05** | Deterministic shard (SHA-256, not Python hash) | [`runtime/shard.py:compute_shard()`](evidencegate/runtime/shard.py) | `test_ic_05_deterministic_sharding` |
| **IC-06** | Queue saturation → typed gap + GapAction | [`runtime/dispatcher.py:LaneDispatcher._handle_queue_saturation()`](evidencegate/runtime/dispatcher.py) | `test_ic_06_queue_saturation` |
| **IC-07** | Restart creates new state epoch | [`runtime/state.py:StateStore`](evidencegate/runtime/state.py): fresh `__init__` dict | `test_ic_07_restart_epoch` |
| **IC-08** | Scaffold cannot persist ThreatAlert | [`results/validator.py:ResultValidator.validate()`](evidencegate/results/validator.py) | `test_ic_08_scaffold_no_threat_alert` |
| **IC-09** | Governance is read-only | [`domain/governance.py:LaneGovernance`](evidencegate/domain/governance.py): `@dataclass(frozen=True, slots=True)` | `test_ic_09_governance_readonly` |
| **IC-10** | Unavailable results lack confidence/severity | [`results/types.py:AnalyticUnavailable`](evidencegate/results/types.py): no confidence field | `test_ic_10_unavailable_implications` |
| **IC-11** | Result rows append-only | [`persistence/sqlite.py`](evidencegate/persistence/sqlite.py): `INSERT OR IGNORE` + `rowcount==0` guard | `test_ic_11_sqlite_idempotence` |
| **IC-12** | Slow WS client cannot block analytic path | Bounded `asyncio.Queue(maxsize=)` pattern | `test_ic_12_slow_websocket` |
| **IC-13** | SQLite WAL mode | [`persistence/sqlite.py`](evidencegate/persistence/sqlite.py): `PRAGMA journal_mode=WAL` on connect | `test_ic_13_sqlite_wal` |
| **IC-14** | Bounded metric labels | [`metrics/registry.py:MetricsRegistry`](evidencegate/metrics/registry.py) | `test_ic_14_bounded_metrics` |
| **IC-15** | Pure canonicalization (tuple, deterministic, no side effects) | [`ingest/canonicalizer.py:CanonicalizationResult`](evidencegate/ingest/canonicalizer.py): `observations: tuple[NetworkObservation, ...]`, `control_events: tuple[RuntimeControlEvent, ...]` | `test_ic_15_pure_canonicalization` |
| **IC-16** | Ingest admission does not reject WARMING_UP / INSUFFICIENT_HISTORY / STATE_EVICTED | [`admission/evaluator.py:IngestAdmissionDecision`](evidencegate/admission/evaluator.py) (Phase 1) vs [`EvaluationReadinessDecision`](evidencegate/admission/evaluator.py) (Phase 2, post-update) | `test_ic_16_ingest_admission_states` |
| **IC-17** | Governance owns `allowed_result_types`; permissions not inferred from status names | [`domain/governance.py:LaneGovernance.allowed_result_types: tuple[ResultType, ...]`](evidencegate/domain/governance.py); [`results/validator.py`](evidencegate/results/validator.py) checks enum directly | `test_ic_17_governance_owns_result_permissions` |
| **IC-18** | Result + evidence/provenance/links atomic; idempotent | [`persistence/sqlite.py:SqliteWriter._write_result_sync()`](evidencegate/persistence/sqlite.py): single `BEGIN`/`COMMIT`/`ROLLBACK` | `test_ic_18_atomic_idempotent_sqlite` |
| **N/A** | Enforces missing required fields | [`admission/evaluator.py`](evidencegate/admission/evaluator.py): Checks `required_fields` against `present_fields` | `test_missing_required_fields` |
| **N/A** | Enforces visibility/quality | [`admission/evaluator.py`](evidencegate/admission/evaluator.py): Checks `minimum_visibility` | `test_insufficient_visibility` |
| **N/A** | Enforces finality | [`admission/evaluator.py`](evidencegate/admission/evaluator.py): Checks `allowed_finality` | `test_unsupported_finality` |
| **N/A** | Dispatcher exception observable | [`runtime/dispatcher.py`](evidencegate/runtime/dispatcher.py): Increment metric, emit ERROR control event | `test_unexpected_dispatcher_exception` |

---

## Key Architectural Decision Traceability

### Domain (contract §3)
- [`domain/enums.py`](evidencegate/domain/enums.py): All frozen infrastructure enums: `SourceKind`, `WireDirection`, `Finality`, `AvailabilityBasis`, `QualityGapReason`, `EvidenceReadiness`, `QualityCondition`, `AdmissionReason` (without `ADMITTED`)
- [`domain/payloads.py`](evidencegate/domain/payloads.py): `PacketObservation`, `FlowObservation`, `DNSObservation`, `TLSObservation`, `QUICObservation` — all frozen dataclasses
- [`domain/events.py`](evidencegate/domain/events.py): Separate `NetworkObservationEnvelope` and `RuntimeControlEvent` unions

### Ingest (contract §4)
- [`ingest/source.py`](evidencegate/ingest/source.py): `InputSource` protocol, `RawSourceRecord`, `SourceManifest`
- [`ingest/canonicalizer.py`](evidencegate/ingest/canonicalizer.py): `CanonicalizationResult` with typed tuples; `FlowCanonicalizer` concrete implementation

### Governance (contract §5)
- [`domain/governance.py`](evidencegate/domain/governance.py): `LaneGovernance` frozen, `allowed_result_types: tuple[ResultType, ...]`, `ingest_permitted: bool`

### Registry + Routing (contract §6)
- [`registry/plugin.py`](evidencegate/registry/plugin.py): `AnalyticPlugin` protocol with `route()`, `state_key()`, `process()`, `on_quality_gap()`, etc.
- [`registry/manifest.py`](evidencegate/registry/manifest.py): `PluginManifest` with `gap_action`, `allowed_result_types`, `integration_status`
- [`routing/router.py`](evidencegate/routing/router.py): `RelevanceRouter` compiles `ObservationType → candidate lanes` index at registration

### Admission (contract §6.3 + IC-16)
- [`admission/evaluator.py`](evidencegate/admission/evaluator.py):
  - `IngestAdmissionDecision` — Phase 1, before state update
  - `EvaluationReadinessDecision` — Phase 2, after state update
  - `AdmissionEvaluator.evaluate()` — Phase 1 only
  - `EvaluationReadinessEvaluator.evaluate()` — Phase 2 only

### Runtime (contract §7)
- [`runtime/shard.py`](evidencegate/runtime/shard.py): `LaneShard` with `ShardKeyState` readiness tracking; `compute_shard()` using SHA-256
- [`runtime/dispatcher.py`](evidencegate/runtime/dispatcher.py): `LaneDispatcher` with `LaneHealthRecord`; `_handle_queue_saturation()` wires GapAction
- [`runtime/state.py`](evidencegate/runtime/state.py): `StateStore` — epoch-isolated

### Results (contract §8)
- [`results/types.py`](evidencegate/results/types.py): Full result union; `ThreatAlert.confidence: str | None` (no float default); `ResultDraft.reason_code: AnalyticUnavailableReason | None`
- [`results/validator.py`](evidencegate/results/validator.py): Enum-vs-enum comparison; IC-08, IC-17 enforcement

### Persistence (contract §9 + IC-18)
- [`persistence/schema.sql`](evidencegate/persistence/schema.sql): `results`, `evidence_items`, `provenance_references`, `missing_prerequisites`, `result_links`, `quality_gaps`, `lane_health_history`, `control_events`, `metric_snapshots`
- [`persistence/sqlite.py`](evidencegate/persistence/sqlite.py): Single `BEGIN`/`COMMIT`/`ROLLBACK` transaction; WAL mode; idempotent `INSERT OR IGNORE`

### Metrics (contract §10)
- [`metrics/registry.py`](evidencegate/metrics/registry.py): Bounded labels only (`observation_type`, `lane`, `plugin_id`, `status`)

---

## Correction History

| Prior commit `bc9b6ed` deviation | Corrected in |
|---|---|
| `ReasonCode` undefined → collection failure | `results/types.py` |
| `"READY"` hardcoded string | `runtime/shard.py` |
| `assert True` for IC-16 | `tests/test_ic_invariants.py` |
| IC-18 didn't inject failure | `tests/test_ic_invariants.py` |
| Gap discarded with `pass` | `runtime/dispatcher.py` |
| `allowed_result_types: tuple[str, ...]` | `domain/governance.py` |
| `ADMITTED` in `AdmissionReason` | `domain/enums.py` |
| No `IngestAdmissionDecision`/`EvaluationReadinessDecision` split | `admission/evaluator.py` |
| `CanonicalizationResult` used `Sequence` | `ingest/canonicalizer.py` |
| String vs enum comparison in validator | `results/validator.py` |
| No `provenance_references` table | `persistence/schema.sql` |
| Non-atomic evidence/result writes | `persistence/sqlite.py` |
| `__pycache__` committed to git | `git rm --cached` + `.gitignore` |
