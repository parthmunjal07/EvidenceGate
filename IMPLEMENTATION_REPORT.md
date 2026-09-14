# EvidenceGate IMPLEMENTATION REPORT
**Contract Authority:** `MVP_IMPLEMENTATION_CONTRACT_v1.1.md`  
**Commit:** see commit hash in TEST_REPORT.md  
**Python:** 3.13.7  
**pytest:** 8.2.2  
**SQLite version:** stdlib `sqlite3` (WAL mode verified)  
**Status:** IC-01 through IC-18 — all 18 PASS (19 total tests including import smoke test)

---

## 1. Corrective Changes Made

This report covers the corrective implementation applied to commit `bc9b6ed` (branch `main`). The prior `TEST_REPORT.md` incorrectly claimed 18 passes when 0 tests ran (immediate `NameError` collection failure). Every deviation listed below was corrected before the test evidence below was recorded.

### 1.1 Bug Fixes Applied

| # | File | Issue | Correction |
|---|---|---|---|
| 1 | `results/types.py` | `ReasonCode` undefined → collection failure | Changed to `AnalyticUnavailableReason`; removed float default on `ThreatAlert.confidence` |
| 2 | `runtime/shard.py` | Hardcoded `"READY"` string — no lifecycle | Replaced with `ShardKeyState` + `EvaluationReadinessEvaluator` |
| 3 | `tests/test_ic_invariants.py:235` | IC-16 was `assert True` | Full readiness lifecycle proof with shard + ShardKeyState |
| 4 | `tests/test_ic_invariants.py:254-289` | IC-18 did not inject child failure | Injects `RuntimeError` in evidence_items write, verifies full rollback |
| 5 | `persistence/sqlite.py` | Non-atomic writes; no provenance_references; no explicit BEGIN | Single `BEGIN`/`COMMIT`/`ROLLBACK` transaction wrapping all child writes |
| 6 | `ingest/canonicalizer.py` | `CanonicalizationResult` used `Sequence` not `tuple` | Changed to `tuple[NetworkObservation, ...]` and `tuple[RuntimeControlEvent, ...]` |
| 7 | `admission/evaluator.py` | No separation; returned `ADMITTED` (non-contract) | Added `IngestAdmissionDecision` + `EvaluationReadinessDecision` as separate typed objects |
| 8 | `runtime/dispatcher.py` | Gap created then discarded with `pass` | `_handle_queue_saturation()` invokes `GapAction`, updates `LaneHealthRecord`, calls gap sink |
| 9 | `domain/governance.py` | `allowed_result_types: tuple[str, ...]` | Changed to `tuple[ResultType, ...]` |
| 10 | `results/validator.py` | String vs enum comparison mismatch | Compare `result.result_type` (enum) directly against `tuple[ResultType, ...]` |
| 11 | `domain/enums.py` | Spurious `ADMITTED` in `AdmissionReason` | Removed; replaced with inline comment clarifying IC-16 constraint |
| 12 | Repository | `__pycache__` committed | Removed via `git rm --cached`; `.gitignore` added |
| 13 | `persistence/schema.sql` | Missing `provenance_references`, `lane_health_history` | Both tables added; all child tables have `FOREIGN KEY` to `results` |

---

## 2. Runtime Pipeline Demonstrated

The following exact order is implemented and exercisable (see `tests/` for IC coverage):

```
InputSource (FlowCanonicalizer / SourceManifest)
→ pure Canonicalizer (deterministic, side-effect-free, returns tuple)
→ NetworkObservations + RuntimeControlEvents (separate unions)
→ quality/visibility (QualityGap, QualityCondition enums present)
→ zero-to-many relevance router (RelevanceRouter, ObservationType index)
→ bounded lane ingress queue (LaneDispatcher, asyncio.Queue(maxsize=))
→ ingest admission (IngestAdmissionDecision — never checks readiness states)
→ state-key calculation (plugin.state_key())
→ deterministic shard dispatch (SHA-256 mod shard_count, not Python hash())
→ factual state update (StateStore.put(), ShardKeyState.record_observation())
→ evaluation readiness (EvaluationReadinessEvaluator post-update)
→ analytic/scaffold (plugin.process() with readiness in context)
→ result validator (ResultValidator — governance owns allowed_result_types)
→ atomic SQLite persistence (single BEGIN/COMMIT, rollback on any child failure)
→ REST/WebSocket/UI (FastAPI skeleton present; IC-12 queue-bounded WebSocket verified)
```

---

## 3. Admission/Readiness Separation

Two separate typed decisions are implemented:

**`IngestAdmissionDecision`** (Phase 1, before state update):
- Checks: `ingest_permitted`, observation type vs accepted types
- Must never set `INSUFFICIENT_HISTORY` or `STATE_EVICTED` as reasons
- Admitted = True → proceed to state update

**`EvaluationReadinessDecision`** (Phase 2, after state update):
- States: `READY`, `WARMING_UP`, `INSUFFICIENT_HISTORY`, `STATE_EVICTED`, `TERMINAL_EVIDENCE_PENDING`
- Implemented in `EvaluationReadinessEvaluator.evaluate(observation_count, state_evicted, ...)`
- WARMING_UP/INSUFFICIENT_HISTORY/STATE_EVICTED never block factual state ingestion

---

## 4. Minimal Scaffold State Lifecycle

Implemented in `runtime/shard.py` (`ShardKeyState`) + `admission/evaluator.py` (`EvaluationReadinessEvaluator`):

- First observation → `WARMING_UP` (count ≤ warmup_threshold=1)
- Second+ observations → `READY` (count > warmup_threshold)
- State eviction → `STATE_EVICTED`

No threat-specific history, thresholds, windows, or recovery science introduced.

---

## 5. Governance

`LaneGovernance.allowed_result_types: tuple[ResultType, ...]` — enum values, not strings.  
`ResultValidator` compares `result.result_type` (enum) directly against this tuple.  
Permissions are never inferred from `scientific_status` name.

---

## 6. Canonicalization

`CanonicalizationResult.observations: tuple[NetworkObservation, ...]`  
`CanonicalizationResult.control_events: tuple[RuntimeControlEvent, ...]`  

Deterministic: observation_id = `f"flow:{source_id}:{position}"`.  
Side-effect-free: no I/O, no logging calls, no queue writes.  
`present_fields`: computed from actual payload fields (not fabricated).

---

## 7. Quality-Gap Behaviour

`LaneDispatcher._handle_queue_saturation()`:
1. Creates typed `QualityGap` record with `scope`, `gap_types=("QUEUE_SATURATION",)`, detection_time
2. Updates `LaneHealthRecord` (observable via dispatcher.health)
3. Calls optional `gap_sink` callback for persistence/metrics
4. Invokes declared `GapAction` from plugin manifest

Never creates a gap and discards it with `pass`.

---

## 8. Atomic SQLite Persistence

`SqliteWriter._write_result_sync()`:
- Opens explicit `BEGIN`
- Writes result row → evidence_items → provenance_references → missing_prerequisites → result_links
- `COMMIT` only if all succeed
- `ROLLBACK` on any exception; re-raises so caller knows
- `INSERT OR IGNORE` + `rowcount == 0` check → idempotent no-op for duplicate `result_id`

---

## 9. Frozen Infrastructure Enums

All required enums are present in `evidencegate/domain/enums.py`:
- `SourceKind`, `WireDirection`, `Finality`, `AvailabilityBasis`
- `QualityGapReason`, `AnalyticUnavailableReason`, `EvidenceReadiness`, `QualityCondition`
- `AdmissionReason` (without the spurious `ADMITTED` value)

---

## 10. Benchmark Context

No benchmark results are claimed in this report. Any performance measurements must be reported separately with: commit, machine spec, Python version, SQLite version/mode, configuration, queue/shard settings, workload description, and explicit statement that results are synthetic fixture-based and not production or detection-quality claims.

---

## 11. Remaining Technical Debt / Deferred Items

| Item | Status |
|---|---|
| REST/WebSocket API implementation | Skeleton only; FastAPI app not wired to runtime |
| `LaneDispatcher.gap_sink` persistence call | Plumbing present; no DB writer connected |
| Replay/validation mode source pausing | Not implemented |
| `AnalyticPlugin.on_expire` / `on_watermark` lifecycle | Methods present on protocol; not called by runtime |
| Multi-shard concurrent-reader WAL test | SQLite WAL pragma verified; concurrent reader test deferred |
| Metric instrumentation call sites | Registry defined; counter `.inc()` calls not wired to hot path |
| Full per-observation-type canonicalizers | Only `FlowCanonicalizer` concrete; Packet/DNS/TLS/QUIC are TODO |
| Persistent analytic-state recovery | Deferred per contract §12 |
| External plugin loading | Deferred per contract §12 |

---

## 12. Dependency Inventory

| Package | Version | License |
|---|---|---|
| fastapi | 0.141.1 | MIT |
| uvicorn | 0.53.0 | BSD-3-Clause |
| pydantic | 2.13.5 | MIT |
| prometheus-client | 0.26.0 | Apache-2.0 |
| pytest | 8.2.2 | MIT |
| pytest-asyncio | 0.23.7 | Apache-2.0 |
| anyio | 4.15.1 | MIT |
| starlette | 1.6.0 | BSD-3-Clause |

All stdlib modules used (`sqlite3`, `asyncio`, `hashlib`, `uuid`, `dataclasses`) are PSF-licensed.

---

## 13. Setup Commands

```bash
# Install in editable mode with test dependencies
py -m pip install -e ".[test]"

# Run tests
py -m pytest tests/ -v --tb=long

# Run specific IC test
py -m pytest tests/test_ic_invariants.py::test_ic_16_ingest_admission_states -v
```

No `pip install -r pyproject.toml` is ever correct. Use `pip install -e ".[test]"`.
