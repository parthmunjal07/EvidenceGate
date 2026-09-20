# Persistence Reference

EvidenceGate’s SQLite repository stores only finalized immutable `Result` objects. It validates that `result_id` equals the M5-01 canonical identity before beginning a write, then stores the matching SHA-256 content digest alongside structured v2 result fields.

Writes are a single transaction covering the result parent and its ordered evidence, provenance, quality, governing, prerequisite, and correlation-link children. A duplicate ID is a no-op only when its stored content hash matches. A different or hashless legacy row raises `ResultIdentityConflict` without mutation.

Connections enable WAL, foreign keys, and `synchronous=NORMAL`. Schema migration 2 is additive and idempotent: it upgrades v1 databases without resetting rows, assigns deterministic positions to legacy children, and records version 2 once in `schema_migrations`.

`get_result(result_id)` reconstructs the exact v2 final subtype; legacy hashless rows deliberately raise a clear legacy-read limitation. `list_results()` supports bounded (1–1000) cursor pagination and optional lane/type filters. Ordering is `created_time DESC, result_id DESC`; cursors encode the final pair and avoid offset instability.

No HTTP, WebSocket, or other API surface is implemented by this persistence loop.
