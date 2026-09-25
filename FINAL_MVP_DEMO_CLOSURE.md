# SIH26145 MVP runtime demo closure

**QA date:** 2026-09-26
**Starting revision:** `66cdb3eaa3737f7ba6453c15140105de080424c0`
**Scientific changes:** None. The persisted Result schema, routing predicates, thresholds, model training, claim ceilings, and replay semantics are unchanged.

## Runtime trace contract

- Traffic Lab readiness is indexed by the exact `observation_id + lane_id` pair. Readiness for one observation cannot be applied to a later observation on the same lane.
- On `RUNNING → COMPLETED`, Traffic Lab fetches once more from the last trace cursor. Trace events merge by monotonic sequence, so a poll/final-drain race does not duplicate events.
- `RESULT_PERSISTED` carries the Result's complete `source_observation_ids` list. It does not use a single observation ID to imply exclusive causality.
- Traffic Lab uses the fetched Result's complete source observation list for its lineage label, so multi-observation Results are shown as evidence from multiple observations.
- `/runtime/trace` is a best-effort presentation feed, held in a bounded 500-event ring buffer. Sink failure or trace loss cannot affect replay processing.
- SQLite-backed `/results` remains the scientific authority. The persisted Result schema is unchanged; SSE and trace remain presentation/notification surfaces.

## Restored DGA M1-R1 artifact

| Check | Verified value |
| --- | --- |
| Artifact | `DGA_M1_R1_SERIALIZED_MODEL.joblib` |
| Runtime path | `artifacts/dga/local/DGA_M1_R1_SERIALIZED_MODEL.joblib` |
| Bytes | `5,720,970` |
| SHA-256 | `39da209d2cfd869dd284e10b8a07adc04826c95146712cc6854a69b9873890df` |
| Model | `DGA-A1-M1-R1` |
| Representation | `DGA_M1_REPRESENTATION_v1` |
| Classes / positive class | `['benign', 'dga']` / `dga` at index `1` |
| Runtime readiness | `VERIFIED_READY` when started with `EVIDENCEGATE_DGA_MODEL` set to the path above |
| Git state | Model is ignored and untracked; manifest remains tracked |

The live `dga_lexical` replay produced a DGA lexical resemblance score of `0.9851716132182514`. Its Analyst Queue projection uses `MODEL_SCORE` and says it is not a calibrated attack probability. The DGA and DNS T1 Results remain independent.

## Live replay QA

Each scenario completed with no runtime error. Counts below are source records (PCAP rows are packets), canonical observations, readiness events, and persisted Results from the live service harness.

| Scenario | Records | Observations | Routed lanes | Readiness events | Results | Result types / notes |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `mixed_ddos_recon` | 2 | 2 | 7 | 7 | 8 | Review findings and insufficient evidence |
| `ddos_one_way` | 2 | 2 | 4 | 5 | 4 | Includes insufficient evidence with missing reverse TCP state |
| `ddos_udp` | 2 | 2 | 3 | 3 | 3 | Review findings |
| `c2_recurrence` | 3 | 3 | 2 | 6 | 6 | Two stateful Results have multi-observation lineage; one cites all 3 source observations |
| `dga_lexical` | 1 | 1 | 2 | 2 | 2 | Independent DGA M1 and DNS T1 review Results; live model score |
| `dns_observation` | 1 | 1 | 2 | 2 | 2 | DGA lane routed but this domain representation is unavailable; DNS T1 Result remains independent |
| `encrypted_session` | 1 | 1 | 1 | 1 | 1 | Review finding |
| `transfer_magnitude` | 1 | 1 | 1 | 1 | 1 | Review finding |
| `raw_pcap_ddos_recon` | 11 packets | 11 | 10 | 42 | 35 | Offline PCAP replay and independent DDoS/Recon Results |

The one-way SYN replay explicitly reports missing reverse TCP state and returns an insufficient-evidence Result. It does not infer a benign peer, no attack, or a completed connection. The DNS/DGA zero-to-many case produced two independent routes and two separate Results from one DNS observation. C2 stateful readiness came from mechanism runtime telemetry; the frontend does not derive a threshold.

## Architecture and demo

The architecture matrix marks typed NDJSON and offline PCAP replay, parse/canonicalize once, visibility and quality facts, zero-to-many routing, mechanism readiness, bounded state, immutable Results, analyst projection, missing evidence, REST, SSE, and bounded trace as implemented. Live interface capture, NetFlow/IPFIX/sFlow, learned correlation, and distributed multi-host processing remain deferred.

The judge-ready 105-second script is in [FINAL_MVP_DEMO_SCRIPT.md](FINAL_MVP_DEMO_SCRIPT.md). The implementation matrix is [docs/ARCHITECTURE_IMPLEMENTATION_MATRIX.md](docs/ARCHITECTURE_IMPLEMENTATION_MATRIX.md).

## Verification results

- Frontend: `npm ci` passed in an isolated frontend QA copy; `npm run typecheck`, `npm run lint`, `npm test -- --run` (46 tests), and `npm run build` passed. `npm audit` reported 0 vulnerabilities. The built static bundle was refreshed in the repository.
- Backend: `python -m pytest -q` — 444 passed.
- `python -m compileall -q evidencegate scripts` — passed.
- `git diff --check` — passed.
- Screenshot QA — unavailable; no browser was exposed in the computer-use inventory. Source, automated tests, and live replay QA completed.

The installed Node version is 22.20.0 while `frontend/package.json` declares Node `>=24.21.0`. Frontend checks passed on the available version, with npm's engine warning. A workspace `npm ci` attempt could not replace a Rolldown native binary locked by the running dev server; the lockfile install and checks succeeded in the isolated QA copy, and the workspace dependency files were restored without stopping that server.

## Deferred scope

- Live interface capture
- NetFlow/IPFIX/sFlow ingestion
- Learned correlation
- Distributed multi-host processing
