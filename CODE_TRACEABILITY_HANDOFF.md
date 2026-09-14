# Code Traceability Handoff

This document traces the system-level decisions (`DEC-SYS-*`) and implementation constraints (`IC-*`) to their concrete instantiations within the EvidenceGate MVP codebase.

## Implementation Constraints (IC-01 to IC-18)

| ID | Description | Source Enforcement | Test Validation |
|---|---|---|---|
| **IC-01** | Control event bypass router | `evidencegate/routing/router.py` (type signature) | `tests/test_ic_invariants.py::test_ic_01_router_typing` |
| **IC-02** | Zero-to-many routing | `evidencegate/routing/router.py:RelevanceRouter.route()` | `test_ic_02_routing_zero_to_many` |
| **IC-03** | Typed admission rejection | `evidencegate/admission/evaluator.py:AdmissionEvaluator.evaluate()` | `test_ic_03_admission_unavailable` |
| **IC-04** | Flow causal availability limits | `evidencegate/ingest/canonicalizer.py:FlowCanonicalizer` | `test_ic_04_causal_availability` |
| **IC-05** | Deterministic sharding | `evidencegate/runtime/shard.py:compute_shard()` | `test_ic_05_deterministic_sharding` |
| **IC-06** | Saturation drop/QualityGap | `evidencegate/runtime/supervisor.py:ingest_observation()` | `test_ic_06_queue_saturation` |
| **IC-07** | Memory boundaries reset state | `evidencegate/runtime/state.py:StateStore` | `test_ic_07_restart_epoch` |
| **IC-08** | Scaffold result limitations | `evidencegate/results/validator.py:ResultValidator.validate()` | `test_ic_08_scaffold_no_threat_alert` |
| **IC-09** | Read-only governance snapshots | `evidencegate/domain/governance.py:LaneGovernance` (frozen dataclass) | `test_ic_09_governance_readonly` |
| **IC-10** | Unavailable payloads lack threat confidence | `evidencegate/results/types.py:AnalyticUnavailable` | `test_ic_10_unavailable_implications` |
| **IC-11** | SQLite Idempotence | `evidencegate/persistence/sqlite.py` (`INSERT OR IGNORE`) | `test_ic_11_sqlite_idempotence` |
| **IC-12** | WebSocket slow client drops | `evidencegate/api/app.py:live_updates` (bounded `put_nowait` queue) | `test_ic_12_slow_websocket` |
| **IC-13** | SQLite WAL mode | `evidencegate/persistence/sqlite.py` (`PRAGMA journal_mode=WAL`) | `test_ic_13_sqlite_wal` |
| **IC-14** | Bounded Metrics | `evidencegate/metrics/registry.py` | `test_ic_14_bounded_metrics` |
| **IC-15 to 18** | Pure Canonicalization, Ingest States, Governance Roles, Atomic DB Writes | `evidencegate/ingest/canonicalizer.py`, `evidencegate/admission/evaluator.py`, `evidencegate/results/validator.py`, `evidencegate/persistence/sqlite.py` | **PASS** |

## Research Decisions (DEC-SYS)
*(Note: Decision IDs map to architectural foundations established throughout the Python namespace).*

- **DEC-SYS-01 to 05 (Domain Modeling):** Implemented in `evidencegate/domain/payloads.py` using strictly typed, frozen Pydantic models.
- **DEC-SYS-06 to 10 (Ingest & Routing):** Realized in `evidencegate/ingest/canonicalizer.py` and `evidencegate/routing/router.py`. No dynamic plugin loading is permitted.
- **DEC-SYS-11 to 16 (State & Concurrency):** Sharded concurrency executed in `evidencegate/runtime/shard.py`. Memory/RSS tracking profiled in `scripts/benchmark.py`.
- **DEC-SYS-17 to 22 (Analytics & Validation):** Reflected in `evidencegate/registry/plugin.py` and strictly enforced by `evidencegate/results/validator.py`.
- **DEC-SYS-23 to 27 (Data persistence & APIs):** Implemented cleanly in `evidencegate/persistence/sqlite.py` and `evidencegate/api/app.py`.
