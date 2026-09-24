# Persistence Reference

EvidenceGate's SQLite repository stores only runtime-finalized, immutable `Result` objects. Schema version 3 adds the evidence-result contract required before mechanism analytics: a runtime-owned mechanism ID, canonical structured evidence, source observation and source IDs, factual quality and visibility snapshots, the state snapshot version, and optional config/parser/model provenance.

`ResultDraft.evidence` is a JSON-shaped object containing factual mechanism measurements. Finalization converts it to `EvidencePayload`, whose only stored representation is deterministic canonical JSON. Object keys are sorted; enums and timezone-aware datetimes have stable representations; non-string keys, non-finite numbers, naive datetimes, and arbitrary Python objects are rejected. The final result never retains the draft's mutable dictionary.

Runtime finalization injects `mechanism_id` from `PluginManifest`, the triggering observation and source IDs, exact `EvidenceQuality` and `VisibilityProfile` snapshots, state version when a keyed state snapshot was read, and any explicitly available config/parser/model references. It continues to inject analytic and governance versions and the governance-owned claim ceiling. Plugins cannot set those runtime-owned fields. Additional causal observation IDs may be declared by a mechanism draft when they come from retained causal state.

Canonical v3 identity includes all structured evidence and provenance above. Consequently, changing a measurement, mechanism, causal observation, source, quality fact, visibility fact, state version, or optional provenance changes `result_id`. Processing time is deferred as operational metadata: no wall-clock timestamp is introduced into deterministic scientific identity. `created_time` remains the explicitly supplied causal result time.

Writes use one transaction for the result parent and ordered child rows. Source observation IDs, source IDs, parser references, and model references have explicit positions; evidence is stored in one canonical JSON column. Duplicate IDs are no-ops only when the stored SHA-256 semantic-content hash matches. A changed or unverifiable payload raises `ResultIdentityConflict`; there is no `INSERT OR IGNORE` path.

Migration 3 is additive and idempotent. Databases already at version 2 keep every row, result ID, content hash, and scientific field unchanged. New columns remain `NULL` and new child tables remain empty for legacy v2 rows because mechanism evidence and provenance cannot be reconstructed truthfully. Canonical v2 identity remains version-aware and unchanged, while all newly finalized results use schema `3.0`.

Connections enable WAL, foreign keys, and `synchronous=NORMAL`. `get_result(result_id)` reconstructs exact v2 or v3 final subtypes; hashless v1 rows retain the existing explicit read limitation. `list_results()` supports bounded cursor pagination, lane, mechanism, result-type, source, and created-time filters. The HTTP limit is 1-500.

## Product API

`create_app(database)` owns the SQLite connection through the FastAPI lifespan,
so importing the module does not open a connection and tests can supply a
temporary database. The same application serves the static dashboard; no broad
CORS policy is enabled.

`GET /results` returns typed Pydantic DTOs without exposing Python dataclass
internals. Normal pages are ordered by `(created_time, result_id)` descending.
`next_cursor` continues toward older rows. `sync_cursor` is an `after.` cursor;
passing it back through the same `cursor` parameter returns later durable rows in
ascending order. Both forms encode an exact durable `(created_time, result_id)`
boundary, not an offset or list index. Invalid cursors are rejected with a typed
422 response.

`GET /events` is a one-way Server-Sent Events notification stream. Each browser
has an independent bounded queue. The runtime callback first commits a finalized
result to SQLite and only then broadcasts its lightweight ID/time/lane/mechanism/
type hint. On subscriber overflow, notification hints are discarded and a
`stream_gap` event requests REST resynchronization; the durable result and
runtime processing are unaffected.

`POST /replay` selects a bundled fixture by an explicit scenario ID. Arbitrary
paths, URLs, and extra request fields are rejected. One replay may run at a time.
`GET /replay/status` reports only measured lifecycle values, while `GET /runtime`
reports the exact 16-lane registration, DGA shell state, family readiness,
database state, subscriber count, replay state, and available scenario metadata.

`GET /alerts` is active by default under `SIH_ALERT_POLICY_V1`. It projects up
to the newest 500 immutable Results at query time into separate analyst alerts
and system/evidence status records. It has no independent alert table. An alert
is an analyst-attention record, not a confirmed attack. Each record carries its
source Result ID for lookup through `GET /results/{result_id}`. `/results`
remains the scientific authority; `/alerts` is versioned SIH analyst
presentation. The dashboard exposes both views and keeps status outside the
analyst alert count. Numeric confidence is nullable: only DGA carries its
actual lexical model score; other mechanisms carry a mandatory factual basis.
`EVIDENCEGATE_DISABLE_ALERTS=1` is an optional development opt-out.
