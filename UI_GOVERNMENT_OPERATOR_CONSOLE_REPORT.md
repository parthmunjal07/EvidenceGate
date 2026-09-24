# EvidenceGate Government Operator Console

**UI-01 implementation report · 2026-09-25**

## Design goal

Adapt the frozen EvidenceGate MVP into a calm, dense operations console for a
government or SOC analyst. The interface keeps passive observations, immutable
scientific results, the versioned analyst projection, and operational evidence
status visibly separate. It uses the existing FastAPI-served HTML, CSS, vanilla
JavaScript, and SVG stack.

## Reference sources studied

- PlanetScale, [How product design works at PlanetScale](https://planetscale.com/blog/how-product-design-works-at-planetscale): prototype core flows and real state changes, then refine the working interface with engineering.
- PlanetScale, [B-trees and database indexes](https://planetscale.com/blog/btrees-and-database-indexes): interactive diagrams explain cause and effect, allow user-controlled pacing, and keep motion tied to an explicit action.
- PlanetScale, [Making 768 servers look like 1](https://planetscale.com/blog/making-768-servers-look-like-1): layered architecture diagrams make a complex system legible through a clear abstraction.
- [U.S. Web Design System](https://designsystem.digital.gov/), including its [table guidance](https://designsystem.digital.gov/components/table/): accessible semantics, predictable controls, readable data tables, and consistent focus behavior.
- [GOV.UK Design System](https://design-system.service.gov.uk/) and its [accessibility guidance](https://design-system.service.gov.uk/accessibility/): plain language and the reminder that using design-system patterns still requires product-level accessibility checks.
- The supplied Drive reference folder was located. Its examples include ExtraHop, Darktrace, Arista NDR, Arkime, Vectra, Corelight, Suricata, Plixer, Cisco Secure, FortiNDR, Zeek/Grafana, and Stitch1. The implementation follows the brief's pattern guidance: stable navigation, compact evidence tables, master/detail investigation, and an evidence-focused inspector. No reference assets were added to the repository.

## What was retained

- Real `/runtime`, `/results`, `/alerts`, `/events`, `/replay`, and
  `/replay/status` data flows.
- Durable-result resynchronization after SSE reconnects or stream gaps.
- Runtime-provided replay allowlisting and source-result traceability.
- Existing DGA model score wording and the source claim ceiling.

## What changed

- Replaced the masthead and two-pane timeline with an application shell and five
  operator sections: Overview, Analyst Alerts, Evidence Results, System &
  Evidence Status, and Replay.
- Added a four-metric operational summary sourced from the runtime and the
  newest 500 projections.
- Added a responsive overview flow diagram. Persisted result events animate the
  actual evidence path; review findings and lifecycle status branch into
  separate projection stages.
- Replaced large result and alert cards with dense, selectable tables, search
  and filters, and a right-side evidence inspector.
- Added a system page that renders all runtime targets and current model,
  database, policy, source, subscriber, and status-record details.
- Added replay speed selection, runtime-backed scenario controls, replay state
  and counters, and an event log populated by persisted result events.
- Added small-screen navigation, scrollable tables, visible focus, labelled
  state text, and reduced-motion handling.

## Information architecture and interaction

- **Overview:** runtime/replay state, alert and status counts, event-driven
  evidence flow, and recent analyst attention.
- **Analyst Alerts:** the active `SIH_ALERT_POLICY_V1` queue with filters and an
  inspector. Each alert links to its immutable source Result.
- **Evidence Results:** the scientific authority, searchable by entity, lane,
  mechanism, result ID, family, and factual result type.
- **System & Evidence Status:** runtime summary, all default targets grouped by
  lane family, and separately projected status records.
- **Replay:** allowlisted runtime scenarios, speed control, live replay status,
  persisted counters, and session result events.

## Motion policy

Motion explains state changes. A result pulse and brief stage highlights run
only after persisted SSE result notifications. The replay progress indicator
reflects `/replay/status`. Page transitions are brief; no animation loops in the
background. `prefers-reduced-motion: reduce` removes the pulse and reduces
transitions while keeping all information and controls available.

## Accessibility

The interface uses semantic navigation, headings, tables, buttons, labelled
filters, keyboard-selectable rows, visible focus, and an Escape-closeable
inspector overlay at narrower widths. Statuses include text and symbols, so
colour is not the only signal. Tables retain horizontal scrolling at narrow
widths. A browser-based visual/accessibility audit was unavailable in this
session because no browser was exposed to the computer-use environment; the
responsive rules and rendered HTML structure were checked in source and through
product tests.

## Scientific-semantic safeguards

- `/results` remains the immutable scientific authority; `/alerts` remains the
  active, versioned analyst presentation layer.
- Alert copy states that an alert is an analyst-attention record, not
  confirmed malicious activity.
- The DGA inspector labels its numeric value as a DGA-labelled lexical
  resemblance score and says it is not calibrated attack probability.
- Non-DGA confidence displays its basis and says numeric attack probability is
  not defined by that analytic.
- Quality facts, visibility classes, evidence status, and analyst priority are
  displayed separately.
- Claim ceilings render the exact source string. Source observations, model
  refs, parser refs, governing IDs, config hash, and source Result ID remain
  available in the inspectors.
- No global risk score, invented telemetry, synthetic event timeline, or
  attack map was added.

## Files changed

- `evidencegate/api/static/index.html`
- `evidencegate/api/static/styles.css`
- `evidencegate/api/static/app.js`
- `tests/test_product_surface.py`
- `README.md` (operator-console run instructions)
- `UI_GOVERNMENT_OPERATOR_CONSOLE_REPORT.md`

No backend, scientific, result, projection, persistence, or API contract files
were changed.

## Screens and verification

- Overview, Analyst Alerts, Evidence Results, System & Evidence Status, and
  Replay are implemented in the single-page console.
- Product-surface tests: **17 passed**. They verify the five sections, the separate inspectors,
  scientific and presentation wording, runtime targets, reduced motion, and
  responsive CSS.
- `node --check evidencegate/api/static/app.js` passed.
- Local live replay smoke checks used `dga_lexical`, `mixed_ddos_recon`, and
  `dns_observation`. The DGA artifact reported `VERIFIED_READY`. The replays
  completed with 2, 8, and 2 results persisted respectively; the DGA source
  produced independent DGA and DNS-T1 review projections.
- UI static red-team search found no prohibited fake-score, attack-claim,
  candidate-alert, or world-map language in the active static UI.
- HTML source check found 68 unique IDs and no duplicate IDs. No replacement
  characters or external font imports were present.
- Full pytest suite: **440 passed, 0 failed**.
- `python -m compileall -q evidencegate scripts`: passed.
- `git diff --check`: passed.

## Known UI limitations

- The API exposes only the newest 500 alerts and status records. Older
  scientific results remain cursor-paged.
- The replay contract has no cancellation endpoint, so the UI offers no stop
  control.
- Browser screenshot QA at 1366×768, 1440×900, and 1920×1080 could not be
  performed in this session because no browser surface was available. The
  layout includes responsive rules for those widths and narrower screens.

## Human gate

The final visual and UX review remains with Rachit / Control Room. Scientific
semantics and backend contracts remain frozen.
