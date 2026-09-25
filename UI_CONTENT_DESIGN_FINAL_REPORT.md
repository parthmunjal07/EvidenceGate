# UI-03 content design and typography pass

## Outcome

The React operator UI received a content, type, and hierarchy pass. No analytics, API fields, routing, persistence, replay behavior, confidence semantics, or alert policy logic changed. The only backend-adjacent edit updates an existing product-surface test to expect the new sentence-case navigation labels.

## Page jobs

- **Overview:** Show runtime, current alerts, evidence quality issues, and unavailable analytics, then a compact live evidence path.
- **Analyst alerts:** Help an analyst decide what to review and why it was surfaced.
- **Evidence results:** Show observed and derived source records behind alerts.
- **System status:** Show runtime, model readiness, policy, target registration, quality, and visibility records.
- **Replay:** Run a controlled scenario and review its outputs.

## Content and hierarchy

- Overview now leads with four runtime-backed metrics, followed by **Recent alerts** (up to six) and then **Live evidence path**. Empty alerts link to Replay. The path uses Observed traffic, Visibility checks, Analytics, and Evidence result, branching to Analyst review or System status.
- Navigation and page names use sentence case. The sidebar foregrounds EvidenceGate and Passive network evidence; SIH26145 remains footer metadata and the policy version remains in System status.
- Analyst alerts retain the visible distinction that an alert requests review and does not confirm malicious activity. Evidence results are described as the source records behind analyst alerts.
- Table headings and evidence summaries are shorter. Structured references render as concise text in tables while the inspectors retain the full values and claim ceiling.
- Replay copy uses direct scenario actions and explains that one observation can produce evidence for more than one analytic.
- Taxonomy labels display as human-readable names (for example, DDoS and DNS tunnelling); exact API values remain unchanged for filtering and data exchange.
- Repeated architecture captions, stage numbering, decorative eyebrows, and repeated explanatory notices were removed or reduced.

## Typography

| Role | Size / treatment |
| --- | --- |
| Page title | 24–28px, sans |
| Page description | 14px / 20px, sans |
| Major section | 17–19px, sans |
| Panel title | 14–16px, sans |
| Body | 14px / 20px, sans |
| Table | 13px / 18–20px, sans; approximately 40–48px rows |
| Secondary metadata | 12px / 16px, sans |
| Technical values | 11–12px / 16px, mono |

Primary stack: `"Segoe UI Variable", "Segoe UI", system-ui, -apple-system, BlinkMacSystemFont, Arial, sans-serif`.

Mono stack: `"Cascadia Mono", "SFMono-Regular", Consolas, "Roboto Mono", monospace`. Routine 9px text was eliminated; remaining 11px text is for technical values such as IDs, timestamps, hashes, and structured snapshots.

## Scientific and product boundaries

- UI changes preserve result types, confidence basis and score, severity, alert priority, source IDs, model references, governing IDs, quality and visibility snapshots, and zero-to-many result handling.
- DGA scores remain labeled as lexical resemblance and explicitly not calibrated attack probability. Non-DGA analytics state that numeric attack probability is not defined.
- Claim ceiling values remain exact in evidence detail. The UI separates source result records from analyst alerts and status records.
- No scientific or backend behavior changed. The DGA serialized model remains absent and untracked in this checkout.

## Visual and replay QA

- Headless Chrome screenshot QA was completed for Overview at 1280×720, 1366×768, 1440×900, and 1920×1080. The layout showed no overlap; at 1280px the dense alert table uses horizontal scrolling for its later columns.
- At 1440×900, captures were inspected for Analyst alerts, Evidence results, System status, Replay, the alert inspector, and the result inspector. The inspector captures showed evidence, confidence semantics, quality/visibility, source records, and the exact claim-limit content. The final small typography, taxonomy, and claim-limit label adjustments were rebuilt and covered by automated validation after the inspected captures.
- Screenshots: `%TEMP%\evidencegate-ui03-shots-DbRIJH\` (`overview-*.png`, `analyst-alerts-1440x900.png`, `evidence-results-1440x900.png`, `system-status-1440x900.png`, `replay-1440x900.png`, and both inspector captures).
- Isolated replay QA used a temporary database on port 8001 and left the existing port 8000 service and its database untouched. `dga_lexical`, `mixed_ddos_recon`, and `dns_observation` completed; results appeared in the evidence table, alerts in the analyst view, and inspectors opened. The UI flow tests cover active and empty states.
- The DGA artifact was not present (`ARTIFACT_MISSING` / `MODEL_PATH_MISSING`). The DGA replay therefore produced an unavailable analytic result plus an independent DNS review finding; it could not demonstrate a scored DGA output or verify live DGA/DNS independence in this checkout. DGA score wording and inspector semantics are covered by UI tests. This is the remaining QA limitation.

## Automated checks

- `npm ci`: passed; 259 packages installed, 0 vulnerabilities. The environment runs Node 22.20.0 while `package.json` declares Node >=24.21.0, so npm printed an engine warning.
- `npm run typecheck`: passed.
- `npm run lint`: passed.
- `npm test -- --run`: passed, 37 tests across 8 files.
- `npm run build`: passed. Final bundle: JavaScript 263.65 kB (79.96 kB gzip), CSS 24.18 kB (6.41 kB gzip). Compared with UI-02 (~267 kB JS and ~24 kB CSS), JavaScript is about 3.3 kB smaller and CSS about 0.2 kB larger.
- `npm audit`: passed, 0 vulnerabilities.
- `pytest -q`: passed, 440 tests.
- `python -m compileall -q evidencegate scripts`: passed.
- `git diff --check`: passed.

## Final gate

**Human visual acceptance is still required.** The DGA model artifact is also needed to complete scored DGA and independent DGA/DNS replay verification. No further redesign should start before Control Room review.
