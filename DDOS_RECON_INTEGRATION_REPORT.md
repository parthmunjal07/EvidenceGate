# DDoS + Recon Integration Report

Status: integration and regression complete; default activation remains human-gated.

This pass combines factual DDoS and Recon evidence construction. It does not
introduce attack detection, maliciousness or authorization inference, a family
score, confidence, severity, or `THREAT_ALERT` production.

## Integration record

| Item | Value |
|---|---|
| Main pre-merge head | `a89ad11d6f1966bfc1894043c5487998ce009f03` |
| Recon source | `2f605f0986fd23c235d4cf67b5f3d4ab782be557` (`parallel/recon-macro`) |
| Merge method | Clean cherry-pick |
| Cherry-picked commit on main | `625e12c` — `feat(recon): add bounded scan-activity evidence mechanisms` |
| Reconciliation commit | `b7e237d` — `fix(integration): reconcile recon with canonical packet contract` |
| Documentation commit | Commit containing this report |
| Conflicts | None |

The accepted DDoS history was preserved. The local Recon recovery branch was
not rebased, rewritten, deleted, or required on the remote.

## Contract reconciliation

### Packet protocol

Recon now requires `protocol` in `present_fields` and reads only
`PacketObservation.protocol`. TCP is accepted only as canonical IP protocol
number `6`. The old `observed_l4_facts["protocol"]` compatibility fallback and
its configurable lookup key were removed. Tests, replay fixtures, and the
capacity workload now declare `payload.protocol` explicitly. A regression test
proves that compatibility-only L4 metadata no longer routes.

### Direction and roles

Recon requires explicit `FORWARD` or `REVERSE` `wire_direction`. It orients
packet endpoints from that fact and then requires exactly one source-declared
`initiator_id` and `target_id` that agree with the oriented endpoints. It does
not infer roles from tuple position, address class, or ports. Flow protocol
semantics remain separate and unchanged.

## Consolidated implementation status

| DDoS mechanism | Status | Boundary |
|---|---|---|
| DDOS-A | IMPLEMENTED | Factual SYN/captured-state evidence |
| DDOS-B | IMPLEMENTED | Factual UDP demand measurement |
| DDOS-CV | IMPLEMENTED | Explicit victim-side reflection-shape facts |
| DDOS-CR | DEFERRED | Canonical paired transaction facts absent |
| DDOS-D | IMPLEMENTED | Bounded apparent-source diversity |
| DDOS-E1 | IMPLEMENTED | Factual ICMP demand measurement |
| DDOS-E2 | IMPLEMENTED | Explicit fragment facts |
| DDOS-E3 | IMPLEMENTED | Bounded initiating-TCP tuple measurement |
| DDOS-F | ANALYTIC_UNAVAILABLE | Trusted visible L7 telemetry absent |

| Recon mechanism | Status | Boundary |
|---|---|---|
| RECON-H | IMPLEMENTED | Horizontal host breadth and attempt count |
| RECON-V | IMPLEMENTED | Target-port breadth and attempt count |
| RECON-2D | IMPLEMENTED | Independent host, port, pair, and attempt counts |
| RECON-TCP | IMPLEMENTED | Captured SYN/SYN-ACK/RST/ACK progression facts |
| RECON-UDP | NOT IMPLEMENTED | No UDP attempt contract added in this pass |
| RECON-SLOW | CONTEXT_ONLY | Multi-horizon measurements only; no scan threshold |
| RECON-DIST | NOT IMPLEMENTED | No distributed-source fusion or attribution |
| RECON-B | NOT IMPLEMENTED | No family score, classifier, or inferred verdict |

## Regression and independence evidence

The mixed integration test sends canonical forward TCP SYN observations with
explicit trusted roles through one runtime. Each observation independently
selects all seven applicable targets:

- `ddos.syn_state` (`DDOS-A-B0`)
- `ddos.source_diversity` (`DDOS-D-B0`)
- `ddos.connection_churn` (`DDOS-E3-B0`)
- `recon.h` (`RECON-H`)
- `recon.v` (`RECON-V`)
- `recon.2d` (`RECON-2D`)
- `recon.tcp` (`RECON-TCP`)

Seven independent immutable mechanism result streams are produced. No top-1
selection or fused attack result exists. Every lane has a separate state store;
the test verifies DDoS stores contain only DDoS state payloads and Recon stores
contain only Recon payloads. No result ID appears in another result's evidence.
Previously emitted result IDs, evidence JSON, and state versions remain unchanged
after a later packet is processed.

The existing DDoS targeted suites pass unchanged. The existing active lanes
`c2.r1` (C2-R1), `dns_tunnelling.t1` (DNS-T1),
`encrypted_session.enc_a` (ENC-A), and `unusual_transfer.m1` (CAT6-EX-M1)
also pass unchanged.

## Boundedness audit

| Family/resource | Bound and saturation behavior |
|---|---|
| Recon state keys | Per-lane `StateStore.max_entries` from each manifest |
| Recon host/port/pair breadth | Derived from retained immutable events; event tuple is capped by `max_events_per_key` |
| Recon TCP attempt history | Immutable event tuple capped by `max_events_per_key` |
| Recon histories | Largest configured horizon plus `state_ttl`; capacity drops are counted and surfaced |
| DDoS SYN state | Per-lane state-entry cap; fixed-size payload |
| DDoS window state | Per-lane state-entry cap and fixed event-time window |
| DDoS source sets | `max_sources_per_window`; saturation becomes a quality-degraded lower bound |
| DDoS visible tuples | `max_attempts_per_window`; saturation becomes a quality-degraded lower bound |

Loss, sampling, capture gaps, parser degradation, reorder saturation, and state
saturation remain quality or visibility facts. None becomes a benign or attack
conclusion.

## Capacity evidence and candidates

### DDoS candidates — not approved

| Resource | Exact candidate |
|---|---:|
| DDOS-A state entries | 1,024 |
| DDOS-A reorder per key | 16 |
| DDOS-A reorder total | 2,048 |
| Window state entries per lane | 512 |
| Window reorder per key | 256 |
| Window reorder total per lane | 2,048 |
| Sources per reflection/diversity window | 256 |
| Visible tuples per connection-churn window | 256 |
| Measurement window | 1 second, measurement-only |

### Recon candidates — not approved

The integrated 1,024-observation boundary run used the exact candidate limits
below and produced 4,096 results, retained 1,600 state entries and 4,096 events,
reported no quality gaps or runtime errors, serialized 707,048 state bytes, and
reached a 5,704,927-byte tracemalloc peak.

| Resource | Exact candidate |
|---|---:|
| State entries per Recon lane | 1,024 |
| Retained events per key | 16 |
| Reorder events per key | 16 |
| Reorder events total per lane | 1,024 |
| State TTL | 3,600 seconds |
| Candidate measurement horizons | 60 and 3,600 seconds, measurement-only |

The historical/test horizons `10, 30, 60, 300, 900, 1800, 3600` seconds remain
experiment/configuration horizons. No horizon is promoted to a production scan
threshold.

## SQLite and validation

The mixed test writes DDoS and Recon results through the current SQLite schema
without migration and reads every result back equal to the finalized object.
It verifies mechanism ID, configuration hash, source observation IDs, quality
and visibility snapshots, state version, claim ceiling, and governing decision
ID. State version is nullable for a first transition by existing contract and is
retained exactly.

| Check | Result |
|---|---|
| DDoS + Recon focused integration | PASS |
| Required targeted groups | 314 passed |
| Full `pytest` | 356 passed, 0 failed |
| Default registry duplicate targets | None |
| Default stateful lane missing reorder policy | None |
| Static red-team review | Safe matches only: prohibitions, tests, and controlled measurements |
| SQLite mixed-family round trip | PASS |

## One consolidated activation gate — proposal only

Default activation is still gated. The proposed single human decision is:

1. Approve, reject, or revise the exact DDoS and Recon resource values above.
2. Approve the default-active factual subset `DDOS-A`, `DDOS-B`, `DDOS-CV`,
   `DDOS-D`, `DDOS-E1`, `DDOS-E2`, `DDOS-E3`, `RECON-H`, `RECON-V`,
   `RECON-2D`, and `RECON-TCP`.
3. If approved, replace the `ddos` and `recon` shells with these exact lane
   targets: `ddos.syn_state`, `ddos.udp_demand`, `ddos.reflection_victim`,
   `ddos.source_diversity`, `ddos.icmp_demand`, `ddos.fragment_demand`,
   `ddos.connection_churn`, `recon.h`, `recon.v`, `recon.2d`, and `recon.tcp`.
4. Preserve existing targets `c2.r1`, `dga`, `dns_tunnelling.t1`,
   `encrypted_session.enc_a`, and `unusual_transfer.m1` unchanged.
5. Keep DDOS-CR deferred, DDOS-F unavailable, and RECON-UDP/RECON-DIST/RECON-B
   unimplemented; keep RECON-SLOW context-only.

The one-second DDoS window and Recon horizons are aggregation/measurement
configuration, not attack or scan thresholds. Remaining scientific limitations
are lack of production threshold validation, FPR/TPR evidence, maliciousness or
authorization inference, victim-impact proof, source-authenticity proof,
distributed-Recon correlation, UDP-Recon semantics, and deployment-specific
capacity validation. Capture limitations continue to produce lower bounds.

No activation was performed in this integration pass.
