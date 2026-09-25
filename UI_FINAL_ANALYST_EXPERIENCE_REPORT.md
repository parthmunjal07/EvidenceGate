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

## Screenshot review

Screenshots were captured after the final frontend build. Main views were reviewed at 1440×900, 1366×768, and 1920×1080. The set includes overview, queue, selected DDoS investigation, evidence, selected result, health popover, diagnostics drawer, Traffic lab idle/running/completed, and processing trace, including the zero-to-many example.

Screenshots are in [`screenshots/ui05`](screenshots/ui05/):

- [Overview, 1440×900](screenshots/ui05/overview-1440x900.png)
- [Analyst queue with selected DDoS item, 1440×900](screenshots/ui05/analyst-queue-selected-ddos-1440x900.png)
- [Evidence with selected result, 1440×900](screenshots/ui05/evidence-selected-result-1440x900.png)
- [System health popover, 1440×900](screenshots/ui05/system-health-popover-1440x900.png)
- [System diagnostics, 1440×900](screenshots/ui05/system-diagnostics-1440x900.png)
- [Traffic lab running, 1440×900](screenshots/ui05/traffic-lab-running-1440x900.png)
- [Traffic lab completed, 1440×900](screenshots/ui05/traffic-lab-completed-1440x900.png)
- [Processing trace, 1440×900](screenshots/ui05/processing-trace-1440x900.png)
- [Processing trace zero-to-many, 1440×900](screenshots/ui05/processing-trace-zero-to-many-1440x900.png)
- [Overview, 1366×768](screenshots/ui05/overview-1366x768.png)
- [Analyst queue with selection, 1366×768](screenshots/ui05/analyst-queue-selected-1366x768.png)
- [Overview, 1920×1080](screenshots/ui05/overview-1920x1080.png)
- [Analyst queue with selection, 1920×1080](screenshots/ui05/analyst-queue-selected-1920x1080.png)

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
