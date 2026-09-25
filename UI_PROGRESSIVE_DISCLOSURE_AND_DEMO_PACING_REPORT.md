# UI progressive disclosure and demo pacing

## What changed

Source review identified a three-column target registry with uneven family card heights, repeated implementation-status text, status cards that printed pretty JSON, and a permanent full-width quality/visibility help panel. Replay showed a raw lane-oriented event log and had no separately paced explanatory trace. These were code-level findings; browser screenshots were unavailable for visual confirmation.

- System status now opens on seven runtime-derived analytic-family rows. Family counts and mechanism counts come from the runtime target list; mechanism IDs and implementation evidence are available only after opening a family. Repeated “Active factual mechanism” copy is gone.
- Status records lead with a readable result, family/mechanism, entity summary, missing prerequisite, and time. Selecting a row opens the existing right inspector. Quality and visibility use structured labels. Raw evidence, claim ceiling, references, and full IDs are rendered only after opening Technical details. The known DDOS-A TCP state-key shape is formatted only when its mechanism ID and field types match; unknown shapes fall back safely.
- Alert and result inspectors keep evidence summaries and missing prerequisites in the foreground; raw evidence structures and IDs are behind technical disclosures.
- Replay now has a separate Visual pace control. Demo runs for about 4.75 seconds; Normal runs for about 1.9 seconds. The original Replay speed control and request contract are unchanged. Results enter application state immediately. The presentation queue is capped at three pending traces, coalesces equivalent queued traces, and bounds its seen-ID set to 64. Results sharing source-observation IDs appear as separate analytic outputs.
- Reduced-motion mode skips the visual trace. Replay labels it “Visual trace” and states that display pacing does not represent processing latency.

## Scientific and runtime boundary

No backend, API, routing, detector, threshold, result/alert schema, quality/visibility semantic, SSE, replay contract, or persistence code changed. Only the local UI build and replay QA data changed. The live `raw_pcap_ddos_recon` QA replay added 35 persisted results to the local database (11 input records, 11 observations). The separate `mixed_ddos_recon` replay completed with zero persisted results.

## Verification

- Frontend clean install: `npm ci` passed in an isolated copy. Running it in the workspace first failed because the declared Node requirement is `>=24.21.0` while the available version is `22.20.0`, and the running Vite process locked its Rolldown native binary. Dependencies were restored from the isolated install without stopping that process.
- Frontend typecheck: PASS.
- Frontend lint: PASS.
- Frontend tests: PASS, 43 tests across 9 files.
- Frontend build: PASS. JS bundle is 273.55 KB (from 263.65 KB, +3.75%); CSS is 27.24 KB (from 24.18 KB, +12.65%).
- `npm audit`: PASS, 0 vulnerabilities.
- Full pytest: PASS, 440 passed.
- `python -m compileall -q evidencegate scripts`: PASS.
- `git diff --check`: PASS.
- Runtime DGA readiness: `ARTIFACT_MISSING` (`MODEL_PATH_MISSING`); live scored DGA QA is blocked by the unavailable artifact.
- Zero-to-many live QA: PASS on raw PCAP replay. The 35 persisted results included 8 shared-observation groups; the largest group contained 8 analytic results.

## Screenshot and visual review

Screenshots were not captured. The available computer-use browser inventory returned no apps or browsers; opening the local page reported that the browser was unavailable. The `@oai/sky` Windows automation pipe also could not connect. As a result, the required 1366×768, 1440×900, and 1920×1080 screenshots and the requested Overview, Alerts, Results, System Status, inspector, and Replay-state visual reviews remain blocked. Visual acceptance and judge narration are not claimed as passed. Rachit’s screenshot review remains the human gate.

## Review status

Changes are committed locally only. Nothing was pushed. Do not push until screenshot review is complete and approved.
