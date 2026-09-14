# EvidenceGate BENCHMARK PLAN v1

This document outlines the reproducible methodology for evaluating the pure baseline throughput and latency ceilings of the EvidenceGate runtime infrastructure (Prompt 4).

## 1. Methodology and Constraints
- **Scope:** Runtime infrastructure only. No scientific models, thresholds, or parsers are evaluated.
- **Fixture Generation:** The script uses a synthetic pre-allocated pool of `NetworkObservationEnvelope` payloads to avoid memory-allocation overheads polluting the measurement.
- **Persistence:** An in-memory SQLite database (`:memory:`) in WAL mode is used.
- **Concurrency Setup:**
  - 4 configured concurrent lanes (plugins).
  - 4 shards per lane.
  - Replay pacing operates in tight burst loops, measuring unconstrained queue saturation and backpressure recovery.
- **Reporting Mechanism:** A background `psutil` task captures CPU %, RSS memory, and asyncio event-loop lag every 100ms.

## 2. Measurement Definitions

### Rate Measurements
- **Input Rate:** Number of observations generated and ingested per second.
- **Routed Rate:** Observations successfully matching the `RelevanceRouter` index.
- **Admitted Rate:** Observations passing the `AdmissionEvaluator`.
- **Processed Rate:** Observations fully yielded by the `AnalyticPlugin.process()` boundary.
- **Dropped Rate:** Observations hitting `QueueFull` and skipped (measured via `QueueSaturation` counts).

### Queue Metrics
- **Queue Depth & Saturation:** Measured instantaneously via `asyncio.Queue.qsize()`. Saturation triggers `QualityGap` tracking.
- **Oldest Age:** The delta between the current wall clock and the `ingest_time` of the oldest item popped off the queue.

### Latency Profiles (p50/p95/p99)
- **Plugin Latency:** The execution time strictly spanning `AnalyticPlugin.process()`.
- **Persistence Latency:** The await time of `SqliteWriter.write_result()`.
- **End-to-End Latency:** The wall-clock delta between `causal_available_time` of the source payload and the successful `sqlite.commit()` of the corresponding `Result`.

### System Health
- **Memory/RSS:** Tracked via `psutil.Process().memory_info().rss`.
- **State Count:** Instantaneous size of the `StateStore` dictionaries.
- **CPU & Event Loop Lag:** CPU tracked via `psutil.cpu_percent()`. Event loop lag is measured by scheduling a zero-sleep task and calculating the deviation from the expected wake time.

## 3. Execution Script
The benchmark logic will be located in `scripts/benchmark.py` and run via the project's `.venv`. No capacities or counts are hardcoded into the core implementation contract (e.g., shard configuration is parameterized).
