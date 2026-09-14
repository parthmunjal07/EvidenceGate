# Plugin Author Contract

As an author of an EvidenceGate analytic plugin, you are implementing the `AnalyticPlugin` protocol (`evidencegate.registry.plugin.AnalyticPlugin`). Your plugin is hosted within the shared runtime and must adhere strictly to the following contracts.

## 1. Plugin Manifest
You must define a static `PluginManifest` detailing your plugin's boundaries. This includes accepted observation types, routing predicates, state keys, and governance IDs. 

## 2. Purity and State
- **Stateless Routing**: Your `route()` method must be bounded, deterministic, and side-effect-free.
- **State Keys**: The `state_key()` method extracts an entity identifier (e.g., an IP address) used by the Runtime Supervisor to deterministically shard traffic. You cannot access global memory across shards.
- **Process Boundaries**: The `process()` method receives the injected state. You may mutate this local state, but you must not open external database connections, publish to external message buses, or block the event loop with synchronous I/O.

## 3. Governance and Allowed Results
Your plugin operates under a read-only `LaneGovernance` snapshot.
- If your lane is governed under `EVIDENCE_CONSTRUCTION` (e.g., a test scaffold), you are explicitly forbidden from emitting `ThreatAlert` results. The `ResultValidator` will aggressively reject these.
- You must only return `ResultDraft` sequences. The runtime will compile these into immutable SQLite records.

## 4. Quality Gaps, Abstentions, and Unavailability
The runtime forces you to explicitly distinguish between:
1. **Benign/No Threat**: Explicitly processed evidence resulting in no threat.
2. **Missing Prerequisites**: Data was missing to make a claim. Emit `PrerequisiteMissing`.
3. **Analytic Unavailable**: The lane is shut down by governance. Emit `AnalyticUnavailable`.
4. **Quality Gaps**: You may receive `on_quality_gap()` invocations if the upstream pipeline saturated or dropped packets.

**CRITICAL**: You must *never* silently translate a missing prerequisite or an unavailable analytic status into a "benign" result. The absence of a signal is not a signal of absence.
