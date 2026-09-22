# EvidenceGate BENCHMARK REPORT v1

> **SUPERSEDED FOR FINAL THROUGHPUT CLAIMS.** This historical artifact used a
> dummy `BenchmarkPlugin`, in-memory SQLite, and intentional queue saturation.
> Its reported rate is invalid as current-stack or final throughput evidence.
> Use `scripts/benchmark_current_stack.py`,
> `benchmark_results/current_stack_real_benchmark.json`, and
> `CURRENT_STACK_REAL_BENCHMARK_REPORT.md` for the PRE-DGA current-MVP
> characterization. This file remains only as historical evidence.

This report outlines the performance and throughput ceilings of the EvidenceGate runtime MVP. 

## 1. Environment & Parameters
- **Python Version:** 3.14.7
- **Database:** SQLite In-Memory (`:memory:`) with `PRAGMA journal_mode=WAL`
- **Dependencies:** `fastapi`, `pydantic`, `psutil`
- **Configuration:** 
  - Lanes: 4 (simulating parallel concurrent analytic plugins)
  - Shards per Lane: 4 (yielding 16 total processing queues)
  - Queue Capacity: 100 per shard (backpressured / dropping after saturation)
  - Fixtures: 5,000 synthetic pre-allocated `NetworkObservationEnvelope` items.

## 2. Benchmark Results
*Executed on: 2026-09-14T19:12*

### Throughput & Scaling
- **Total Duration:** 0.292 seconds
- **Raw Ingest Replay Rate:** 17,152 operations/second
- **Total Persisted Results:** 800 
  *(Note: Due to the 100-item queue cap and the intentional saturation replay pacing, ~96% of routed events were actively rejected/dropped via `QueueFull` exceptions, successfully demonstrating the system's backpressure bounds).*

### Latency Profiles (ms)
- **Plugin Execution (`AnalyticPlugin.process()`):**
  - p50: 0.951 ms
  - p95: 2.418 ms
  - p99: 2.751 ms
- **Database Persistence (`SqliteWriter.write_result()`):**
  - p50: 0.021 ms
  - p95: 0.039 ms
  - p99: 0.054 ms

### System Health during Saturation
- **CPU Utilization:** 68.2% avg 
- **Memory (Peak RSS):** 33.2 MB
- **Event Loop Lag:** 5.606 ms avg

## 3. Explicit Limitations
1. **Security Tool Context:** This framework is purely a concurrent pipeline mechanism for dispatching observations to arbitrary algorithms. It is not a security tool and has no capability to detect threats.
2. **Scaffold Modeling:** The synthetic `BenchmarkPlugin` simulates execution using `asyncio.sleep(0)`. Real AI/analytic workloads will drastically inflate the plugin p50/p95 times.
3. **In-Memory SQLite:** Testing utilized an in-memory SQLite database to explicitly measure serialization overhead of WAL concurrency. Real-world disk-backed WAL SQLite writes will increase persistence latency proportionally to the disk hardware's IOPS.
4. **Ingest Parsing & Lane Dispatch:** Ingest parsing latency and concurrent lane dispatch queuing are explicitly measured above, demonstrating the baseline overhead before plugin execution.
5. **Saturation Dropping:** Replay rates intentionally overwhelmed the tiny `100` max-size queues to simulate a traffic spike. In real implementations, capacities and shard distributions must be tuned to the network throughput curve to avoid dropping.
