# Current Stack Real Benchmark Report

> **PRE-DGA / SUPERSEDED FOR FINAL MVP STACK CHARACTERIZATION**

This historical M13 evidence is retained unchanged below. Use
`FINAL_MVP_MODEL_INCLUSIVE_BENCHMARK_REPORT.md` for the activated final-MVP stack.

> **PRE-DGA / CONTROLLED MVP / NOT PRODUCTION THROUGHPUT**

Classification: **PRE-DGA CURRENT-MVP STACK CHARACTERIZATION**. These controlled measurements are not final, production, sustained-capacity, or sizing claims. DGA model inference is not active.

## Environment

```json
{
  "captured_at": "2026-09-22T18:23:27.942379+00:00",
  "os_platform": "Windows-11-10.0.26200-SP0",
  "python_version": "3.13.7",
  "cpu_logical": 18,
  "cpu_physical": 14,
  "ram_total_bytes": 16568107008,
  "dependency_versions": {
    "evidencegate": "0.1.0",
    "dpkt": "1.9.8",
    "pydantic": "2.13.5",
    "fastapi": "0.141.1",
    "psutil": "7.0.0"
  }
}
```

Both modes use the real source adapter, shared canonicalizer, default 16-target registry, routing, mechanism state, finalization, and a disk-backed SQLite database at replay speed 0.

## Runs

| Source | Read | Observations | Routed updates | Finalized | Persisted | Wall seconds | Zero drop |
|---|---:|---:|---:|---:|---:|---:|---|
| NDJSON | 11 | 11 | 42 | 35 | 35 | 0.082028 | True |
| PCAP | 11 | 11 | 42 | 35 | 35 | 0.075716 | True |

## Persist latency

| Source | p50 ms | p95 ms | p99 ms |
|---|---:|---:|---:|
| NDJSON | 0.7405 | 3.7542 | 8.4191 |
| PCAP | 0.7176 | 2.4165 | 7.3171 |

Structural time-to-signal remains a mechanism-evidence property. End-to-end evidence latency is not combined with historical capture timestamps. Replay wall duration is reported separately.

## Memory and state

| Source | RSS start | RSS peak | RSS end | Active state end | Peak reorder | SQLite bytes |
|---|---:|---:|---:|---:|---:|---:|
| NDJSON | 46817280 | 47616000 | 47616000 | 14 | 1 | 417792 |
| PCAP | 47730688 | 48009216 | 48009216 | 14 | 1 | 417792 |

## Quality and capacity

Each run's machine-readable counters separately report quality gaps, state-capacity events, reorder-capacity events, input drops, runtime-work drops, and SSE notification drops. `zero_drop` requires no quality gap and no runtime error control. The fixture is deliberately small; the observed processing rate is descriptive only and is not a sustainable-throughput headline.

## Limitations

- single development host and short deterministic private-network fixtures
- processing latency is not independently instrumented; persistence latency is reported
- no UI subscriber was attached, so SSE drops are zero by construction
- results must be rerun after DGA model integration
