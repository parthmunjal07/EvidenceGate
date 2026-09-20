# Plugin Author Contract

An EvidenceGate analytic plugin implements `evidencegate.registry.plugin.AnalyticPlugin` inside the shared runtime.

## Manifest and mechanism identity

Define a static `PluginManifest` with the plugin boundary: accepted observation types, routing predicates, state keys, governance IDs, and versions. A plugin that emits any result must declare a non-empty `mechanism_id`. Structural provider shells may omit it only while they remain result-free.

## Purity and state

- `route()` must be bounded, deterministic, and side-effect-free.
- `state_key()` extracts the identifier used for deterministic sharding; plugins cannot access global cross-shard memory.
- `process()` receives a defensive, versioned state snapshot. It may calculate one declarative transition but must not mutate runtime state, open external database connections, publish to message buses, or block the event loop with synchronous I/O.
- A stateful result records the exact version of the snapshot read. Stateless evaluation uses `None`, never a fabricated version zero.

## Result drafts and factual evidence

Plugins return `ResultDraft` values only. `ResultDraft.evidence` is a JSON-shaped object for factual measurements, such as interval counts, observed bytes, peer identifiers, or record-shape facts. It is not a generic score, confidence value, or verdict channel. Values may be strings, integers, finite floats, booleans, nulls, arrays, and nested string-keyed objects. Unsupported objects, `NaN`, and infinity are rejected.

A draft may name additional `source_observation_ids` only when they are causal observations retained in mechanism state. It must not invent IDs or refer to future observations. The runtime always adds the triggering observation ID during normal processing.

Plugins do not own or set `plugin_id`, `mechanism_id`, plugin/analytic/governance versions, taxonomy, claim ceiling, source IDs, quality, visibility, state version, or config/parser/model provenance. The runtime injects these facts from the manifest, governance snapshot, observation, and state boundary. Finalization deep-freezes evidence into canonical `EvidencePayload`; later mutation of draft input cannot alter the final result.

## Governance and allowed results

The runtime validates every finalized result against a read-only `LaneGovernance` snapshot. A lane governed under `EVIDENCE_CONSTRUCTION` or analytic unavailability cannot emit `ThreatAlert`. Plugins may emit only explicitly allowed result types, and only the runtime supplies the governance-owned claim ceiling.

## Quality, visibility, and unavailable evidence

The runtime preserves the triggering observation's exact `EvidenceQuality` and `VisibilityProfile`, along with quality and provenance references. Plugins must not reinterpret unavailable or degraded sensor facts as observed zeros or benign evidence.

Distinguish explicitly between:

1. Evidence supporting no finding.
2. Missing prerequisites, represented by `missing_prerequisites` and an appropriate result type.
3. Analytic unavailability governed by lane status.
4. Quality gaps delivered through lifecycle callbacks.

Absence of a signal is not evidence of absence. Lifecycle results may carry only provenance genuinely available from their causal state or watermark context; no visibility, quality, source, parser, model, or config facts may be fabricated.
