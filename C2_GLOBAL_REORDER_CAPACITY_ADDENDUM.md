# [EXPERIMENT]
# CONTROLLED MVP GLOBAL REORDER CAPACITY CHARACTERIZATION

This addendum uses controlled synthetic engineering load through the real typed-NDJSON replay, C2-R1 plugin, event-time reorder, StateStore, shards, and real result finalization. It makes no production-capacity or C2-detection claim.

## Root cause and policy contract

A per-key bound alone cannot bound the sum of buffers when many distinct keys share an unclosed event-time boundary. `EventTimeReorderPolicy` now requires independent positive non-boolean `max_buffered_events_per_key` and `max_buffered_events_total` values, with total greater than or equal to per-key. The dispatcher checks per-key first, then total, before insertion.

Existing buffered facts are never evicted. A fact rejected by the lane-wide budget produces one `REORDER_BUFFER_TOTAL_SATURATION` QualityGap and invokes the plugin's existing GapAction. Per-key overflow remains `REORDER_BUFFER_SATURATION`. Watermark ordering and release semantics are unchanged.

State capacity, per-key reorder capacity, lane-total reorder capacity, and C2 scientific retained history (32 events) remain four separate concepts. None is derived from another.

## Many-key same-time workload and total sweep

| run | keys | events/key | per-key | total | offered | accepted peak | rejected total | peak total | peak/key | seconds | current traced at peak | peak traced | bytes/pending | status |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 6f7dcc692d4a | 64 | 4 | 16 | 256 | 257 | 256 | 0 | 256 | 4 | 0.809272 | 1468066 | 1473274 | 5734.633 | CLEAN |
| a1929ce373e0 | 128 | 4 | 16 | 512 | 513 | 512 | 0 | 512 | 4 | 1.721339 | 2698613 | 2703207 | 5270.729 | CLEAN |
| 7576cfd60851 | 128 | 8 | 16 | 1024 | 1025 | 1024 | 0 | 1024 | 8 | 5.719061 | 5128954 | 5131958 | 5008.744 | CLEAN |
| bc6e57503ec1 | 256 | 8 | 16 | 2048 | 2049 | 2048 | 0 | 2048 | 8 | 10.426852 | 10023423 | 10026427 | 4894.25 | CLEAN |
| 26418bdf42b3 | 257 | 1 | 16 | 256 | 258 | 256 | 1 | 256 | 1 | 0.991046 | 1517905 | 1521719 | 5929.316 | SATURATED_REORDER_TOTAL |
| 0296f5fcfd79 | 64 | 8 | 16 | 256 | 513 | 256 | 256 | 256 | 8 | 2.007583 | 1465997 | 1469607 | 5726.551 | SATURATED_REORDER_TOTAL |
| 24ed6b0da313 | 64 | 4 | 16 | 256 | 257 | 256 | 0 | 256 | 4 | 1.454207 | 1467489 | 1472747 | 5732.379 | CLEAN |
| adfc7ce51695 | 128 | 4 | 16 | 512 | 513 | 512 | 0 | 512 | 4 | 2.315109 | 2698701 | 2703295 | 5270.9 | CLEAN |
| 2472893e411e | 128 | 8 | 16 | 1024 | 1025 | 1024 | 0 | 1024 | 8 | 5.823146 | 5128783 | 5131787 | 5008.577 | CLEAN |
| a675332a2fcb | 256 | 8 | 16 | 2048 | 2049 | 2048 | 0 | 2048 | 8 | 10.459166 | 10023378 | 10026382 | 4894.228 | CLEAN |
| 3fc4357b51a1 | 257 | 1 | 16 | 256 | 258 | 256 | 1 | 256 | 1 | 0.83452 | 1517642 | 1521556 | 5928.289 | SATURATED_REORDER_TOTAL |
| 201425410f93 | 64 | 8 | 16 | 256 | 513 | 256 | 256 | 256 | 8 | 1.731369 | 1465285 | 1468945 | 5723.77 | SATURATED_REORDER_TOTAL |
| 4f2e64aaae3a | 64 | 4 | 16 | 256 | 257 | 256 | 0 | 256 | 4 | 1.08607 | 1467527 | 1472785 | 5732.527 | CLEAN |
| f6ade6ba503f | 128 | 4 | 16 | 512 | 513 | 512 | 0 | 512 | 4 | 1.923048 | 2698447 | 2703091 | 5270.404 | CLEAN |
| 95ffdf38c5e2 | 128 | 8 | 16 | 1024 | 1025 | 1024 | 0 | 1024 | 8 | 6.352945 | 5128695 | 5131699 | 5008.491 | CLEAN |
| 3868fce0fb5c | 256 | 8 | 16 | 2048 | 2049 | 2048 | 0 | 2048 | 8 | 9.592343 | 10023446 | 10026450 | 4894.261 | CLEAN |
| aaf21541758b | 257 | 1 | 16 | 256 | 258 | 256 | 1 | 256 | 1 | 1.362165 | 1518276 | 1522140 | 5930.766 | SATURATED_REORDER_TOTAL |
| 1134f25e0922 | 64 | 8 | 16 | 256 | 513 | 256 | 256 | 256 | 8 | 2.212988 | 1466193 | 1469853 | 5727.316 | SATURATED_REORDER_TOTAL |

The workload assigns explicit trusted `SOURCE_DECLARED_ROLE` client, peer, and service identities. All K x B observations share one event time; a later source timestamp advances the real replay watermark. Offered observations include that later boundary record. Accepted peak counts refer to simultaneously buffered same-time observations; rejected-total counts are one visible gap per incoming excess fact.

## Memory and throughput interpretation

The table records Python traced current and peak allocation at the observed pending-buffer maximum plus an approximate incremental bytes/pending observation value. `tracemalloc` is not process RSS and the point-in-time value includes runtime and benchmark instrumentation. Saturated offered rates are not sustainable-throughput claims.

## Environment

- Captured: 2026-09-22T03:42:33.125598+00:00
- OS: Windows-11-10.0.26200-SP0
- Python: 3.13.7
- CPU: Intel64 Family 6 Model 170 Stepping 4, GenuineIntel (18 logical CPUs)
- Available memory: unavailable
- Starting git commit: `cb4008f3924133a9433bed1b2bd007fd903f8803`

## Limitations

- Single development host and controlled synthetic typed replay.
- Point-in-time `tracemalloc` allocation is not RSS.
- C2-R1 vertical slice only; no DGA, other threats, API, dashboard, or raw-PCAP path.
- Tested values are engineering candidates, not activated defaults or production claims.

HUMAN GATE REQUIRED

PROVISIONAL STATE CAPACITY:
1024
NOT YET ACTIVE

PROVISIONAL PER-KEY REORDER CAPACITY:
16
NOT YET ACTIVE

TOTAL REORDER CAPACITY CANDIDATES:
256-2048 among exact clean tested bounds

SUPPORTING RUN IDS:
['6f7dcc692d4a', 'a1929ce373e0', '7576cfd60851', 'bc6e57503ec1', '26418bdf42b3', '0296f5fcfd79']

KNOWN LIMITATIONS:
- Single-host controlled synthetic replay; tracemalloc is not RSS.
- Candidate values require Control Room review and are not production capacity.

NO C2 CAPACITY VALUE HAS BEEN ACTIVATED.
