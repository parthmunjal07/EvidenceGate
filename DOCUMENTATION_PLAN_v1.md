# EvidenceGate DOCUMENTATION PLAN v1

This plan maps out the required operational and reference documentation for the EvidenceGate Runtime MVP to satisfy the Implementation Contract. 

## Documentation Strategy

### 1. Nomenclature & Precision
All documentation must strictly observe the vocabulary bounds defined by the architecture:
- **Observation:** Immutable factual records mapped from physical network traffic (e.g., a packet or flow) via a `Canonicalizer`. Not yet subjected to analytics.
- **Evidence:** Cryptographically or causally linked observations that have been processed and cited by an `AnalyticPlugin`.
- **Analytic Status:** Operational boundaries related to the lifecycle of the analytic model (e.g., `ANALYTIC_UNAVAILABLE`, `EVIDENCE_CONSTRUCTION`).
- **Operational Health:** The physical throughput and hardware boundaries of the system (e.g., queue saturation, Quality Gaps).
- **Threat Claims:** Outputs formally categorized as `ThreatAlert`.
- **Scaffold Rules:** A scaffold plugin exists to test the pipeline. **It is not a detector**, and it has no accuracy, true positive rate, or scientific backing. 

### 2. Output Artifacts

1. **`README.md`**: Core entrypoint. Exposes setup, run, and test instructions, alongside a mandatory dependency and license inventory, and the explicit scientific no-go boundaries.
2. **`docs/ARCHITECTURE_AND_DATA_FLOW.md`**: Outlines the progression of an observation into evidence through routing, admission, and analytic processing.
3. **`docs/PLUGIN_AUTHOR_CONTRACT.md`**: A developer guide on writing conforming implementations of `AnalyticPlugin`, understanding `LaneGovernance`, and handling edge cases like missing prerequisites or abstentions.
4. **`docs/API_AND_PERSISTENCE.md`**: Reference for the generic endpoints, handling WebSocket disconnections (durable cursors), and SQLite WAL-mode concurrency notes.
5. **`docs/TROUBLESHOOTING_RUNBOOK.md`**: Mitigation runbooks for queue saturation, WAL lockups, and unhandled analytic exceptions.

*No performance or accuracy numbers will be invented in these documents. Throughput ceilings will strictly reference the reproducible ceilings verified in `BENCHMARK_REPORT.md`.*
