# Sustained Final MVP Benchmark Report

## M17 post-activation acceptance (2026-09-25)

The approved 50 offered observations/s controlled demo point **passed** with
`SIH_ALERT_POLICY_V1` active. The normal FastAPI application, its SQLite writer,
dashboard, and `/alerts` route were available throughout the measured run.
The warmed 16-target registration and the same declared nine-observation
mixed workload were used. A separate 3-second warm-up was excluded. The
projection runs at query time, outside the ingestion hot path. `/alerts`
was queried before measured load and after full drain; it was **not** queried
continuously during the 30-second measured phase because repeated 500-result
reads distorted preliminary measurements.

| Measure | Post-activation result |
|---|---:|
| Configured offered rate / duration | 50 observations/s / 30 s |
| Actual offered rate | 50.009 observations/s |
| Offered / accepted / processed | 1,500 / 1,500 / 1,500 |
| Persisted immutable Results | 2,837 |
| Input drops / runtime work drops | 0 / 0 |
| Queue overflow / state-capacity / reorder-capacity events | 0 / 0 / 0 |
| Persistence failures | 0 |
| Peak / final backlog | 70 / 0 |
| Backlog slope | -0.029 items/s |
| Post-offer drain | 0.201802 s |
| Processing p50 / p95 / p99 | 186.3378 / 883.2264 / 1,017.04 ms |
| End-to-end evidence p50 / p95 / p99 | 312.552 / 983.132 / 1,165.4749 ms |
| Early / late processing p95 | 896.2601 / 883.6355 ms |
| Peak RSS | 244,203,520 bytes |
| `/alerts` pre / post HTTP status | 200 / 200 |
| Post-run bounded projection | 411 analyst alerts / 89 separate status items |

The final measurement is stored in
`benchmark_results/final_mvp_acceptance.json`. Preliminary setup runs at
50 observations/s failed the sustained criterion: periodic 500-result reads
created growing backlog in two runs, and a run using a separate measurement
writer from the application writer also grew backlog. The acceptance harness
was corrected to use the normal application's writer and to keep the optional
large API reads outside the measured interval. The final run above is the
post-correction acceptance evidence; the earlier failures are not presented
as passes.

On the measured development machine, the controlled MVP sustained a configured offered rate of 50 input observations/s for 30 seconds with zero input/runtime drops under the declared mixed workload.

This is a controlled SIH demo operating claim, not production capacity or an
SLA. The historical M16 sweep and its candidate wording remain below.

> **DEVELOPMENT MACHINE / CONTROLLED MVP / NOT PRODUCTION CAPACITY**

Classification: **CONTROLLED SIH DEMO SUSTAINED OPERATING-RATE CHARACTERIZATION**. This measures offered typed input observations on one development machine. It is not production capacity, an SLA, network line rate, or attacks per second.

## Method

The exact stack is real canonicalization -> the real 16-target registry -> the verified DGA model -> real stateful mechanisms and event-time reorder -> real finalization -> disk-backed SQLite (WAL/NORMAL). The DGA model is loaded and verified once, followed by a separate 3.0-second warm-up excluded from every steady-state point.

Workload: `{"cycle_observations": 9, "eligible_families": ["DDoS", "C2", "DGA M1-R1", "DNS-T1", "ENC-A", "Recon", "Exfil-M1"], "episode_policy": "unique source and role identities per nine-observation episode", "event_time_policy": "fixture-relative offsets; seven-minute monotonic episode progression", "interpretation_limit": "repetition is infrastructure load only, not population-level threat evidence", "typed_mix_counts": {"DNS": 1, "FLOW": 4, "PACKET": 3, "TLS": 1}, "typed_mix_proportions": {"DNS": 0.1111111111111111, "FLOW": 0.4444444444444444, "PACKET": 0.3333333333333333, "TLS": 0.1111111111111111}}`

Duration basis: 30 seconds per measured point after separate warm-up; fixed offered count is rate multiplied by duration. Queue/reorder occupancy is sampled every 50 ms. A point is sustainable only with every declared drop counter at zero, completed routed work, empty final backlog, stable backlog, prompt drain, bounded latency, and no runtime control error.

## Environment and startup

```json
{
  "environment": {
    "captured_at": "2026-09-23T18:01:50.816058+00:00",
    "cpu_logical": 18,
    "cpu_model": "Intel64 Family 6 Model 170 Stepping 4, GenuineIntel",
    "cpu_physical": 14,
    "dependencies": {
      "dpkt": "1.9.8",
      "evidencegate": "0.1.0",
      "fastapi": "0.141.1",
      "joblib": "1.6.0",
      "scikit-learn": "1.6.1",
      "tldextract": "5.1.3"
    },
    "os": "Windows-11-10.0.26200-SP0",
    "python": "3.13.7",
    "ram_total_bytes": 16568107008,
    "sqlite": {
      "foreign_keys": "ON",
      "journal_mode": "WAL",
      "synchronous": "NORMAL"
    }
  },
  "model": {
    "artifact_sha256": "39da209d2cfd869dd284e10b8a07adc04826c95146712cc6854a69b9873890df",
    "readiness": "VERIFIED_READY",
    "rss_after_load_bytes": 220590080,
    "rss_before_load_bytes": 42627072,
    "rss_delta_bytes": 177963008,
    "verification_and_load_seconds": 3.339475,
    "warmup_duration_seconds": 3.0,
    "warmup_excluded_from_steady_state": true
  }
}
```

## Rate sweep and repetitions

| Requested obs/s | Rep | Offered | Actual offered/s | Accepted/s | Processed/s | Routed updates/s | Persisted/s | Runtime drops | Peak backlog | Drain s | Zero drop | Sustainable |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| 25 | 1 | 750 | 25.03 | 25.03 | 24.948 | 44.588 | 47.234 | 0 | 39 | 0.099577 | True | True |
| 50 | 1 | 1500 | 49.29 | 49.29 | 48.499 | 87.737 | 91.728 | 0 | 113 | 0.49655 | True | True |
| 75 | 1 | 2250 | 74.659 | 74.659 | 73.35 | 132.727 | 138.55 | 0 | 175 | 0.537645 | True | True |
| 100 | 1 | 3000 | 98.32 | 98.32 | 86.851 | 174.879 | 164.149 | 0 | 1065 | 4.029348 | True | False |
| 75 | 2 | 2250 | 75.002 | 75.002 | 74.107 | 133.337 | 139.98 | 0 | 100 | 0.362178 | True | True |
| 75 | 3 | 2250 | 74.956 | 74.956 | 73.826 | 133.256 | 139.448 | 0 | 137 | 0.459765 | True | True |
| 50 | 2 | 1500 | 50.027 | 50.027 | 49.649 | 89.048 | 93.902 | 0 | 55 | 0.228496 | True | True |
| 50 | 3 | 1500 | 50.019 | 50.019 | 49.653 | 89.033 | 93.911 | 0 | 67 | 0.220678 | True | True |

Highest repeatedly demonstrated sustainable zero-drop point: **75 observations/s**.

First saturation/limit point: **100**.

Candidate controlled demo target: **50 observations/s**. Margin below the highest repeated point: **25 observations/s**.

## Candidate latency

| Rep | Processing p50 ms | p95 | p99 | Persistence p50 ms | p95 | p99 | End-to-end evidence p50 ms | p95 | p99 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 235.0961 | 1044.8326 | 1556.2789 | 0.7831 | 7.7715 | 54.3491 | 317.0692 | 1182.3517 | 1759.3116 |
| 2 | 163.8731 | 873.2719 | 1011.313 | 0.8514 | 6.936 | 50.76 | 281.6051 | 962.8729 | 1113.084 |
| 3 | 198.028 | 873.0188 | 1024.9503 | 0.9033 | 7.9604 | 57.706 | 315.9587 | 1002.203 | 1266.1127 |

Processing latency runs from offered admission until every selected mechanism update completes. Persistence latency is the actual SQLite write. End-to-end evidence latency runs from the latest contributing observation admission until its immutable result is persisted.

## Candidate memory and storage

| Rep | RSS start | RSS peak | RSS final | Growth | Peak state entries | Peak reorder | SQLite bytes |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 226295808 | 227225600 | 227225600 | 929792 | 50 | 27 | 16949248 |
| 2 | 231776256 | 232124416 | 232124416 | 348160 | 51 | 18 | 16973824 |
| 3 | 232157184 | 233070592 | 233070592 | 913408 | 50 | 18 | 16904192 |

## Governed wording

On the measured development machine, the controlled MVP sustained a configured offered rate of 50 input observations/s for 30 seconds with zero input/runtime drops under the declared mixed workload.

## Limitations

- single measured development host; results do not generalize to production sizing
- typed deterministic workload rather than live capture or network line-rate input
- repeated fixtures are load stimuli and are not population-level threat evidence
- SSE subscriber notification loss is out of scope and recorded separately from runtime drops
- raw PCAP is not used for the seven-family rate because its DNS canonical extraction is deferred
