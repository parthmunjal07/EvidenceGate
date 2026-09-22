# DDoS MVP Macro Implementation and Capacity Report

Status: implementation and controlled characterization complete; default activation remains gated.

> **This pass validates deterministic passive evidence construction and bounded runtime mechanics. It does not establish production DDoS accuracy, production FPR, victim resource exhaustion, spoofing, or malicious intent.**

## Scope classification

| Branch | Classification | Result |
|---|---|---|
| DDOS-A-B0 SYN/state | IMPLEMENTED | Existing semantics preserved unchanged |
| DDOS-B-B0 UDP demand | IMPLEMENTED / MEASUREMENT ONLY | Event-time packet and `lengths["ip"]` measurements |
| DDOS-CV-B0 victim reflection shape | IMPLEMENTED / MEASUREMENT ONLY | Requires `DDOS_REFLECTION_FACT_V1` source facts |
| DDOS-CR-B0 reflector transaction | DEFERRED | Canonical transaction identity, request/response role, and paired byte facts are absent |
| DDOS-D-B0 apparent source diversity | IMPLEMENTED / MEASUREMENT ONLY | Exact bounded source set and lower-bound saturation semantics |
| DDOS-E1-B0 ICMP demand | IMPLEMENTED / MEASUREMENT ONLY | Explicit protocol 1 only |
| DDOS-E2-B0 fragment demand | IMPLEMENTED / MEASUREMENT ONLY | Requires `DDOS_FRAGMENT_FACT_V1` source facts |
| DDOS-E3-B0 connection churn | IMPLEMENTED / MEASUREMENT ONLY | Forward TCP initiating SYN facts and bounded visible tuples |
| DDOS-F-B0 L7 | ANALYTIC UNAVAILABLE | No visible/trusted canonical L7 telemetry |
| Historical rate/non-completion cutoffs | REJECTED | Not used as detector logic |
| Universal family detector, score, or ML | REJECTED | Not implemented |

The named final DDoS package and reference-engine files were not present in this checkout. Semantic parity was therefore checked against the supplied frozen Control Room contract and existing DDOS-A behavior; executable cross-run parity against `ddos_engine_core.py` was not possible.

## Implemented contracts

All mechanisms require explicit canonical protocol, known packet direction, `PACKET_FACTS`, and exactly one trusted `target_id` and `service_id`. No target, service, or direction is derived from endpoint position.

Packet length uses only the repository-established `lengths["ip"]` convention. Missing length preserves packet count, reports byte count as unavailable, and never zero-fills unknown bytes.

Windows are UTC-aligned, end-exclusive, event-time windows closed by runtime watermark expiry. The one-second window is `POC_OR_EXPERIMENT_ONLY`, `science_admitted=false`, and controls aggregation only.

Victim reflection requires all exact source facts:

- `fact_contract = DDOS_REFLECTION_FACT_V1`
- `response_like = true`
- a non-empty `protocol_context`
- protocol 17, explicit `FORWARD` victim-bound direction, and explicit target/service roles

Fragment demand requires `fact_contract = DDOS_FRAGMENT_FACT_V1`, `is_fragment = true`, and typed optional offset/more-fragments facts. Merely supplying a fragmentation dictionary does not route.

## One-way and quality matrix

| Mechanism | BOTH | FORWARD only | REVERSE only | Loss/sampling |
|---|---|---|---|---|
| DDOS-A | Captured state progression or controlled incomplete evidence | SYN arrival survives; reverse completion unavailable causes abstention | Midstream reverse state is insufficient evidence | Completion/incomplete claims degrade |
| DDOS-B | Directional UDP measurement | AVAILABLE for observed forward side | AVAILABLE for observed reverse side | Count/bytes are explicit lower bounds |
| DDOS-CV | AVAILABLE only with explicit victim facts | AVAILABLE with explicit forward victim contract | NOT APPLICABLE under current victim-side contract | Shape counts become lower bounds |
| DDOS-D | Direction-scoped apparent cardinality | AVAILABLE for observed forward side | AVAILABLE for observed reverse side | Cardinality may undercount and is marked lower bound |
| DDOS-E1 | Directional ICMP measurement | AVAILABLE | AVAILABLE | Count/bytes become lower bounds |
| DDOS-E2 | Directional fragment measurement | AVAILABLE | AVAILABLE | Count/bytes become lower bounds |
| DDOS-E3 | Forward initiating attempts only | AVAILABLE | NOT APPLICABLE | Attempt/tuple counts become lower bounds |

Controlled 10% loss, 30% loss, and 0.5 sampling projections produced observed counts of 9, 7, and 5 from a 10-packet baseline. Every transformed measurement was `QUALITY_DEGRADED`; absence was never strengthened into a benign conclusion.

## Boundedness audit

| Mechanism | State-key bound | Payload bound |
|---|---|---|
| DDOS-A | Constructor-supplied `max_state_entries` | Fixed-size attempt state; bounded causal IDs |
| DDOS-B | Constructor-supplied `max_state_entries` | Fixed counters, length statistics, first/last IDs |
| DDOS-CV | Constructor-supplied `max_state_entries` | Fixed counters plus `max_sources_per_window` |
| DDOS-D | Constructor-supplied `max_state_entries` | Exact set capped by `max_sources_per_window` |
| DDOS-E1 | Constructor-supplied `max_state_entries` | Fixed counters, length statistics, first/last IDs |
| DDOS-E2 | Constructor-supplied `max_state_entries` | Fixed counters, length statistics, first/last IDs |
| DDOS-E3 | Constructor-supplied `max_state_entries` | Exact tuple set capped by `max_attempts_per_window` |

At exact-set capacity, a new distinct value is not retained, the retained cardinality remains a truthful lower bound, `capacity_reached=true`, and the window emits `QUALITY_DEGRADED`. No random eviction occurs.

## Controlled capacity characterization

Artifact: `benchmark_results/ddos_mvp_capacity_characterization.json`.

The benchmark used the real `ReplayRunner`, `RuntimeSupervisor`, `StateStore`, `EventTimeReorderPolicy`, result finalization, and `SqliteWriter`. Rates are local controlled measurements, not final project throughput or production sizing.

### DDOS-A concurrent active tuple sweep

| Active tuples | State payload | Approx. bytes/entry | Tracemalloc peak | Processed results/s | Reorder occupancy | Quality gaps |
|---:|---:|---:|---:|---:|---:|---:|
| 32 | 0.05 MiB | 1,639 | 0.25 MiB | 252.0 | 32 | 0 |
| 128 | 0.20 MiB | 1,622 | 0.73 MiB | 258.8 | 128 | 0 |
| 512 | 0.79 MiB | 1,619 | 2.32 MiB | 244.8 | 512 | 0 |
| 1,024 | 1.58 MiB | 1,618 | 5.51 MiB | 230.7 | 1,024 | 0 |
| 2,048 | 3.16 MiB | 1,619 | 7.81 MiB | 214.1 | 2,048 | 0 |
| 4,096 | 6.33 MiB | 1,621 | 17.02 MiB | 209.5 | 4,096 | 0 |

At 4,096 tuples the measured offered submission rate was 3,313.5 observations/s. Successfully processed and persisted result rate was 209.5/s. Ingress submission latency was p50 0.157 ms, p95 0.347 ms, and p99 1.273 ms. SQLite persistence is included, so this is intentionally not a pure plugin microbenchmark.

### Window mechanisms at 512 concurrent keys

| Mechanism | Approx. bytes/entry | Tracemalloc peak | Processed and persisted results/s | Quality gaps |
|---|---:|---:|---:|---:|
| DDOS-B-B0 | 1,491 | 1.79 MiB | 198.8 | 0 |
| DDOS-CV-B0 | 1,605 | 1.84 MiB | 201.9 | 0 |
| DDOS-D-B0 | 1,598 | 1.83 MiB | 208.4 | 0 |
| DDOS-E1-B0 | 1,492 | 1.75 MiB | 208.5 | 0 |
| DDOS-E2-B0 | 1,499 | 2.03 MiB | 208.1 | 0 |
| DDOS-E3-B0 | 1,628 | 1.93 MiB | 200.6 | 0 |

### Internal exact-set and reorder boundaries

| Resource | Controlled result |
|---|---|
| Source set | Capacity 256; 257 offered; 256 retained; ~18,447 bytes for the state; `QUALITY_DEGRADED` lower bound |
| Visible-tuple set | Capacity 256; 257 offered; 256 retained; ~25,875 bytes for the state; `QUALITY_DEGRADED` lower bound |
| DDOS-A same-key reorder | Capacity 16; 17 offered; 16 retained; one quality gap; boundary effective |
| Many-key reorder | 4,096 retained under an explicit test total bound of 4,104; no quality gaps |

## Reference semantic parity

Preserved reference concepts:

- five-second DDOS-A POC TTL;
- one-second demand-measurement window;
- normalized visible TCP endpoints;
- factual UDP, source-diversity, ICMP, fragment, and initiating-attempt measurements.

Intentional EvidenceGate differences:

- trusted roles and explicit direction instead of positional inference;
- watermark closure instead of wall-clock evaluation;
- explicit missing evidence and quality lower bounds;
- exact sets with visible engineering caps;
- no simplistic string prefix derivation;
- no missing-reply semantics, family score, or threat verdict;
- DDOS-CR deferred until canonical paired transaction fields exist.

## SQLite and zero-to-many

Every implemented window mechanism was finalized and round-tripped through SQLite v3 with mechanism ID, configuration hash, bounded source observation IDs, state version, claim ceiling, governing decision ID, quality/visibility snapshot, and evidence unchanged.

One explicit UDP response-shaped packet independently routes to DDOS-B, DDOS-CV, and DDOS-D. One initiating TCP SYN independently routes to DDOS-A, DDOS-D, and DDOS-E3. No plugin consumes another plugin's result and no family fusion exists.

## Consolidated Human-Gate table

| Mechanism | Implemented? | Scientific status | Window/TTL | State key | Payload bound | Tested clean capacity | One-way/quality | Default candidate? | Unresolved decision |
|---|---|---|---|---|---|---|---|---|---|
| DDOS-A | Yes | Evidence construction | 5 s POC TTL | target × service × normalized tuple × protocol | Fixed | 4,096 tuples | Existing conservative semantics | Yes | State/reorder limits |
| DDOS-B | Yes | Measurement only | 1 s POC | target × service × direction × window | Fixed | 512 keys | Directional; lower-bound on degradation | Yes | Window/state/reorder limits |
| DDOS-CV | Yes | Measurement only | 1 s POC | target × service × direction × window × context | Sources capped | 512 keys | Forward victim contract only | Yes | Source/state/reorder limits |
| DDOS-CR | No | Deferred | N/A | N/A | N/A | N/A | Canonical transaction facts absent | No | Add explicit canonical transaction contract |
| DDOS-D | Yes | Measurement only | 1 s POC | target × service × direction × window | Sources capped | 512 keys | Directional lower bound | Yes | Source/state/reorder limits |
| DDOS-E1 | Yes | Measurement only | 1 s POC | target × service × direction × window | Fixed | 512 keys | Directional lower bound | Yes | State/reorder limits |
| DDOS-E2 | Yes | Measurement only | 1 s POC | target × service × direction × window × protocol | Fixed | 512 keys | Directional lower bound | Yes | State/reorder limits |
| DDOS-E3 | Yes | Measurement only | 1 s POC | target × service × direction × window | Tuples capped | 512 keys | Forward initiating facts | Yes | Tuple/state/reorder limits |
| DDOS-F | No | Analytic unavailable | N/A | N/A | N/A | N/A | L7 telemetry absent | No | Canonical trusted L7 telemetry |

## Candidate engineering values — not approved

| Parameter | Candidate | Evidence and implication |
|---|---:|---|
| DDOS-A `max_state_entries` | 1,024 | Clean; ~1.58 MiB retained payload and 5.51 MiB benchmark peak |
| DDOS-A reorder per key | 16 | Boundary tested; the 17th same-key event creates a quality gap |
| DDOS-A reorder total | 2,048 | Clean many-key occupancy measured at 2,048; limits burst retention |
| Window `max_state_entries` per lane | 512 | Every implemented window mechanism clean at 512 keys |
| Window reorder per key | 256 | Supports a controlled 256-observation hot window; overflow must degrade measurement |
| Window reorder total per lane | 2,048 | Allows several concurrent hot keys while bounding memory |
| Reflection/diversity sources per window | 256 | Exact boundary and lower-bound saturation behavior measured |
| Connection-churn tuples per window | 256 | Exact boundary and lower-bound saturation behavior measured |
| Measurement window | 1 second | SUPPORT as controlled MVP measurement window only; not science admission |

Window alternatives are 500 ms (lower state/reorder occupancy, more results and boundary sensitivity) and 2 seconds (fewer results, higher state/set/reorder occupancy). The one-second reference value is the least-divergent controlled candidate.

## Prepared activation plan — not executed

After one Human-Gate decision, construct explicit registry entries for the approved subset of:

`ddos.syn_state`, `ddos.udp_demand`, `ddos.reflection_victim`, `ddos.source_diversity`, `ddos.icmp_demand`, `ddos.fragment_demand`, and `ddos.connection_churn`, each with its approved state and reorder policy. Remove or retain the `ddos` shell only as the decision specifies. Do not register DDOS-CR or DDOS-F.

The current default registry remains unchanged: `ddos -> DdosShellPlugin`.

## Verification

- DDoS, replay, event-time, lifecycle, gap/quality, C2, DNS-T1, ENC-A,
  CAT6-EX-M1, provider/registry, persistence, finalization, and invariant tests:
  PASS.
- Full suite: **333 passed, 0 failed**.
- `git diff --check`: PASS.
- `THREAT_ALERT`: none.
- Universal score/probability/ML: none.

## Consolidated Human-Gate question

Approve, reject, or revise the candidate table as one controlled-MVP engineering decision, including the one-second measurement window and the exact mechanism subset to activate. This approval would govern runtime resources and activation only; it would not admit DDoS detection science or authorize `THREAT_ALERT`.
