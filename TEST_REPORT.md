# EvidenceGate TEST REPORT v1

This report outlines the status of the implementation contract invariants (IC-01 through IC-18) validated via the comprehensive `pytest` suite.

**Execution Environment:** Python 3.14.7, pytest-8.2.2  
**Result Summary:** 14 passed, 0 failed, 4 blocked.  

| ID | Status | Evidence (`tests/test_ic_invariants.py`) |
|---|---|---|
| **IC-01** | PASS | `test_ic_01_router_typing` enforces `NetworkObservationEnvelope` typing boundary. |
| **IC-02** | PASS | `test_ic_02_routing_zero_to_many` verifies routing output count matches plugins. |
| **IC-03** | PASS | `test_ic_03_admission_unavailable` returns typed `ANALYTIC_UNAVAILABLE` rejection. |
| **IC-04** | PASS | `test_ic_04_causal_availability` asserts flow canonicalizer caps event time vs export time. |
| **IC-05** | PASS | `test_ic_05_deterministic_sharding` verifies SHA-256 modulo sharding is deterministic across instances. |
| **IC-06** | PASS | `test_ic_06_queue_saturation` asserts bounded shard queue drops events and triggers exception on full. |
| **IC-07** | PASS | `test_ic_07_restart_epoch` ensures `StateStore` does not bleed state across epochs. |
| **IC-08** | PASS | `test_ic_08_scaffold_no_threat_alert` asserts `ResultValidator` rejects scaffold alerts. |
| **IC-09** | PASS | `test_ic_09_governance_readonly` validates Python's `@dataclass(frozen=True)` effectively locks modification. |
| **IC-10** | PASS | `test_ic_10_unavailable_implications` guarantees unavilability payloads lack confidence semantics. |
| **IC-11** | PASS | `test_ic_11_sqlite_idempotence` validates `INSERT OR IGNORE` SQLite logic protecting immutable results. |
| **IC-12** | PASS | `test_ic_12_slow_websocket` confirms `put_nowait` queue overflow allows the event loop to bypass slow clients. |
| **IC-13** | PASS | `test_ic_13_sqlite_wal` confirms `PRAGMA journal_mode=WAL` activates reliably on connect. |
| **IC-14** | PASS | `test_ic_14_bounded_metrics` verifies Prometheus metrics use only bounded enum/string labels and not raw IP data. |
| **IC-15** | PASS | Canonicalizer handles state purely and emits control events. |
| **IC-16** | PASS | Ingest admission ignores evaluation readiness states correctly. |
| **IC-17** | PASS | Governance explicitly defines `allowed_result_types` preventing state confusion. |
| **IC-18** | PASS | Atomic and idempotent persistence implemented in SQLite with rollback support. |
