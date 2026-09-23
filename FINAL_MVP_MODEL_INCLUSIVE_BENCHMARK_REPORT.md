# Final MVP Model-Inclusive Benchmark Report

> **CONTROLLED MVP CHARACTERIZATION — NOT PRODUCTION SIZING**

Classification: **CONTROLLED FINAL-MVP MODEL-INCLUSIVE STACK CHARACTERIZATION**. This is not a production capacity, enterprise sizing, or SLA claim.

## Startup and DGA model

- Readiness: `VERIFIED_READY`
- Load time: `17.189049` seconds
- RSS before/after/delta: `45629440` / `223756288` / `178126848` bytes
- Artifact: `39da209d2cfd869dd284e10b8a07adc04826c95146712cc6854a69b9873890df`
- Frozen model input / score: `ajdkskqweoiuzx.com` / `0.9851716132182514` (regression tolerance `1e-12`)
- DGA representation p50/p95/p99 ms: `{'p50_ms': 0.0222, 'p95_ms': 0.0453, 'p99_ms': 0.0855}`
- DGA transform + inference p50/p95/p99 ms: `{'p50_ms': 0.4975, 'p95_ms': 1.2613, 'p99_ms': 1.8312}`
- DGA result persistence p50/p95/p99 ms (typed run): `{'p50_ms': 0.6902, 'p95_ms': 0.6902, 'p99_ms': 0.6902}`

The numeric output is a **DGA-labelled lexical resemblance score**, not malware, infection, compromise, C2, tunnel, exfiltration, ownership, intent, or attack probability. No production threshold is active.

## Workload and runs

Exact controlled mix: `{"eligible_families": ["DDoS", "C2", "DGA M1", "DNS-T1", "ENC-A", "Recon", "Exfil-M1"], "raw_pcap_packets": 11, "typed_records": {"DNS": 1, "FLOW": 4, "PACKET": 3, "TLS": 1}}`.

| Source | Read | Observations | Routed updates | Persisted | DGA exercised | Zero drop |
|---|---:|---:|---:|---:|---|---|
| TYPED_NDJSON | 9 | 9 | 20 | 21 | True | True |
| RAW_PCAP | 11 | 11 | 42 | 35 | False | True |

The typed run exercises real DGA representation, vectorizer, classifier, routing, finalization, and disk-backed SQLite persistence. The raw-PCAP run does **not** exercise DGA because raw-PCAP DNS extraction remains deferred.

## Latency

| Source | Proc p50 | Proc p95 | Proc p99 | Persist p50 | Persist p95 | Persist p99 | E2E p50 | E2E p95 | E2E p99 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| TYPED_NDJSON | 0.0581 | 0.2568 | 0.2568 | 0.7676 | 1.7073 | 2.1157 | 7.0706 | 41.603 | 43.72 |
| RAW_PCAP | 0.1143 | 0.1418 | 0.1418 | 0.6001 | 1.9769 | 22.7563 | 13.4633 | 47.8102 | 76.1705 |

Processing is routing/enqueue latency. Persistence is SQLite write latency. End-to-end is in-process observation admission through persisted evidence and is not combined with historical capture timestamps. Replay wall-clock and structural time-to-signal remain separately recorded in JSON.

## Memory, state, and storage

| Source | RSS start | RSS peak | RSS end | SQLite bytes | State entries end | Peak reorder |
|---|---:|---:|---:|---:|---:|---:|
| TYPED_NDJSON | 224608256 | 227160064 | 227160064 | 290816 | 5 | 1 |
| RAW_PCAP | 227184640 | 227581952 | 227581952 | 417792 | 14 | 1 |

## No-drop region and target

demonstrated for the two bounded replay points only; no offered-rate sweep exists in this harness. Proposed SIH demo throughput target: **NONE**. No target proposed from short deterministic fixtures; Control Room approval remains required.

## Limitations

- single development host and short deterministic private-network fixtures
- raw-PCAP DNS extraction is deferred, so the PCAP run does not exercise DGA
- no live interface capture and no NetFlow/IPFIX/sFlow adapter
- no sustained offered-rate sweep; observed replay rates are descriptive only
- SSE notification drops are zero by construction because no UI subscriber is attached
