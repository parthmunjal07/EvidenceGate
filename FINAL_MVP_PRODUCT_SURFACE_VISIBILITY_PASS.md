# Final MVP Product Surface / Architecture Visibility Pass

## Product changes

- Overview now presents the current service and latest replay counters, a compact runtime progression, six threat-family decomposition cards, and a separate measured development benchmark.
- Traffic Lab extends its runtime path from source records through canonical observations, visibility, zero-to-many mechanism routing, readiness, immutable Results, family composition, and factual investigation links.
- Analyst Queue remains family-first and places family review below the full-width episode list. Related links open the dedicated Investigations page.
- Investigations presents each exact shared-observation relation as two family evidence episodes with its joint-investigation-only claim guard.
- Evidence uses the full available table width. Selecting a row opens a centered modal sized to 78% of the desktop viewport; it closes with Escape or the backdrop.
- The primary navigation is Overview, Traffic Lab, Analyst Queue, Investigations, and Evidence. The implementation matrix now records these demo surfaces and the limits of live performance telemetry.

## Telemetry and benchmark basis

The live API exposes runtime registration, durable Result count, replay state, records read, observations emitted, persisted Results, elapsed replay time, and bounded presentation trace events. It does not expose live processing percentiles, end-to-end evidence latency, current active-state entries, queue depth, or a live drop counter. The Overview labels those measures as unavailable instead of deriving proxy values.

The historical card is derived from the three 50 observations/s, 30-second runs in `benchmark_results/sustained_final_mvp_benchmark.json` (captured 2026-09-23). The displayed latency percentiles are medians across those runs: processing 198 / 873 / 1,025 ms (p50 / p95 / p99), and end-to-end evidence 316 / 1,002 / 1,266 ms. Each run recorded zero input/runtime drops. The card reports the highest measured RSS, 233.1 MB. It is labeled as a controlled development benchmark, not production capacity or an SLA.

## Replay QA

Each scenario was replayed once against a temporary SQLite database and a separate local API process.

| Scenario | Records / observations | Persisted Results | Family views | Investigation links |
| --- | ---: | ---: | ---: | ---: |
| `mixed_ddos_recon` | 2 / 2 | 8 | 2: DDoS, Reconnaissance | 1 |
| `dga_lexical` | 1 / 1 | 2 | 1: DGA + DNS | 0 |
| `c2_recurrence` | 3 / 3 | 6 | 4: C2 / Beaconing and Data Transfer | 3 |
| `ddos_one_way` | 2 / 2 | 4 | 1: DDoS, retaining the missing reverse-evidence limitation | 0 |

All four completed. The replay Results and family views remained separate from cross-family investigation links.

## Checks

- Backend: `python -m pytest -q` — 451 tests passed (exit code 0).
- Frontend: typecheck passed; ESLint passed; 48 tests passed; production build passed.
- Isolated preview server: HTTP 200 for the app, `/health`, and `/runtime` through the Vite proxy.
- Scientific mechanisms, thresholds, readiness, routing, model behavior, and immutable Result semantics were not changed.

## Screenshot review

I could not complete the requested screenshot capture and visual inspection in this environment. The computer-use browser inventory returned no apps or browsers, and both the in-app browser and Chrome surface were unavailable. No screenshots are included in this pass; the pages were verified through frontend tests, the production build, and isolated replay/API checks.
