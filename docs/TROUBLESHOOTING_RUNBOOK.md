# Troubleshooting Runbook

This guide covers common operational anomalies in the EvidenceGate runtime.

## 1. Queue Saturation (QualityGap Generation)
**Symptom**: `QueueFull` exceptions logged, high memory usage, and `QualityGap` records appearing with `reason="Shard queue full"`.
**Cause**: The ingestion rate (e.g., a burst of packets) has exceeded the processing speed of the analytic plugins in a specific lane, causing the 100-item shard queue to saturate.
**Mitigation**:
- The runtime will automatically drop saturated items to protect memory and emit a `QualityGap`.
- Investigate the specific `AnalyticPlugin.process()` hook for blocking operations or unexpected algorithmic complexity.
- Do not increase queue sizes to hide slow analytics.

## 2. Scaffold Validator Rejections
**Symptom**: `ValueError: ThreatAlert cannot be emitted from a scaffold` in logs.
**Cause**: A developer has attempted to emit a production `ThreatAlert` from a lane governed under `EVIDENCE_CONSTRUCTION`.
**Mitigation**: 
- Scaffolds must only emit `ReviewFinding` or `AnalyticUnavailable`.
- Ensure the lane is fully approved for `PRODUCTION` status in `LaneGovernance` before running active threat models.

## 3. WebSocket Feed Freezing
**Symptom**: The UI real-time feed stops updating, but the SQLite database continues growing.
**Cause**: The UI client is processing WebSocket frames too slowly, triggering the server's slow-client protection mechanism (dropping updates).
**Mitigation**:
- Have the UI fall back to `GET /results?cursor=X` to fetch missing data.
- Optimize client-side rendering.

## 4. SQLite "Database is Locked" Errors
**Symptom**: `sqlite3.OperationalError: database is locked`.
**Cause**: External processes are modifying the SQLite file outside of WAL concurrency boundaries, or a host OS bug exists with WAL reset signaling.
**Mitigation**:
- Ensure no external process is opening the DB in write mode.
- In extreme cases, a specific `pysqlite3-binary` wheel might be required if the host OS SQLite is drastically outdated.
