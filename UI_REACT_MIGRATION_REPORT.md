# EvidenceGate UI-02 React migration report

## Scope and authority

Migrated the UI-01 government operator console from hand-maintained browser
JavaScript to React + TypeScript. The UI-01 layout, restrained palette, tables,
inspectors, live flow, reduced-motion behavior, and five sections remain the
visual authority. No analytics, detector science, result DTOs, alert projection
policy, or confidence / severity semantics changed. FastAPI source changes were
limited to mounting Vite's generated `/assets` directory. All API routes and
contracts are unchanged.

## Architecture

- `frontend/src/api/types.ts` mirrors the actual response/request DTOs in
  `evidencegate/api/models.py` and `projection.py`; `api/client.ts` centralizes
  JSON fetches, abort signals, and typed HTTP errors.
- `EvidenceProvider` and `evidenceReducer` use React Context + `useReducer` for
  shared runtime, result map/order, alerts, status records, cursors, replay and
  stream state. Search and selection stay in their pages.
- `EvidenceContext` owns the SSE connection. A `result` event triggers a durable
  `/results/{result_id}` fetch. `ready` and `stream_gap` trigger cursor-based
  `/results` resync before alerts refresh. REST results remain scientific
  authority; SSE is never stored as a Result.
- `useReplay` polls `/replay/status` with one cancellable timer chain and refreshes
  runtime after completion.
- Five typed hash sections avoid collisions with FastAPI routes without a router
  dependency. `App.tsx` hosts the shell and page selection.
- Separate AlertInspector and ResultInspector components preserve the difference
  between the analyst projection and immutable scientific record. Shared
  primitives render exact claim ceilings, quality, visibility, and provenance.
- CSS stays ordinary CSS, carried forward from UI-01. There is no Tailwind,
  design-system package, table library, or icon dependency.

## Build and runtime

Node/npm are build-time dependencies. Vite emits hashed, source-map-free JS/CSS
to `evidencegate/api/static`; those generated assets are committed for demo
portability and overwritten by `npm run build`. FastAPI remains the only runtime
process. Development uses Vite's explicit proxy for the current API paths and
SSE.

Pinned frontend versions: React / React DOM 19.3.0, TypeScript 6.0.3, Vite
8.3.1, Vitest 5.0.1, Testing Library 16.3.3, ESLint 10.11.0, and Node
24.21.0 (current LTS; `package.json` requires Node >=24.21). Registry versions
were checked on 2026-09-25. Dependencies are locked by `package-lock.json`.

## Safeguards

- `REVIEW` stays analyst priority, never probability or impact.
- DGA shows its lexical resemblance score and says it is not calibrated attack
  probability. Non-DGA mechanisms state that numeric attack probability is not
  defined by that analytic.
- The source claim ceiling is rendered verbatim. Quality, visibility, system
  status, alert priority, and scientific Result remain separate.
- The flow highlights a persisted Result lane and branches to alert or status
  only according to the backend Result type. It never fuses independent results.
- Replay scenarios come only from `/runtime`; requests send a scenario ID and
  speed. Network and provenance values render as text.

## Verification

- Clean `npm ci`: passed in an isolated frontend copy using Node 24.21.0.
- `npm run typecheck`: passed.
- `npm run lint`: passed.
- Frontend tests: **16 passed**. Coverage includes hash navigation, runtime and
  scenario rendering, replay request payload, REST fetch after SSE notification,
  durable cursor resync on `stream_gap`, filters, confidence wording, semantic
  tables, inspectors, keyboard selection, and Escape close.
- `npm run build`: passed. Production output is **267.21 KB JS** (81.55 KB
  gzip) and **23.84 KB CSS** (6.40 KB gzip). No source maps are emitted.
- `npm audit`: **0 vulnerabilities** (0 info, low, moderate, high, or critical).
- Product/API-targeted pytest: **32 passed**. Full pytest: **440 passed**.
- `python -m compileall -q evidencegate scripts`: passed.
- `git diff --check`: passed.
- Existing product integration tests exercised verified-model DGA, mixed
  DDoS/Recon, DNS, and additional allowlisted replay scenarios through
  REST/SSE/API contracts. No detector or DTO code changed.
- React-source red-team search found no prohibited synthetic attack/probability
  language; remaining matches are factual boundary statements.
- The DGA model file exists locally and remains untracked.
- Browser screenshot QA was **not available**: the computer-use inventory had
  no browser and could not open the in-app browser. No viewport screenshot or
  visual inspection is claimed.

## Known limits

- Alert and status views preserve the backend's newest-500 bound; Results retain
  cursor paging.
- Replay has no cancellation API, so the UI has no stop control.
- Visual review at 1366×768, 1440×900, 1920×1080, and mobile widths remains for
  the Control Room review because no browser surface was available here.
- The source-folder `npm ci` could not unlink the native Vite binding while a
  Vite process held it. The clean install and full frontend checks passed in an
  isolated copy; stop that process before reinstalling dependencies in the
  source folder.
