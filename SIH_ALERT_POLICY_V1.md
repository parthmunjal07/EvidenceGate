# SIH Alert Policy V1

Decision `MVP-DEC-FINAL-ALERT-THROUGHPUT-V1`, approved by Rachit / Control Room
on 2026-09-23, promotes the M16 candidate to `SIH_ALERT_POLICY_V1`.
This document defines the active controlled MVP presentation policy.

## Authority and meaning

`Result → pure versioned projection → analyst alert or status record`.
An alert is an **analyst-attention record**. It does not confirm an attack,
malware, compromise, exfiltration, intent, or maliciousness. Immutable persisted
Results and `GET /results/{result_id}` remain scientific authority. The
query-time `GET /alerts` view never writes a projection back to Result or to a
second alert store. The dashboard shows the newest 500 source Results in the
queue; this is a bounded current view, not a lifetime alert count.

## Admission

| Immutable Result type | V1 projection | Priority |
|---|---|---|
| `REVIEW_FINDING` | Analyst threat-evidence alert | `severity=REVIEW` |
| `QUALITY_DEGRADED` | Quality status | `priority=ATTENTION` |
| `PREREQUISITE_MISSING` | Capability status | `priority=ATTENTION` |
| `ANALYTIC_UNAVAILABLE` | System capability status | `priority=ATTENTION` |
| `INSUFFICIENT_EVIDENCE` | Evidence status | `priority=INFO` |
| `PLUGIN_STATUS` | Plugin/system status | `priority=INFO` |
| `THREAT_ALERT`, `CORRELATION_FINDING` | No V1 projection | — |

`REVIEW` orders analyst attention only; it does not encode probability, impact,
damage, business risk, or maliciousness. Status `priority` is a separate field.
Quality remains a separate snapshot and never increases threat severity.

## Taxonomy and confidence

| EvidenceGate lane | Official SIH presentation class | Confidence basis | Numeric score |
|---|---|---|---|
| `ddos.*` | `DDOS` | `STATISTICAL_SUPPORT` | null |
| `c2.*` | `BOTNET_C2_BEACONING` | `STATISTICAL_SUPPORT` | null |
| `dga.m1` | `DGA` | `MODEL_SCORE` | actual `dga_labelled_lexical_resemblance_score` |
| `dns_tunnelling.*` | `DNS_TUNNELLING` | `OBSERVED_EVIDENCE` | null |
| `encrypted_session.*` | `MALWARE_IN_ENCRYPTED_SESSION` | `OBSERVED_EVIDENCE` | null |
| `recon.*` | `RECONNAISSANCE` | `STATISTICAL_SUPPORT` | null |
| `unusual_transfer.*` | `DATA_EXFILTRATION` | `OBSERVED_EVIDENCE` | null |

Every alert has `confidence_basis` and a statement. The DGA number is
DGA-labelled lexical resemblance, **not calibrated attack probability**.
No non-DGA mechanism defines a numeric attack probability. DDoS measurements,
C2 recurrence, DNS structure, ENC-A handshake/fingerprint facts, Recon
breadth/geometry/TCP facts, and transfer magnitude retain their own factual
meaning. The encrypted-session taxonomy label does not establish malware; the
exfiltration label does not establish theft or sensitive content.

## Provenance and independence

Each projection retains the source Result ID, exact claim ceiling, mechanism,
evidence, visibility, quality, model references where applicable, governing
IDs, and parser/quality/provenance references. The deterministic identifier is
derived from the policy version, source Result ID, and record kind. Repeating
projection or refreshing REST produces the same record. Promotion from the M16
candidate intentionally changes the policy-scoped ID.

One observation can yield zero to many independent Results and thus independent
alert/status records. DGA and DNS-T1, or DDoS and Recon, are never fused into a
global score or shared conclusion. Each record preserves its own claim ceiling.

`GET /alerts` and the analyst dashboard are enabled by default. The optional
development switch `EVIDENCEGATE_DISABLE_ALERTS=1` disables the endpoint.
