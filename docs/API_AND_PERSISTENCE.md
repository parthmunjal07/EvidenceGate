# Persistence Reference

EvidenceGate's SQLite repository stores only runtime-finalized, immutable `Result` objects. Schema version 3 adds the evidence-result contract required before mechanism analytics: a runtime-owned mechanism ID, canonical structured evidence, source observation and source IDs, factual quality and visibility snapshots, the state snapshot version, and optional config/parser/model provenance.

`ResultDraft.evidence` is a JSON-shaped object containing factual mechanism measurements. Finalization converts it to `EvidencePayload`, whose only stored representation is deterministic canonical JSON. Object keys are sorted; enums and timezone-aware datetimes have stable representations; non-string keys, non-finite numbers, naive datetimes, and arbitrary Python objects are rejected. The final result never retains the draft's mutable dictionary.

Runtime finalization injects `mechanism_id` from `PluginManifest`, the triggering observation and source IDs, exact `EvidenceQuality` and `VisibilityProfile` snapshots, state version when a keyed state snapshot was read, and any explicitly available config/parser/model references. It continues to inject analytic and governance versions and the governance-owned claim ceiling. Plugins cannot set those runtime-owned fields. Additional causal observation IDs may be declared by a mechanism draft when they come from retained causal state.

Canonical v3 identity includes all structured evidence and provenance above. Consequently, changing a measurement, mechanism, causal observation, source, quality fact, visibility fact, state version, or optional provenance changes `result_id`. Processing time is deferred as operational metadata: no wall-clock timestamp is introduced into deterministic scientific identity. `created_time` remains the explicitly supplied causal result time.

Writes use one transaction for the result parent and ordered child rows. Source observation IDs, source IDs, parser references, and model references have explicit positions; evidence is stored in one canonical JSON column. Duplicate IDs are no-ops only when the stored SHA-256 semantic-content hash matches. A changed or unverifiable payload raises `ResultIdentityConflict`; there is no `INSERT OR IGNORE` path.

Migration 3 is additive and idempotent. Databases already at version 2 keep every row, result ID, content hash, and scientific field unchanged. New columns remain `NULL` and new child tables remain empty for legacy v2 rows because mechanism evidence and provenance cannot be reconstructed truthfully. Canonical v2 identity remains version-aware and unchanged, while all newly finalized results use schema `3.0`.

Connections enable WAL, foreign keys, and `synchronous=NORMAL`. `get_result(result_id)` reconstructs exact v2 or v3 final subtypes; hashless v1 rows retain the existing explicit read limitation. `list_results()` supports bounded (1-1000) cursor pagination and optional lane/type filters, ordered by `created_time DESC, result_id DESC`.

No HTTP, WebSocket, or other API surface is changed by this persistence loop.
