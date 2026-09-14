# EvidenceGate TEST PLAN v1.1
**Contract Authority:** `MVP_IMPLEMENTATION_CONTRACT_v1.1.md`  
**Updated:** Corrective implementation commit (2026-09-15)

---

## 1. Test Methodology

- **Framework:** `pytest` (8.2.2) and `pytest-asyncio` (0.23.7)  
- **Fixtures:** Deterministic static fixtures (synthetically generated `PacketObservation`, `FlowObservation`, frozen `LaneGovernance`) using UTC-aware timestamps  
- **Isolation:** Unit tests verify behavior at boundaries (canonicalization, validation, routing, persistence, readiness lifecycle)  
- **Asynchronous tests:** `@pytest.mark.asyncio` with `asyncio_mode=auto`  
- **Constraints:**  
  - No generated threat labels or unapproved features  
  - Tests do not measure production performance (reserved for Benchmark Plan)  
  - IC-16 must prove state updates, not assert True  
  - IC-18 must inject a mandatory child-write failure and verify rollback

---

## 2. Invariant Mapping — IC-01 through IC-18

| ID | Description | Test Function | Strategy |
|---|---|---|---|
| **IC-01** | Control event cannot enter router | `test_ic_01_router_typing` | `inspect.signature` verifies `route()` annotation is `NetworkObservationEnvelope` |
| **IC-02** | Zero-to-many routing | `test_ic_02_routing_zero_to_many` | Two-lane router with same plugin; assert 2 distinct targets returned |
| **IC-03** | Inadmissible → typed reason, never benign | `test_ic_03_admission_unavailable` | `ingest_permitted=False` → `ANALYTIC_UNAVAILABLE` in `IngestAdmissionDecision.reasons` |
| **IC-04** | Terminal flow causal availability | `test_ic_04_causal_availability` | `FlowCanonicalizer` asserts `causal_available_time >= export_time` |
| **IC-05** | Deterministic shard | `test_ic_05_deterministic_sharding` | SHA-256 `compute_shard()` stable across calls; no Python `hash()` |
| **IC-06** | Queue saturation | `test_ic_06_queue_saturation` | `put_nowait` raises `QueueFull` on `max_size=1` shard |
| **IC-07** | Restart epoch | `test_ic_07_restart_epoch` | Two `StateStore()` instances are independent |
| **IC-08** | Scaffold no ThreatAlert | `test_ic_08_scaffold_no_threat_alert` | `ResultValidator` raises `ValueError` for `THREAT_ALERT` not in `allowed_result_types` |
| **IC-09** | Governance read-only | `test_ic_09_governance_readonly` | `FrozenInstanceError` on mutation of frozen dataclass |
| **IC-10** | Unavailable no confidence/severity | `test_ic_10_unavailable_implications` | `getattr(res, "confidence", None) is None` |
| **IC-11** | Result rows append-only | `test_ic_11_sqlite_idempotence` | Second `write_result()` → `rowcount==0` → no-op; `COUNT(*)==1` |
| **IC-12** | Slow WS client | `test_ic_12_slow_websocket` | `asyncio.Queue(maxsize=1)` → `QueueFull`; analytic path not blocked |
| **IC-13** | SQLite WAL | `test_ic_13_sqlite_wal` | `PRAGMA journal_mode` returns `wal` |
| **IC-14** | Bounded metric labels | `test_ic_14_bounded_metrics` | `ip` and `entity_reference` absent; `observation_type` present |
| **IC-15** | Pure canonicalization | `test_ic_15_pure_canonicalization` | Result is `tuple`, deterministic (`same obs_id`), no side effects |
| **IC-16** | Ingest admission doesn't reject readiness states | `test_ic_16_ingest_admission_states` | Admission admits; `WARMING_UP` after obs#1; `READY` after obs#2; `ShardKeyState` counts verified; shard processes without rejecting |
| **IC-17** | Governance owns result permissions | `test_ic_17_governance_owns_result_permissions` | `MODEL_VALIDATED` without `THREAT_ALERT` in `allowed_result_types` → validator rejects |
| **IC-18** | Atomic idempotent SQLite | `test_ic_18_atomic_idempotent_sqlite` | Injected child failure → result_id absent (`COUNT==0` rollback); clean write; idempotent re-write |

---

## 3. Execution Command

```bash
py -m pip install -e ".[test]"
py -m pytest tests/ -v --tb=long
```

Expected: `19 passed, 0 failed` (18 IC tests + 1 import smoke test).

---

## 4. Out of Scope (Benchmark Plan)

- Sustained-throughput measurements  
- Detection-accuracy / false-positive rates  
- Concurrent-reader WAL stress tests  
- Replay mode pacing  
- Per-threat feature validation  
