# API and Persistence Reference

## FastAPI and WebSocket Endpoints

EvidenceGate exposes generic REST and WebSocket endpoints for reading results.

### `GET /results`
Provides durable cursor-based polling for historical and active `Result` records.
- **Use case**: Reliable UI dashboards and asynchronous metric aggregation.

### `WS /live`
Provides an ephemeral real-time feed of analytic updates.
- **Slow Client Protection**: The WebSocket endpoint utilizes a bounded `asyncio.Queue` per client. If a client is too slow to process messages, the queue will saturate (`QueueFull`), and the server will **silently drop real-time updates** for that client.
- **Recovery**: Slow clients must rely on durable cursor queries (`GET /results`) to recover dropped sequences.

## SQLite Persistence

The runtime uses an application-owned SQLite writer bound to a single thread.

### WAL Mode
The database operates in **WAL (Write-Ahead Logging)** mode (`PRAGMA journal_mode=WAL`). This permits multiple concurrent readers (e.g., UI queries) without blocking the primary writer thread.

### Idempotence and Replay
- The `SqliteWriter` executes writes using `INSERT OR IGNORE`.
- Because observations and results are immutable (IC-11), replays of historical PCAP data will seamlessly skip duplicate `result_id` keys without crashing or corrupting the database.

### Partial Commits
- The `SqliteWriter.write_result` method wraps the parent `Result` and its associated `evidence_items` and `missing_prerequisites` in a single atomic transaction. 
- If the parent `Result` is ignored (duplicate), the child relationships are aggressively skipped to maintain referential integrity.
