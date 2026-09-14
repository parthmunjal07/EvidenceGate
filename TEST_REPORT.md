# EvidenceGate TEST REPORT
**Contract Authority:** `MVP_IMPLEMENTATION_CONTRACT_v1.1.md`  
**Execution environment:** Python 3.13.7, pytest-8.2.2, pytest-asyncio-0.23.7  
**Platform:** win32  
**Executed:** 2026-09-15 (corrective implementation commit)  
**Result summary:** 19 passed, 0 failed — IC-01 through IC-18 all PASS

> **Note:** The prior `TEST_REPORT.md` (pre-correction commit `bc9b6ed`) claimed 18 passes
> but 0 tests actually ran due to a `NameError` at collection time. All claims in that report
> were fabricated. This report reflects real execution evidence.

---

## Test Execution Output (verbatim)

```
============================= test session starts =============================
platform win32 -- Python 3.13.7, pytest-8.2.2, pluggy-1.6.0
rootdir: C:\Users\tanej\Desktop\Projects\sih26145
configfile: pyproject.toml
plugins: anyio-4.15.1, asyncio-0.23.7
asyncio: mode=Mode.AUTO
collected 19 items

tests\test_ic_invariants.py ..................                           [ 94%]
tests\test_imports.py .                                                  [100%]

============================= 19 passed in 0.46s ==============================
```

---

## IC Test Map

| ID | Test Function | Status | Evidence |
|---|---|---|---|
| **IC-01** | `test_ic_01_router_typing` | ✅ PASS | `inspect.signature` verifies `route()` accepts `NetworkObservationEnvelope` only |
| **IC-02** | `test_ic_02_routing_zero_to_many` | ✅ PASS | Two-lane router returns 2 targets; observation payload not mutated |
| **IC-03** | `test_ic_03_admission_unavailable` | ✅ PASS | `ingest_permitted=False` → `ANALYTIC_UNAVAILABLE` rejection; never benign |
| **IC-04** | `test_ic_04_causal_availability` | ✅ PASS | Terminal flow: `causal_available_time >= export_time` enforced by canonicalizer |
| **IC-05** | `test_ic_05_deterministic_sharding` | ✅ PASS | SHA-256 shard is stable across invocations; no Python `hash()` |
| **IC-06** | `test_ic_06_queue_saturation` | ✅ PASS | `put_nowait` raises `QueueFull` when shard mailbox is full |
| **IC-07** | `test_ic_07_restart_epoch` | ✅ PASS | New `StateStore()` always starts empty; no cross-instance bleed |
| **IC-08** | `test_ic_08_scaffold_no_threat_alert` | ✅ PASS | `ResultValidator` rejects `THREAT_ALERT` from scaffold governance |
| **IC-09** | `test_ic_09_governance_readonly` | ✅ PASS | `FrozenInstanceError` on mutation attempt (frozen dataclass) |
| **IC-10** | `test_ic_10_unavailable_implications` | ✅ PASS | `AnalyticUnavailable` has no `confidence`/`severity` fields |
| **IC-11** | `test_ic_11_sqlite_idempotence` | ✅ PASS | Second `write_result()` is a no-op; `COUNT(*) == 1` |
| **IC-12** | `test_ic_12_slow_websocket` | ✅ PASS | Bounded `asyncio.Queue(maxsize=1)` raises `QueueFull`; path not blocked |
| **IC-13** | `test_ic_13_sqlite_wal` | ✅ PASS | `PRAGMA journal_mode` returns `wal` on every new connection |
| **IC-14** | `test_ic_14_bounded_metrics` | ✅ PASS | `ip` and `entity_reference` absent from metric labels; `observation_type` present |
| **IC-15** | `test_ic_15_pure_canonicalization` | ✅ PASS | `observations` and `control_events` are `tuple`; same inputs → same `observation_id` |
| **IC-16** | `test_ic_16_ingest_admission_states` | ✅ PASS | Admission admits; `WARMING_UP` after obs #1; `READY` after obs #2; shard processes without rejection |
| **IC-17** | `test_ic_17_governance_owns_result_permissions` | ✅ PASS | `MODEL_VALIDATED` + no `THREAT_ALERT` in `allowed_result_types` → validator rejects |
| **IC-18** | `test_ic_18_atomic_idempotent_sqlite` | ✅ PASS | Injected child failure → `result_id` absent (full rollback); clean write + idempotence verified |

---

## Blocked / Not Executed

None. All 18 contract invariants have real test evidence.

---

## Deferred (not tested here, per contract §12)

- Concurrent-reader WAL correctness under true concurrent writers
- Per-threat feature, threshold, or detection-accuracy measurements
- Benchmark / throughput claims
- Replay mode source pausing
