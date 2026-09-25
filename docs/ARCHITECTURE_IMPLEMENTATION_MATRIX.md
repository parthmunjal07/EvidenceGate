# Architecture implementation matrix

This matrix separates the implemented MVP runtime from proposed system architecture. The demo surfaces only the implemented rows marked **Implemented**.

| Architecture element | Implementation status | Demo surface |
| --- | --- | --- |
| Passive source input | **Implemented** for typed NDJSON replay and offline raw PCAP replay | Traffic Lab source panel and live source counters |
| Parse once into canonical observations | **Implemented** through source canonicalizers and the shared observation contract | Traffic Lab live observation feed |
| Observation visibility and quality | **Implemented** as explicit visibility and quality facts; lane admission checks its declared requirements | Runtime trace visibility stage and evidence detail |
| Zero-to-many analytic routing | **Implemented** through deterministic per-observation routing plans | Eligible analytics branches in Traffic Lab |
| Mechanism-owned readiness and bounded state | **Implemented** where a mechanism reports readiness; stateless analytics can be ready on an observation | Per-analytic readiness labels in Traffic Lab |
| Independent immutable Results | **Implemented** and persisted in SQLite; `/results` remains authoritative | New Evidence feed and Evidence Results page |
| Analyst-facing family projection | **Implemented** as a presentation projection over immutable Results | Analyst Queue |
| Missing prerequisite evidence | **Implemented** when a persisted Result records missing prerequisites or a limitation | Limitation result in New Evidence and the analyst detail view |
| Live interface capture | **Deferred** | Not presented as active |
| NetFlow, IPFIX, or sFlow ingestion | **Deferred** | Not presented as active |
| Cross-observation correlation ML | **Proposed / deferred** | Not presented as active |
| Distributed multi-host processing | **Proposed / deferred** | Not presented as active |

Runtime trace telemetry is presentation-only, bounded in memory, and best effort. It does not replace persisted Results or change routing, readiness, analytic, or persistence semantics.
