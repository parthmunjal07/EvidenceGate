# Architecture implementation matrix

This matrix separates the implemented MVP runtime from proposed system architecture. The demo surfaces only the implemented rows marked **Implemented**.

| Architecture element | Implementation status | Demo surface |
| --- | --- | --- |
| Passive source input | **Implemented** for typed NDJSON replay and offline raw PCAP replay | Traffic Lab source panel and live source counters |
| Parse once into canonical observations | **Implemented** through source canonicalizers and the shared observation contract; bounded safe summaries show source facts alongside canonical facts | Traffic Lab Network Observations and source-to-canonical workbench |
| Observation visibility and quality | **Implemented** as explicit visibility and quality facts; lane admission checks its declared requirements | Observation detail, runtime stage, and evidence detail |
| Zero-to-many analytic routing | **Implemented** through deterministic per-observation routing plans, including retained observations with no eligible routes | Per-row route counts and independent route list in Traffic Lab |
| Mechanism-owned readiness and bounded state | **Implemented** where a mechanism reports readiness; stateless analytics can be ready on an observation | Per-analytic readiness labels in Traffic Lab |
| Independent immutable Results | **Implemented** and persisted in SQLite; `/results` remains authoritative | Full-width Evidence table and on-demand Result modal |
| Family Evidence Composer | **Implemented** as deterministic same-family connected components over exact source-observation lineage; no numeric fusion | Analyst Queue and Traffic Lab family stage |
| Factual Relation Index | **Implemented** as an inverted source-observation index over family views | Dedicated Investigations page and Traffic Lab relation stage |
| Deterministic investigation links | **Implemented** for exact shared source observations across different official families; joint investigation only | Dedicated two-family relationship view |
| ML relevance ranker | **Deferred / not promoted** | Not presented as active |
| Attack-chain reconstruction | **Deferred / not claimed** | Not presented as active |
| Missing prerequisite evidence | **Implemented** when a persisted Result records missing prerequisites or a limitation | Limitation result in New Evidence and the analyst detail view |
| REST result retrieval | **Implemented** through `/results`; persisted SQLite Results remain the scientific authority | Evidence Results page |
| Server-sent result notifications | **Implemented** as hints followed by REST retrieval of the durable Result | Live New Evidence updates |
| Bounded runtime trace | **Implemented** with 5,000 backend-retained events and a 500-event frontend presentation buffer; both are in-memory, best effort, and cannot change persisted Results | Traffic Lab runtime stages |
| Family-first analyst review | **Implemented** as one queue row per composed family view, with independent findings and limitations preserved | Analyst Queue |
| Live performance telemetry | **Partially exposed**: replay records, observations, elapsed time, and durable Result count are available; live processing percentiles, end-to-end latency, queue depth, and state footprint are not | Overview labels unavailable live measures as not exposed |
| Governed benchmark display | **Implemented** from `benchmark_results/sustained_final_mvp_benchmark.json`; shown separately from live runtime state and labeled development-only | Overview measured benchmark card |
| Curated judge replay assets | **Implemented** as five deterministic runtime-owned NDJSON/PCAP bundles; internal fixtures require the explicit development toggle | Traffic Lab picker |
| Railway single-host deployment | **Implemented** with Docker build, `/health` deploy check, SQLite and the verified DGA artifact on a persistent volume | Public-but-unlisted judge URL |
| Private model locator handling | **Implemented**: only model ID and SHA-256 are included in public Result provenance; Drive locators and local paths are filtered | Result API and evidence detail |
| Live interface capture | **Deferred** | Not presented as active |
| NetFlow, IPFIX, or sFlow ingestion | **Deferred** | Not presented as active |
| Distributed multi-host processing | **Proposed / deferred** | Not presented as active |

Runtime trace telemetry is presentation-only, bounded in memory, and best effort. The backend retains up to 5,000 events; the frontend's active presentation merge retains up to 500 events. A pre-replay baseline reads `latest_sequence` from a one-event trace request and then polls forward from that sequence. `RESULT_PERSISTED` carries the Result's full source observation lineage and its Result ID; playback reveals the durable Result at this trace event, while lineage remains attribution only. The source and canonical observation projections are whitelist-only, omit raw payloads and internal references, and fail open if projection fails. Trace events do not replace persisted Results or change routing, readiness, analytic, or persistence semantics. SQLite-backed `/results` remains authoritative if the trace is dropped or truncated.

Railway runs one application process with SQLite and the private serialized DGA model on the same persistent volume. Live interface capture, NetFlow/IPFIX/sFlow, raw-PCAP DNS parsing, learned correlation, distributed execution, and production throughput sizing remain deferred.
