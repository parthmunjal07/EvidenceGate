# DDoS + Recon Default Activation Closure Report

## Decision and revision

- Human-gate decision: `DDOS-RECON-DEC-MVP-ACTIVATION-V1` — ACCEPTED
- Owner: Rachit / Control Room
- Pre-activation head: `1a7c0e48d0440a24ee9f2497c2a0b4ae82d4eab0`
- Activation implementation head: `01fc41da28f62c2f508e96aba237019101265c89`
- Scope: configuration and default activation only; no scientific mechanism,
  threshold, claim-ceiling, or persistence-schema change

## Exact default registry

The default registry contains exactly 16 unique targets:

1. `ddos.syn_state`
2. `ddos.udp_demand`
3. `ddos.reflection_victim`
4. `ddos.source_diversity`
5. `ddos.icmp_demand`
6. `ddos.fragment_demand`
7. `ddos.connection_churn`
8. `c2.r1`
9. `dga`
10. `dns_tunnelling.t1`
11. `encrypted_session.enc_a`
12. `recon.h`
13. `recon.v`
14. `recon.2d`
15. `recon.tcp`
16. `unusual_transfer.m1`

`ddos` and `recon` shells remain available in source for compatibility but are
absent from the default registry. DGA remains a shell. C2-R1, DNS-T1, ENC-A, and
CAT6-EX-M1 remain active and unchanged.

## Controlled-MVP capacity and configuration

| Mechanism group | State | Retained/set bound | Reorder per key | Reorder lane-wide | Time contract |
|---|---:|---:|---:|---:|---|
| DDOS-A-B0 | 1024 | — | 16 | 2048 | 5s controlled reference/POC expiry |
| DDoS window lanes | 512/lane | 256 sources for CV/D; 256 attempts for E3 | 256 | 2048/lane | 1s event-time measurement window |
| Recon H/V/2D/TCP | 1024/lane | 16 events/key | 16 | 1024/lane | 3600s TTL; 60s + 3600s horizons |

All values are controlled-MVP engineering or measurement configuration. They are
not production sizing, attack thresholds, scan thresholds, or maliciousness
policy. C2 continues to use its independent `C2-DEC-MVP-CAPACITY-V1` authority.
Every DDoS/Recon stateful lane has its own explicit reorder-policy instance.

## Configurations and canonical hashes

- DDOS-A `DdosASynConfig.reference_poc_v1()`:
  `sha256:cc20711fc66a4b13c7b26229e58cb551d97a5e7d48ef2961a6a344f37309e62e`
- DDoS one-second reference POC window configs:
  `sha256:3a52a7a8c1b036bda84c23c1953da25d4eb3ae47a2109eb972097d43fa257639`
- Recon `ReconConfig.controlled_mvp_v1()`:
  `sha256:74987e85154c9e44d6fdb852b89ea3e3200cacc52e4c6d9f6ebb7ee6b5a058d9`

Recon hash tests establish deterministic equality for identical executable
inputs and invariance under a `config_id`-only rename.

## Governance and provenance

All activated lanes use `EVIDENCE_CONSTRUCTION`, their existing manifest result
types, and their exact existing mechanism claim ceilings. DDoS governance phases
are lane-specific factual SYN/state, UDP demand, victim reflection-shape,
apparent-source distribution, ICMP demand, fragment demand, and TCP
initiating-attempt measurement. Recon phases are horizontal breadth, target-port
breadth, host × port geometry, and captured TCP probing-state measurement.

Every activated DDoS/Recon manifest and finalized result contains
`DDOS-RECON-DEC-MVP-ACTIVATION-V1`. No `ThreatAlert`, confidence, severity,
probability, score, family verdict, or ML reference was introduced.

## Verification evidence

- Default TCP replay: one explicit forward TCP SYN with trusted `target_id`,
  `service_id`, and `initiator_id` selected seven independent lanes:
  DDOS-A, DDOS-D, DDOS-E3, RECON-H, RECON-V, RECON-2D, and RECON-TCP.
- Default UDP replay: one explicit UDP observation selected DDOS-B and DDOS-D;
  the exact `DDOS_REFLECTION_FACT_V1` contract also selected DDOS-CV.
- SQLite: both default mixed replays passed through `ReplayRunner`,
  `RuntimeSupervisor`, and `SqliteWriter`; full immutable result equality passed
  after readback, including mechanism/config/provenance/source/quality/visibility/
  state-version/claim-ceiling fields. No schema migration was added.
- Capacity boundaries: DDoS source and attempt sets retain 256 values and expose
  lower-bound degradation on the 257th distinct value. Recon retains 16 events
  and exposes `capacity_truncated`, a dropped count, and
  `OBSERVED_LOWER_BOUND` on event 17.
- Window behavior: existing tests continue to prove one-second DDoS closure by
  event-time/watermark and Recon 60/3600-second event-time horizon behavior.
- One-way behavior: DDOS-A forward-only SYN evidence and Recon forward-only
  breadth remain visible as lower bounds; reverse-only evidence does not
  reconstruct forward probing breadth.
- Quality behavior: loss, sampling, capture/parser gaps, state/payload capacity,
  and reorder saturation remain quality degradation, lower-bound evidence, or
  insufficient evidence—not benign/malicious verdicts.
- Active-lane regression: C2-R1, DNS-T1, ENC-A, CAT6-EX-M1, and the DGA shell pass
  unchanged.

Targeted regression: **244 passed, 0 failed**.

Full regression: **365 passed, 0 failed**.

`python -m compileall -q evidencegate scripts`: PASS.

`git diff --check`: PASS.

## Limitations retained

- DDOS-CR remains deferred because canonical paired transaction identity and
  paired byte facts are absent.
- DDOS-F remains analytically unavailable because trusted canonical L7 telemetry
  is absent.
- RECON-UDP, RECON-DIST, and RECON-B remain unimplemented.
- RECON-SLOW is not a separate lane; approved multi-horizon observation remains
  represented by the H/V/2D state.
- DGA remains a shell pending its separate frozen-model integration gate.
- The runtime makes no victim exhaustion, spoofing, botnet, attacker attribution,
  authorization, maliciousness, or confirmed-attack claim.

## Closure

Category 1 DDoS MVP: **CLOSED for the current approved scope**.

Category 5 Recon MVP: **CLOSED for the current approved scope**.

Human gate required: **NO**.

Next: **DO NOT START. Await Control Room review.**
