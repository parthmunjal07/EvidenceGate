# Final Alert and Throughput Policy Gate

> Historical M16 gate record. **PROMOTED** by `MVP-DEC-FINAL-ALERT-THROUGHPUT-V1`
> (approved 2026-09-23). The active implementation is `SIH_ALERT_POLICY_V1`;
> see `SIH_ALERT_POLICY_V1.md` and `FINAL_MVP_IMPLEMENTATION_CLOSURE.md`.

## Gate status

M16 implementation and controlled measurement are complete. The sustained-rate evidence supports a **candidate controlled SIH demo offered-input rate of 50 observations/s** on the measured development machine. The alert projection is implemented as `SIH_ALERT_POLICY_V1_CANDIDATE`, but it is deliberately inactive by default pending the final Human Gate.

Neither conclusion is a production-capacity, SLA, network-line-rate, attacks-per-second, or confirmed-attack claim. Immutable EvidenceGate results remain the scientific authority.

## Sustained benchmark methodology

The benchmark uses the exact application path:

`real canonicalization -> real 16-target registry -> verified DGA model -> real stateful mechanisms/reorder -> real finalization -> disk-backed SQLite`

The DGA artifact is verified and loaded once. A separate three-second warm-up is excluded from steady-state measurement. Each measured point lasts 30 seconds and offers a deterministic nine-observation typed cycle containing three packets, four flows, one DNS observation, and one TLS observation. The cycle is eligible for DDoS, C2, DGA M1-R1, DNS-T1, ENC-A, Recon, and Exfil-M1.

Each nine-observation episode has an explicit unique source and role identity. Within-episode event-time offsets are retained and episode event time advances monotonically by seven minutes. This exercises recurrence, state expiry, lifecycle, reorder, and SQLite behavior without an identical-time flood or unbounded misleading state accumulation. Repetition is infrastructure load only and is not population-level threat evidence.

The offered-rate clock is independent of runtime completion. Offered, accepted, processed, routed-update, and persisted-result rates are recorded separately. Dispatcher, shard, and reorder backlog is sampled every 50 ms. Drain starts when offered load stops and includes outstanding watermarks, queued mechanism work, finalization, and SQLite persistence.

A run is sustainable only if:

- dropped input, runtime work, queue overflow, state-capacity events, reorder-capacity events, and persistence failures are all zero;
- every accepted observation completes all selected mechanism updates;
- final backlog is zero and the sampled backlog has no sustained positive growth;
- early/late latency does not diverge;
- post-offer drain is prompt; and
- no runtime control error occurs.

## Environment and model startup

| Item | Measured value |
|---|---|
| CPU | Intel64 Family 6 Model 170 Stepping 4, GenuineIntel |
| Logical / physical cores | 18 / 14 |
| RAM | 16,568,107,008 bytes |
| OS | Windows 11 (`10.0.26200`) |
| Python | 3.13.7 |
| dpkt | 1.9.8 |
| scikit-learn | 1.6.1 |
| joblib | 1.6.0 |
| tldextract | 5.1.3 |
| FastAPI | 0.141.1 |
| SQLite | WAL, `synchronous=NORMAL`, foreign keys ON |
| DGA SHA-256 | `39da209d2cfd869dd284e10b8a07adc04826c95146712cc6854a69b9873890df` |
| Default targets | 16 |
| Model verification/load | 5.507010 s |
| RSS before / after / delta | 43,278,336 / 220,241,920 / 176,963,584 bytes |
| Excluded warm-up | 3 s |

## Rate sweep and repetitions

All listed runs had zero input/runtime drops, zero queue overflow, zero state-capacity events, zero reorder-capacity events, zero persistence failures, and an empty final backlog.

| Requested offered obs/s | Rep | Actual offered/s | Processed/s incl. drain | Persisted results/s incl. drain | Peak backlog | Backlog slope items/s | Drain s | Sustainable |
|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 25 | 1 | 25.030 | 24.948 | 47.234 | 39 | 0.054 | 0.099577 | YES |
| 50 | 1 | 49.290 | 48.499 | 91.728 | 113 | 0.175 | 0.496550 | YES |
| 50 | 2 | 50.027 | 49.649 | 93.902 | 55 | 0.047 | 0.228496 | YES |
| 50 | 3 | 50.019 | 49.653 | 93.911 | 67 | 0.130 | 0.220678 | YES |
| 75 | 1 | 74.659 | 73.350 | 138.550 | 175 | -0.055 | 0.537645 | YES |
| 75 | 2 | 75.002 | 74.107 | 139.980 | 100 | 0.117 | 0.362178 | YES |
| 75 | 3 | 74.956 | 73.826 | 139.448 | 137 | 0.095 | 0.459765 | YES |
| 100 | 1 | 98.320 | 86.851 | 164.149 | 1,065 | 16.402 | 4.029348 | **NO** |

The 100 obs/s point is a detected operating limit, not supported capacity. It did not drop work, but backlog grew, the source fell behind its requested clock, and processing p95 rose from 1,303.3882 ms in the early quarter to 7,194.0252 ms in the late quarter. It therefore fails the sustainable-rate rule.

The highest repeatedly demonstrated sustainable zero-drop point is 75 offered observations/s. The proposed target is one measured step lower: **50 offered observations/s**, a 25 obs/s nominal margin (33.3% below 75).

## Candidate target evidence

| Rep | Processing p50/p95/p99 ms | Persistence p50/p95/p99 ms | End-to-end evidence p50/p95/p99 ms | Peak backlog | Drain s |
|---:|---|---|---|---:|---:|
| 1 | 235.0961 / 1,044.8326 / 1,556.2789 | 0.7831 / 7.7715 / 54.3491 | 317.0692 / 1,182.3517 / 1,759.3116 | 113 | 0.496550 |
| 2 | 163.8731 / 873.2719 / 1,011.3130 | 0.8514 / 6.9360 / 50.7600 | 281.6051 / 962.8729 / 1,113.0840 | 55 | 0.228496 |
| 3 | 198.0280 / 873.0188 / 1,024.9503 | 0.9033 / 7.9604 / 57.7060 | 315.9587 / 1,002.2030 / 1,266.1127 | 67 | 0.220678 |

| Rep | RSS start | RSS peak | RSS final | RSS growth | State-entry peak | Reorder peak | SQLite final bytes |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 226,295,808 | 227,225,600 | 227,225,600 | 929,792 | 50 | 27 | 16,949,248 |
| 2 | 231,776,256 | 232,124,416 | 232,124,416 | 348,160 | 51 | 18 | 16,973,824 |
| 3 | 232,157,184 | 233,070,592 | 233,070,592 | 913,408 | 50 | 18 | 16,904,192 |

Candidate wording:

> On the measured development machine, the controlled MVP sustained a configured offered rate of 50 input observations/s for 30 seconds with zero input/runtime drops under the declared mixed workload.

The complete machine-readable evidence is in `benchmark_results/sustained_final_mvp_benchmark.json`; the dedicated rendering is in `SUSTAINED_FINAL_MVP_BENCHMARK_REPORT.md`.

## Candidate projection architecture

`SihAlertProjection` is a frozen, versioned presentation DTO produced by a pure function over one immutable `Result`. It has deterministic policy-scoped IDs, retains the exact source result ID, mechanism, claim ceiling, model references, governing IDs, quality, visibility, and evidence, and never writes back to the result or database.

The policy version is `SIH_ALERT_POLICY_V1_CANDIDATE`. “Alert” means **analyst-attention record**, not confirmed malicious activity. Multiple source results from one observation remain multiple projections. The candidate performs no cross-family fusion and creates no universal score.

The candidate `GET /alerts` endpoint is registered only when `EVIDENCEGATE_ENABLE_CANDIDATE_ALERTS=1` (or the equivalent explicit application constructor flag in tests). Its response is labelled `CANDIDATE_INACTIVE`. The endpoint is absent by default, `/results` remains the authoritative API, and `alert_policy_active` remains false. The dashboard keeps Evidence Results and adds a separate candidate SIH Alerts / Analyst Queue plus a separate system/quality status area when the opt-in surface is available.

## Result-to-projection admission matrix

| Immutable result type | Candidate output | Threat confidence? | Rationale |
|---|---|---|---|
| `REVIEW_FINDING` | Analyst evidence alert | Per mechanism below | Current admitted evidence requiring analyst review |
| `QUALITY_DEGRADED` | Quality notification | No | Sensor/evidence quality is not threat severity |
| `PREREQUISITE_MISSING` | Capability notification | No | Missing visibility/capability, not attack evidence |
| `INSUFFICIENT_EVIDENCE` | Evidence-status item | No | Insufficient evidence is not a low-confidence threat |
| `ANALYTIC_UNAVAILABLE` | System capability status | No | Unavailable analysis is not zero-confidence evidence |
| `PLUGIN_STATUS` | Plugin status | No | Operational status only |
| `THREAT_ALERT` | No candidate projection | No reinterpretation | Existing result semantics require a separate explicit policy |
| `CORRELATION_FINDING` | No candidate projection | No fusion | Cross-family fusion is out of scope |

## Threat taxonomy and confidence semantics

Threat class is an official SIH presentation taxonomy only; it does not prove the named attack.

| Family / mechanism | SIH presentation class | Confidence score | Mandatory basis | Meaning |
|---|---|---:|---|---|
| DDoS mechanisms | `DDOS` | null | `STATISTICAL_SUPPORT` | Factual/statistical support only |
| C2-R1 | `BOTNET_C2_BEACONING` | null | `STATISTICAL_SUPPORT` | Recurrence measurement support only |
| DGA-A1-M1 | `DGA` | Actual lexical score | `MODEL_SCORE` | DGA-labelled lexical resemblance; not calibrated attack probability |
| DNS-T1 | `DNS_TUNNELLING` | null | `OBSERVED_EVIDENCE` | DNS name-structure evidence only |
| ENC-A | `MALWARE_IN_ENCRYPTED_SESSION` | null | `OBSERVED_EVIDENCE` | Visible handshake evidence only; taxonomy mapping does not assert malware |
| Recon H/V/2D/TCP | `RECONNAISSANCE` | null | `STATISTICAL_SUPPORT` | Bounded factual breadth/geometry/TCP-state measurements |
| Exfil-M1 | `DATA_EXFILTRATION` | null | `OBSERVED_EVIDENCE` | Transfer-magnitude evidence only |

No numeric evidence-completeness value is implemented. Current manifests state admission prerequisites but do not define a mechanism-owned, objectively complete numerator/denominator contract for presentation confidence. Turning those lists into a percentage would manufacture precision. The candidate therefore uses a nullable numeric field plus a mandatory basis and supporting evidence.

## Severity and status priority

Alert severity is operational analyst priority, not scientific probability, maliciousness, damage, or impact. Under the smallest defensible candidate policy every admitted `REVIEW_FINDING` has severity `REVIEW`. There is no `HIGH`, `CRITICAL`, score-derived severity, or automatic cross-family elevation.

Non-threat status records use a separate priority field: `ATTENTION` for quality degradation, missing prerequisites, and unavailable capability; `INFO` for insufficient-evidence and plugin-status records. This priority never changes the separate quality field and never becomes threat severity.

## Remaining ambiguity and exact Human Gate

The official requirement can be represented truthfully as nullable `confidence_score` + mandatory `confidence_basis` + supporting evidence. If the official consumer requires a non-null number for every alert, the candidate cannot meet that narrower shape without inventing probabilities. The smallest scientifically safe change is for the official/demo schema to permit null numeric confidence for transparent mechanisms. A future numeric `EVIDENCE_COMPLETENESS` would require a new explicit per-mechanism manifest denominator and separate Human Gate; it is not inferred in M16.

Human approval is required for all four decisions:

1. Approve 50 offered input observations/s as the controlled SIH demo target on the measured development machine under this exact mixed workload.
2. Approve `SIH_ALERT_POLICY_V1_CANDIDATE` and its result-admission split.
3. Approve the mandatory confidence-basis semantics and nullable non-DGA numeric score.
4. Approve `REVIEW` as analyst priority for evidence alerts and the separate `INFO`/`ATTENTION` system-status priority.

Until that decision, the threat-alert policy is **not active**.

## Limitations

- Single development machine; no production, enterprise-sizing, or SLA inference.
- Deterministic typed load, not live capture or network line rate.
- Raw PCAP remains a separate characterization because DNS extraction is deferred and therefore cannot represent all seven implemented families.
- SSE subscriber notification loss is separate from runtime/input drop accounting.
- No live interface, NetFlow/IPFIX, or sFlow adapter is added.
- No scientific mechanism, representation, model, or mechanism threshold changed in M16.
