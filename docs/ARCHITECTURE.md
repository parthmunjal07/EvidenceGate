# Architecture

EvidenceGate processes recorded observations and makes the evidence contract visible across ingestion, analytics, storage, and the analyst interface.

```text
Typed / NDJSON replay or offline classic PCAP
        ↓
Parse and canonicalize once
        ↓
Visibility, quality, timestamp and identity
        ↓
Shared facts → zero-to-many analytic providers
        ↓
Independent, validated Results
        ↓
Family evidence → deterministic factual relations
        ↓
SQLite, REST/SSE and analyst workbench
```

## Implemented path

### Inputs and canonical observations

The current adapters accept typed observations and NDJSON replay, and read offline classic PCAP with Ethernet link type. The PCAP adapter yields packet observations incrementally and can use an explicit sidecar manifest for direction, roles, service, and related capture facts. Those facts are part of the replay contract; the sensor does not independently discover them. The runtime does not capture a live interface, consume NetFlow/IPFIX/sFlow, or extract DNS observations from raw PCAP.

Canonical observation types include packet, flow, DNS, TLS, and QUIC observations. The envelope carries source/observation identity, event time, direction and visibility, quality, and provenance needed by providers. Missing reverse direction, partial handshakes, loss, sampling, and midstream captures remain explicit limitations. See the domain and ingestion modules for the executable schema.

### Shared facts and routing

The router matches an observation to zero or more registered mechanisms. Shared parsing and facts feed independent providers; DDoS and reconnaissance are not mutually exclusive labels. Providers validate their accepted observation types and required quality before producing evidence. Stateful C2 recurrence uses bounded history and a strict `FLOW_START` event basis; it requires canonical event time to match flow start and explicit stable client, peer, and service-role identity. Unsupported or incomplete prerequisites reduce evidence or yield an unavailable result according to the provider contract.

### Results and family views

Each provider emits an independent immutable `Result` with its mechanism, observation basis, scientific status, evidence, and limitations. Result validation/finalization protects allowed result semantics. `ANALYTIC_UNAVAILABLE` is distinct from an empty finding: the analytic could not produce an observed finding under its contract.

Family evidence is a read-only composition over Results. Deterministic investigation links use factual relations such as shared source-observation identity across independent results. They help an analyst inspect related evidence; they do not assert causality, a common attacker, campaign, progression, or a combined threat probability. A learned relevance ranker was researched and not promoted.

### CORR-04A exact-observation foundation

The correlation foundation stores typed, versioned facts as derived records. It does not add them to the canonical Result payload or change existing Result IDs and hashes. A Result write and its correlation outbox intent share one SQLite transaction. A restart-safe background worker materializes exact source_observation_id facts and retrieves matches through a composite SQLite index.

The enabled relation is EXACT_OBSERVATION: it produces a deterministic candidate for two exact Result IDs in distinct known families. Candidates retain both source hashes, matched fact IDs and observation provenance, event-time relationship, visibility, quality, derivation/policy versions, and a fixed typed claim guard. /correlation/candidates exposes these precise pairs. The existing /investigations family-view response remains unchanged for current clients and retains its family-view aggregation semantics.

Typed schemas exist for scoped entity, peer, domain, observed DNS answer, service, session, and target-service facts, but current materialization emits exact-observation facts only. Protocol context, raw IP equality, and time proximity are not standalone join keys. DNS-to-TLS peer, C2-to-transfer, and reconnaissance-to-demand policies remain disabled with no configured time windows. No learned ranking or causal/attack-chain inference is implemented. This is a persistence and deterministic retrieval foundation, not a validated cross-event correlation system.

### State, persistence and interfaces

Stateful providers keep bounded, provider-specific state. The current replay service exposes an allowlisted scenario catalogue rather than arbitrary filesystem paths or URLs. Results and replay records persist in SQLite. The FastAPI service exposes health, replay, results, family evidence, investigation, and related analyst APIs; server-sent events can publish result updates. The frontend presents the evidence and its limitations, with family views and a versioned attention queue. Queue priority is a presentation decision, not a scientific verdict.

## Implemented and deferred

| Capability | Status | Boundary |
|---|---|---|
| Typed/NDJSON replay | Implemented | Structured input, not a live feed |
| Offline classic Ethernet PCAP replay | Implemented | Replay facts/sidecar may supply direction and roles; PCAP DNS extraction is deferred |
| Six threat areas, including separate DDoS mechanisms | Implemented | Evidence mechanisms only; family-specific claim ceilings apply |
| Bounded C2 recurrence | Implemented | Requires trusted, canonical flow-start timing and explicit identity |
| DGA lexical model | Implemented when exact artifact is available | Controlled MVP; fail-closed otherwise |
| SQLite persistence, REST/SSE, analyst workbench | Implemented | Single-process prototype architecture |
| Family evidence and factual investigation links | Implemented | No learned correlation or causal inference |
| CORR-04A typed exact-observation fact and Result-pair foundation | Implemented | Versioned derived records; existing family-view API retained |
| Cross-event relation policies and DNS answer coverage | Disabled / deferred | No temporal windows; raw-PCAP DNS extraction remains deferred |
| Live NIC capture; NetFlow/IPFIX/sFlow | Deferred | Not in current runtime |
| DNS extraction from raw PCAP | Deferred | DGA/DNS demo uses typed replay observations |
| Distributed state/execution and production capacity sizing | Deferred | Current measurements do not establish production readiness |
| Learned cross-family correlation | Not promoted | Insufficient defensible independent packet-derived multi-family truth |
| Semantic exfiltration model | Not admitted | Authorization and sensitivity truth are missing |

## Performance evidence boundary

`benchmark_results/final_mvp_acceptance.json` records one controlled development acceptance run: after a separate three-second warmup, 1,500 typed observations were offered at 50 observations/second for 30 seconds, accepted and processed, with zero drops/control errors, and the queue drained in about 0.202 seconds. The recorded environment was Windows 11, Python 3.13.7, Intel i5-13450HX, 18 logical/14 physical cores, 16.6 GB RAM, with 16 registered targets and the DGA artifact active. This is one workload and one acceptance replicate. It is not an SLA, production capacity claim, or general throughput guarantee.
