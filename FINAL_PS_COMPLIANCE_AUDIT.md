# Final Official PS Compliance Audit

## Scope and conclusion

EvidenceGate is a passive, read-only, streaming controlled MVP that incrementally
canonicalizes observations, routes a fixed 16-target registry, constructs bounded
evidence, persists immutable results, and exposes REST, SSE, replay, runtime
status, and a dashboard. It does not decrypt payloads. This audit does **not**
claim 100% problem-statement completion or production readiness.

## Requirement status

| Requirement | Status | Evidence / limit |
|---|---|---|
| Passive / read-only | PASS | Typed replay and offline PCAP sources are read-only. |
| No payload decryption | PASS | ENC-A uses visible handshake metadata only. |
| Streaming incremental | PASS | Records/packets are canonicalized and routed incrementally. |
| Bounded evidence latency | PASS FOR CONTROLLED MVP | Stateless lanes signal on one admitted observation; stateful windows and capacities are explicit. No production SLA. |
| Throughput characterization | PASS WITH SUSTAINED CONTROLLED EVIDENCE | Approved 50 offered observations/s controlled demo point, with three M16 sustained repetitions and one M17 post-activation acceptance. No production capacity or SLA claim. |
| Ingest | PASS FOR IMPLEMENTED SOURCES | Typed NDJSON and offline raw PCAP. |
| Feature extraction | PASS | Factual canonical and mechanism-specific evidence construction. |
| Active model inference | PASS | Verified DGA-A1/M1-R1 vectorizer/classifier inference. |
| Alert/result output | PASS FOR CONTROLLED MVP | `/results` remains immutable scientific evidence; active `/alerts` is a versioned SIH analyst presentation. |
| Dashboard | PASS | Evidence Results, Analyst Alerts, and System & Evidence Status are active by default. |
| Six official threat categories | PASS AS BOUNDED EVIDENCE | DDoS, C2, combined DGA/DNS category, encrypted, recon, and exfiltration have active mechanisms. |
| Standardized alert schema | PASS — SIH_ALERT_POLICY_V1 ACTIVE | Deterministic, provenance-preserving projections are available by default. |
| Confidence | PASS WITH BASIS-AWARE SEMANTICS | DGA uses its lexical `MODEL_SCORE`; all non-DGA numeric scores are null with mandatory `STATISTICAL_SUPPORT` or `OBSERVED_EVIDENCE` basis. |
| Severity | PASS AS OPERATIONAL ANALYST PRIORITY | `REVIEW` means analyst priority only; system/quality `INFO`/`ATTENTION` stays separate. |

## Family status

| Family | Controlled-MVP status |
|---|---|
| DDoS | ACTIVE factual mechanisms |
| C2 | ACTIVE R1 recurrence measurement |
| DGA | ACTIVE M1-R1 lexical model evidence |
| DNS tunnelling | ACTIVE T1 structural observation |
| Encrypted | ACTIVE ENC-A handshake evidence |
| Recon | ACTIVE H/V/2D/TCP measurements |
| Exfiltration | ACTIVE M1 transfer magnitude |

## Remaining gaps

- Non-DGA numeric attack probability is not defined; no fake probability is supplied.
- `REVIEW` is operational analyst priority, not scientific severity or impact.
- Raw-PCAP DNS extraction is deferred, so raw PCAP does not exercise DGA/DNS-T1.
- Live interface capture is deferred.
- NetFlow/IPFIX/sFlow adapters are deferred.
- The sustained benchmark is a single-host controlled characterization, not production sizing or an SLA.

On the measured development machine, the controlled MVP sustained a configured offered rate of 50 input observations/s for 30 seconds with zero input/runtime drops under the declared mixed workload.

The M17 post-activation acceptance used the normal application SQLite writer,
verified active `SIH_ALERT_POLICY_V1` and dashboard availability, and passed
with 1,500/1,500 offered/processed observations, zero queue/state/reorder/
persistence failures, stable backlog (peak 70, final zero), and a 0.201802 s
drain. `/alerts` was read before and after the measured phase; its query-time
projection was not continuously exercised during the rate interval. See
`SUSTAINED_FINAL_MVP_BENCHMARK_REPORT.md` for full latency and RSS evidence.

No DGA score is fed into DNS-T1, C2, or a global score. Activating the one ML
lane does not upgrade any other mechanism’s conclusion and does not make the
system ML-based end to end.
