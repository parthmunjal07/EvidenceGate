# [EXPERIMENT]
# CONTROLLED MVP ENGINEERING CAPACITY CHARACTERIZATION

This is **C2-R1 CAPACITY CHARACTERIZATION** using controlled synthetic engineering load. It is not a production benchmark, scientific C2 validation, FPR test, malware-truth test, or EvidenceGate production-throughput claim.

## Scope and environment

- Captured: 2026-09-21T21:18:56.961957+00:00
- OS: Windows-11-10.0.26200-SP0
- Python: 3.13.7
- CPU: Intel64 Family 6 Model 170 Stepping 4, GenuineIntel (18 logical CPUs)
- Available memory: unavailable
- Git commit at measurement start: `4580304131f086df8f5d14e508176368dd8c9e28`
- Scientific config: minimum history `3`, retained history `32`, TTL `3600.0` seconds, basis `FLOW_START`
- Persistence: explicitly stated per run; SQLite runs use the real disk-backed schema v3 writer and persist every warm-up and ready result.

The ingress queue capacity is 2000, shard mailbox capacity is 1000, state-key capacity is the per-run `max_state_entries`, and per-key reorder capacity is the per-run `reorder_capacity`. These are four independent bounds. Scientific retained history (32) is independent of reorder capacity and does not imply a reorder limit of 32.

## Runs

| workload | keys | events/key | burst | state bound | reorder bound | state | reorder total | reorder/key | obs | results | seconds | processed obs/s | peak traced B | gaps | errors | status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| key_cardinality | 32 | 3 | 1 | 33 | 64 | 32 | 32 | 1 | 96 | 96 | 0.303955 | 315.836 | 536214 | 0 | 0 | CLEAN |
| key_cardinality | 64 | 3 | 1 | 65 | 64 | 64 | 64 | 1 | 192 | 192 | 0.592692 | 323.946 | 786422 | 0 | 0 | CLEAN |
| key_cardinality | 128 | 3 | 1 | 129 | 64 | 128 | 128 | 1 | 384 | 384 | 1.312619 | 292.545 | 1284479 | 0 | 0 | CLEAN |
| key_cardinality | 256 | 3 | 1 | 257 | 64 | 256 | 256 | 1 | 768 | 768 | 3.067049 | 250.404 | 2181200 | 0 | 0 | CLEAN |
| key_cardinality | 512 | 3 | 1 | 513 | 64 | 512 | 256 | 1 | 1536 | 1536 | 6.884684 | 223.104 | 2740702 | 0 | 0 | CLEAN |
| key_cardinality | 1024 | 3 | 1 | 1025 | 64 | 1024 | 256 | 1 | 3072 | 3072 | 13.583324 | 226.16 | 3842447 | 0 | 0 | CLEAN |
| key_cardinality | 2048 | 3 | 1 | 2049 | 64 | 2048 | 256 | 1 | 6144 | 6144 | 23.103296 | 265.936 | 6046219 | 0 | 0 | CLEAN |
| full_history | 32 | 32 | 1 | 33 | 64 | 32 | 32 | 1 | 1024 | 1024 | 5.577263 | 183.603 | 1328203 | 0 | 0 | CLEAN |
| full_history | 128 | 32 | 1 | 129 | 64 | 128 | 128 | 1 | 4096 | 4096 | 32.124196 | 127.505 | 3754107 | 0 | 0 | CLEAN |
| full_history | 512 | 32 | 1 | 513 | 64 | 512 | 256 | 1 | 16384 | 16384 | 167.753266 | 97.667 | 12228061 | 0 | 0 | CLEAN |
| full_history | 1024 | 32 | 1 | 1025 | 64 | 1024 | 256 | 1 | 32768 | 32768 | 296.801846 | 110.404 | 15953241 | 0 | 0 | CLEAN |
| same_time_burst | 1 | 2 | 1 | 8 | 1 | 1 | 1 | 1 | 2 | 2 | 0.011696 | 170.993 | 52003 | 0 | 0 | CLEAN |
| same_time_burst | 1 | 3 | 2 | 8 | 1 | 1 | 1 | 1 | 3 | 2 | 0.017299 | 115.616 | 60087 | 1 | 0 | SATURATED_REORDER |
| same_time_burst | 1 | 5 | 4 | 8 | 1 | 1 | 1 | 1 | 5 | 2 | 0.017301 | 115.603 | 68313 | 3 | 0 | SATURATED_REORDER |
| same_time_burst | 1 | 9 | 8 | 8 | 1 | 1 | 1 | 1 | 9 | 2 | 0.032023 | 62.456 | 79069 | 7 | 0 | SATURATED_REORDER |
| same_time_burst | 1 | 17 | 16 | 8 | 1 | 1 | 1 | 1 | 17 | 2 | 0.044323 | 45.123 | 125922 | 15 | 0 | SATURATED_REORDER |
| same_time_burst | 1 | 33 | 32 | 8 | 1 | 1 | 1 | 1 | 33 | 2 | 0.063912 | 31.293 | 224286 | 31 | 0 | SATURATED_REORDER |
| same_time_burst | 1 | 65 | 64 | 8 | 1 | 1 | 1 | 1 | 65 | 2 | 0.098048 | 20.398 | 400926 | 63 | 0 | SATURATED_REORDER |
| same_time_burst | 1 | 2 | 1 | 8 | 2 | 1 | 1 | 1 | 2 | 2 | 0.010864 | 184.094 | 53439 | 0 | 0 | CLEAN |
| same_time_burst | 1 | 3 | 2 | 8 | 2 | 1 | 2 | 2 | 3 | 3 | 0.018823 | 159.382 | 62638 | 0 | 0 | CLEAN |
| same_time_burst | 1 | 5 | 4 | 8 | 2 | 1 | 2 | 2 | 5 | 3 | 0.026554 | 112.975 | 72105 | 2 | 0 | SATURATED_REORDER |
| same_time_burst | 1 | 9 | 8 | 8 | 2 | 1 | 2 | 2 | 9 | 3 | 0.040324 | 74.397 | 85630 | 6 | 0 | SATURATED_REORDER |
| same_time_burst | 1 | 17 | 16 | 8 | 2 | 1 | 2 | 2 | 17 | 3 | 0.04074 | 73.638 | 126772 | 14 | 0 | SATURATED_REORDER |
| same_time_burst | 1 | 33 | 32 | 8 | 2 | 1 | 2 | 2 | 33 | 3 | 0.068936 | 43.518 | 222516 | 30 | 0 | SATURATED_REORDER |
| same_time_burst | 1 | 65 | 64 | 8 | 2 | 1 | 2 | 2 | 65 | 3 | 0.13152 | 22.81 | 402544 | 62 | 0 | SATURATED_REORDER |
| same_time_burst | 1 | 2 | 1 | 8 | 4 | 1 | 1 | 1 | 2 | 2 | 0.012863 | 155.486 | 52364 | 0 | 0 | CLEAN |
| same_time_burst | 1 | 3 | 2 | 8 | 4 | 1 | 2 | 2 | 3 | 3 | 0.026983 | 111.182 | 62477 | 0 | 0 | CLEAN |
| same_time_burst | 1 | 5 | 4 | 8 | 4 | 1 | 4 | 4 | 5 | 5 | 0.027214 | 183.727 | 79005 | 0 | 0 | CLEAN |
| same_time_burst | 1 | 9 | 8 | 8 | 4 | 1 | 4 | 4 | 9 | 5 | 0.041302 | 121.06 | 92527 | 4 | 0 | SATURATED_REORDER |
| same_time_burst | 1 | 17 | 16 | 8 | 4 | 1 | 4 | 4 | 17 | 5 | 0.085505 | 58.476 | 126222 | 12 | 0 | SATURATED_REORDER |
| same_time_burst | 1 | 33 | 32 | 8 | 4 | 1 | 4 | 4 | 33 | 5 | 0.072859 | 68.626 | 224664 | 28 | 0 | SATURATED_REORDER |
| same_time_burst | 1 | 65 | 64 | 8 | 4 | 1 | 4 | 4 | 65 | 5 | 0.152459 | 32.796 | 404154 | 60 | 0 | SATURATED_REORDER |
| same_time_burst | 1 | 2 | 1 | 8 | 8 | 1 | 1 | 1 | 2 | 2 | 0.017135 | 116.724 | 52255 | 0 | 0 | CLEAN |
| same_time_burst | 1 | 3 | 2 | 8 | 8 | 1 | 2 | 2 | 3 | 3 | 0.018307 | 163.876 | 62136 | 0 | 0 | CLEAN |
| same_time_burst | 1 | 5 | 4 | 8 | 8 | 1 | 4 | 4 | 5 | 5 | 0.022182 | 225.404 | 79028 | 0 | 0 | CLEAN |
| same_time_burst | 1 | 9 | 8 | 8 | 8 | 1 | 8 | 8 | 9 | 9 | 0.088772 | 101.383 | 116957 | 0 | 0 | CLEAN |
| same_time_burst | 1 | 17 | 16 | 8 | 8 | 1 | 8 | 8 | 17 | 9 | 0.074068 | 121.51 | 144107 | 8 | 0 | SATURATED_REORDER |
| same_time_burst | 1 | 33 | 32 | 8 | 8 | 1 | 8 | 8 | 33 | 9 | 0.083168 | 108.214 | 225494 | 24 | 0 | SATURATED_REORDER |
| same_time_burst | 1 | 65 | 64 | 8 | 8 | 1 | 8 | 8 | 65 | 9 | 0.14639 | 61.479 | 404175 | 56 | 0 | SATURATED_REORDER |
| same_time_burst | 1 | 2 | 1 | 8 | 16 | 1 | 1 | 1 | 2 | 2 | 0.012034 | 166.201 | 52244 | 0 | 0 | CLEAN |
| same_time_burst | 1 | 3 | 2 | 8 | 16 | 1 | 2 | 2 | 3 | 3 | 0.01624 | 184.73 | 62295 | 0 | 0 | CLEAN |
| same_time_burst | 1 | 5 | 4 | 8 | 16 | 1 | 4 | 4 | 5 | 5 | 0.022055 | 226.708 | 79077 | 0 | 0 | CLEAN |
| same_time_burst | 1 | 9 | 8 | 8 | 16 | 1 | 8 | 8 | 9 | 9 | 0.058493 | 153.864 | 117165 | 0 | 0 | CLEAN |
| same_time_burst | 1 | 17 | 16 | 8 | 16 | 1 | 16 | 16 | 17 | 17 | 0.132833 | 127.981 | 228351 | 0 | 0 | CLEAN |
| same_time_burst | 1 | 33 | 32 | 8 | 16 | 1 | 16 | 16 | 33 | 17 | 0.179774 | 94.563 | 281780 | 16 | 0 | SATURATED_REORDER |
| same_time_burst | 1 | 65 | 64 | 8 | 16 | 1 | 16 | 16 | 65 | 17 | 0.151604 | 112.134 | 407792 | 48 | 0 | SATURATED_REORDER |
| same_time_burst | 1 | 2 | 1 | 8 | 32 | 1 | 1 | 1 | 2 | 2 | 0.012197 | 163.973 | 52194 | 0 | 0 | CLEAN |
| same_time_burst | 1 | 3 | 2 | 8 | 32 | 1 | 2 | 2 | 3 | 3 | 0.018439 | 162.7 | 62284 | 0 | 0 | CLEAN |
| same_time_burst | 1 | 5 | 4 | 8 | 32 | 1 | 4 | 4 | 5 | 5 | 0.022131 | 225.926 | 79316 | 0 | 0 | CLEAN |
| same_time_burst | 1 | 9 | 8 | 8 | 32 | 1 | 8 | 8 | 9 | 9 | 0.065436 | 137.539 | 117154 | 0 | 0 | CLEAN |
| same_time_burst | 1 | 17 | 16 | 8 | 32 | 1 | 16 | 16 | 17 | 17 | 0.151591 | 112.144 | 227826 | 0 | 0 | CLEAN |
| same_time_burst | 1 | 33 | 32 | 8 | 32 | 1 | 32 | 32 | 33 | 33 | 0.261074 | 126.401 | 367289 | 0 | 0 | CLEAN |
| same_time_burst | 1 | 65 | 64 | 8 | 32 | 1 | 32 | 32 | 65 | 33 | 0.3734 | 88.377 | 436869 | 32 | 0 | SATURATED_REORDER |
| same_time_burst | 1 | 2 | 1 | 8 | 64 | 1 | 1 | 1 | 2 | 2 | 0.022043 | 90.732 | 53439 | 0 | 0 | CLEAN |
| same_time_burst | 1 | 3 | 2 | 8 | 64 | 1 | 2 | 2 | 3 | 3 | 0.026803 | 111.928 | 62391 | 0 | 0 | CLEAN |
| same_time_burst | 1 | 5 | 4 | 8 | 64 | 1 | 4 | 4 | 5 | 5 | 0.035899 | 139.28 | 78961 | 0 | 0 | CLEAN |
| same_time_burst | 1 | 9 | 8 | 8 | 64 | 1 | 8 | 8 | 9 | 9 | 0.082143 | 109.565 | 117062 | 0 | 0 | CLEAN |
| same_time_burst | 1 | 17 | 16 | 8 | 64 | 1 | 16 | 16 | 17 | 17 | 0.12699 | 133.869 | 228333 | 0 | 0 | CLEAN |
| same_time_burst | 1 | 33 | 32 | 8 | 64 | 1 | 32 | 32 | 33 | 33 | 0.372727 | 88.537 | 366551 | 0 | 0 | CLEAN |
| same_time_burst | 1 | 65 | 64 | 8 | 64 | 1 | 64 | 64 | 65 | 65 | 0.594091 | 109.411 | 520465 | 0 | 0 | CLEAN |
| mixed | 256 | 8 | 4 | 512 | 16 | 256 | 256 | 4 | 2048 | 2048 | 12.548795 | 163.203 | 2772826 | 0 | 0 | CLEAN |
| key_cardinality | 31 | 3 | 1 | 32 | 64 | 31 | 31 | 1 | 93 | 93 | 0.278811 | 333.559 | 520267 | 0 | 0 | CLEAN |
| key_cardinality | 32 | 3 | 1 | 32 | 64 | 32 | 32 | 1 | 96 | 96 | 0.288105 | 333.212 | 532056 | 0 | 0 | CLEAN |
| key_cardinality | 33 | 3 | 1 | 32 | 64 | 32 | 33 | 1 | 99 | 96 | 0.335512 | 286.13 | 607053 | 0 | 3 | STATE_CAPACITY_EXCEEDED |
| key_cardinality | 2047 | 3 | 1 | 2048 | 64 | 2047 | 256 | 1 | 6141 | 6141 | 17.568916 | 349.538 | 6039536 | 0 | 0 | CLEAN |
| key_cardinality | 2048 | 3 | 1 | 2048 | 64 | 2048 | 256 | 1 | 6144 | 6144 | 17.166207 | 357.912 | 6045930 | 0 | 0 | CLEAN |
| key_cardinality | 2049 | 3 | 1 | 2048 | 64 | 2048 | 256 | 1 | 6147 | 6144 | 17.543602 | 350.213 | 6063431 | 0 | 3 | STATE_CAPACITY_EXCEEDED |
| key_cardinality | 512 | 3 | 1 | 513 | 64 | 512 | 256 | 1 | 1536 | 1536 | 4.257085 | 360.81 | 2745571 | 0 | 0 | CLEAN |
| key_cardinality | 512 | 3 | 1 | 513 | 64 | 512 | 256 | 1 | 1536 | 1536 | 4.242782 | 362.027 | 2739984 | 0 | 0 | CLEAN |
| full_history | 128 | 32 | 1 | 129 | 64 | 128 | 128 | 1 | 4096 | 4096 | 23.610073 | 173.485 | 3754616 | 0 | 0 | CLEAN |
| full_history | 128 | 32 | 1 | 129 | 64 | 128 | 128 | 1 | 4096 | 4096 | 23.080472 | 177.466 | 3753712 | 0 | 0 | CLEAN |
| same_time_burst | 1 | 65 | 64 | 8 | 64 | 1 | 64 | 64 | 65 | 65 | 0.445515 | 145.899 | 521184 | 0 | 0 | CLEAN |
| same_time_burst | 1 | 65 | 64 | 8 | 64 | 1 | 64 | 64 | 65 | 65 | 0.478104 | 135.954 | 520197 | 0 | 0 | CLEAN |
| same_time_burst | 1 | 65 | 64 | 8 | 32 | 1 | 32 | 32 | 65 | 33 | 0.237866 | 138.734 | 440199 | 32 | 0 | SATURATED_REORDER |
| same_time_burst | 1 | 65 | 64 | 8 | 32 | 1 | 32 | 32 | 65 | 33 | 0.26639 | 123.879 | 438760 | 32 | 0 | SATURATED_REORDER |
| mixed | 256 | 8 | 4 | 512 | 16 | 256 | 256 | 4 | 2048 | 2048 | 11.785686 | 173.77 | 2772651 | 0 | 0 | CLEAN |
| mixed | 256 | 8 | 4 | 512 | 16 | 256 | 256 | 4 | 2048 | 2048 | 11.707549 | 174.93 | 2766760 | 0 | 0 | CLEAN |

Offered rate is records/observations submitted per wall second. Successfully processed rate is finalized results per wall second; every successfully processed C2-R1 observation produces one warm-up or ready result. A rate is clean only when ingress, shard, reorder, state-capacity, and processing error counts are all zero. `tracemalloc` reports Python allocations, not full-process RSS. Percentiles are emitted only with at least 100 samples.

## Observed boundaries and timing

- Aggregate ingress queue saturation: 0; shard queue saturation: 0.
- Intentional reorder saturation gaps: 586; intentional state-capacity errors: 6.
- Unexpected processing errors: 0; late events: 0.
- Largest clean minimal-state point: 2048 live keys at 265.936 processed observations/s.
- Largest clean full-history point: 1024 live keys at 110.404 processed observations/s.
- Smallest clean reorder bound by controlled burst: {1: 1, 2: 2, 4: 4, 8: 8, 16: 16, 32: 32, 64: 64}.
- SQLite runs: 3; all have equal finalized and persisted result counts: True. Canonicalization, ingest-submission, plugin, persistence, and end-to-end p50/p95/p99 values are preserved in the JSON artifact.

## Candidate discussion

Clean tested state capacities span 32 through 2049 entries at the exact tabled workloads. Clean tested reorder capacities: [1, 2, 4, 8, 16, 32, 64]. Higher retained history increases memory per key; SQLite persistence reduces the observed vertical-slice rate relative to no-persistence runs. These measurements apply only to the exact environment and workloads above. No automatic headroom multiplier is selected.

The smallest tested clean state/reorder values for a workload can be read from the exact rows and machine-readable artifact. These are a **CANDIDATE RANGE FOR HUMAN GATE**, not final configuration. The default registry remains `LaneTarget("c2") -> C2ShellPlugin`; C2-R1 has not been activated.

HUMAN GATE REQUIRED

STATE CAPACITY CANDIDATES:
32-2048 among exact tested acceptance boundaries; see exact rows

REORDER CAPACITY CANDIDATES:
{1: 1, 2: 2, 4: 4, 8: 8, 16: 16, 32: 32, 64: 64}

SUPPORTING RUN IDS:
['c914ffa4b2c8', 'bca0dc6617fc', '67b88768fbfe', '31f4baf27ddd', 'df66f8decac2', '2e4f09ac9d8f']

KNOWN LIMITATIONS:
- Single development host and synthetic typed-NDJSON replay only.
- `tracemalloc` excludes native allocations and is not RSS.
- C2-R1 vertical slice only; no DGA model, other threat paths, PCAP adapter, API, dashboard, or alert path.
- Rates are machine- and workload-specific and are not production capacity.

NO VALUE HAS BEEN ACTIVATED YET.
