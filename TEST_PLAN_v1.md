# EvidenceGate TEST PLAN v1

This document outlines the test strategy and mapping for verification of the IC (Implementation Contract) invariants (IC-01 through IC-14). 

## 1. Test Methodology
- **Framework**: `pytest` and `pytest-asyncio`.
- **Fixtures**: Deterministic static fixtures (e.g., synthetically generated `PacketObservation` and `FlowObservation` models).
- **Isolation**: Unit tests verify behavior at boundaries (e.g., canonicalization, validation, routing).
- **State**: Bounded queue interactions simulate edge cases like queue saturation.
- **Constraints**: 
  - No generated threat labels or unapproved features are used.
  - Tests do not measure production performance (reserved for the Benchmark Plan).

## 2. Invariant Mapping

| ID | Description | Test Strategy (Location: `test_ic_invariants.py`) |
|---|---|---|
| **IC-01** | Control event cannot enter router | `test_ic_01_router_typing`: Validate function signature restrictions. |
| **IC-02** | Zero-to-many observation routing | `test_ic_02_routing_zero_to_many`: Configure router with multiple targets for same observation type. |
| **IC-03** | Relevant but inadmissible creates typed reason | `test_ic_03_admission_unavailable`: Provide `ANALYTIC_UNAVAILABLE` governance and assert proper `AdmissionDecision`. |
| **IC-04** | Terminal flow causal availability | `test_ic_04_causal_availability`: Use `FlowCanonicalizer` to assert `causal_available_time >= export_time`. |
| **IC-05** | Deterministic state key sharding | `test_ic_05_deterministic_sharding`: Test `compute_shard` yields same modulo integer for same inputs, different for variants. |
| **IC-06** | Queue saturation creates QualityGap | `test_ic_06_queue_saturation`: Overfill a small `LaneShard` queue with `put_nowait` and verify `asyncio.QueueFull` exception behavior. |
| **IC-07** | Restart creates new run epoch | `test_ic_07_restart_epoch`: Verify fresh `StateStore` objects are isolated. |
| **IC-08** | Scaffold cannot persist ThreatAlert | `test_ic_08_scaffold_no_threat_alert`: Assert `ResultValidator` raises error when scaffold governance tries to emit `ThreatAlert`. |
| **IC-09** | Read-only governance | `test_ic_09_governance_readonly`: Verify `LaneGovernance` is frozen (via Python `@dataclass(frozen=True)` property test). |
| **IC-10** | Unavailable results never imply benign | `test_ic_10_unavailable_implications`: Verify `AnalyticUnavailable` models lack benign status or threat score semantics. |
| **IC-11** | Result rows append-only | `test_ic_11_sqlite_idempotence`: Ensure `SqliteWriter` handles duplicate result_id inserts securely using `INSERT OR IGNORE`. |
| **IC-12** | Slow WS client cannot block | `test_ic_12_slow_websocket`: Instantiate a client queue of size 1, send 2 messages, verify `asyncio.QueueFull` is gracefully bypassed. |
| **IC-13** | SQLite WAL mode | `test_ic_13_sqlite_wal`: Inspect database PRAGMA configuration directly after connecting. |
| **IC-14** | Metrics expose bounded labels | `test_ic_14_bounded_metrics`: Verify label names on Prometheus primitives do not contain `ip`, `entity_reference`, or unbounded values. |

## 3. Explicit Limitations
- **IC-15 to IC-18**: Have been fully implemented as pure canonicalization, correct ingest states, governance roles, and atomic database writes.
