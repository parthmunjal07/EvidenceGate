# UI-05 Final Analyst Experience Report

## Scope

This pass updates the EvidenceGate presentation layer from the required local starting HEAD `0cf0a9deffc08b6613b1ac367c46341568bf0b58`. No backend, analytics, mechanism, threshold, model, router, persistence, or API/SSE contract code was changed. The backend product-surface tests were updated only where they asserted obsolete UI bundle copy.

## Analyst experience

- Primary navigation is Overview, Analyst queue, Evidence, and Traffic lab. System status is no longer a primary route.
- Mechanism IDs and SIH policy metadata are kept in Technical details. The primary tables use friendly categories, finding names, entities, and concise “Why surfaced” statements.
- The queue uses an investigation side panel. Evidence is shown before governance details; claim ceilings have explicit human-readable support and limitation text, with the original claim retained in the collapsed technical section.
- Entity and evidence formatters show known fields in readable form, suppress fixture tuple timestamps/direction noise, and keep raw values available under Technical details. Missing evidence and visibility/quality context remain visible.
- Overview summarizes current activity and capability limitations without the architecture diagram. Navigation returns to the top of the selected page.

## System health

The Online control opens a keyboard-accessible System health popover. Runtime state and capability readiness are shown separately. The current runtime is online; the DGA model is unavailable because its artifact is missing, so the UI reports one capability issue and 15 available analytics. Exact readiness/failure identifiers, policy, model references, and adapter names remain in System diagnostics.

## Traffic lab and processing trace

Traffic lab is described as controlled observation replay and recorded PCAP replay. It explicitly says it does not simulate a live network. Scenario groups use runtime source metadata; replay rate describes event-time spacing, not the visual trace pace. The DGA scenario remains visibly unavailable for lexical scoring and was not run.

Processing trace opens on demand in an accessible dialog. It groups only persisted output records that share source observation IDs. The trace animation is explanatory and does not represent processing latency; reduced-motion users see the final path immediately.

## Live scenario QA

| Scenario | Source | Records / observations | Persisted results |
| --- | --- | ---: | ---: |
| `mixed_ddos_recon` | NDJSON | 2 / 2 | 0 |
| `ddos_one_way` | NDJSON | 2 / 2 | 4 |
| `raw_pcap_ddos_recon` | PCAP | 11 / 11 | 0 |
| `dns_observation` | NDJSON | 1 / 1 | 2 |
| `ddos_udp` | NDJSON | 2 / 2 | 3 |
| `c2_recurrence` | NDJSON | 3 / 3 | 6 |
| `encrypted_session` | NDJSON | 1 / 1 | 1 |

The primary runtime’s paced C2 run completed in about 240 seconds. A clean temporary SQLite runtime was also used to capture the zero-to-many trace example: the same C2 fixture produced six persisted results from three observations at unpaced rate. That temporary server was stopped after capture. DGA was skipped because runtime readiness was `ARTIFACT_MISSING`; no score was fabricated.

## Verification

- `npm ci` completed; Node 22.20.0 emitted the project’s existing Node >=24.21.0 engine warning.
- `npm run typecheck` passed.
- `npm run lint` passed.
- `npm test -- --run` passed: 42 tests across 9 files.
- `npm run build` passed.
- `npm audit` reported 0 vulnerabilities.
- `pytest` passed: 440 tests.
- `python -m compileall -q evidencegate scripts` passed.
- `git diff --check` passed; Git reported only its existing LF/CRLF conversion notices.

The browser console showed one missing favicon request (404); no application page errors were observed.
