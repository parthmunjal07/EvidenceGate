# EvidenceGate frontend

The maintained operator-console source is React + TypeScript in `src/`. FastAPI
continues to own the API and serves the Vite build from
`../evidencegate/api/static`. That output is generated and committed for the
Python-only demo launch; do not hand-edit it. Rebuild after source changes.

## Commands

```bash
npm ci
npm run dev       # Vite on port 5173; FastAPI should run on port 8000
npm run typecheck
npm run lint
npm test -- --run
npm run build     # emits hashed JS/CSS into the FastAPI static package
npm audit
```

The production build has no source maps. Hash-named assets make stale browser
caches less likely; TypeScript sources remain in the repository for review.

## Architecture

- `api/` models the existing FastAPI DTOs and centralizes typed fetch/error handling.
- `state/` uses a small Context + reducer for runtime, newest results, alerts,
  status records, replay state, cursor state, and stream status.
- `hooks/useReplay.ts` owns cancellable replay-status polling.
- `EvidenceContext` owns EventSource lifecycle. SSE result messages are hints:
  it fetches each Result from REST. `stream_gap` and reconnect-ready events use
  `/results` cursor pages for durable resynchronization.
- `pages/` owns the five hash-routed sections. Page filters and selections stay
  local. No router, query cache, or global state library is needed.
- `components/` contains the shell, semantic tables, evidence inspectors, and
  the event-driven SVG flow. Existing UI-01 CSS is retained in `src/styles.css`.

The `/results` collection and individual Result endpoint stay the scientific
authority. `/alerts` remains a query-time SIH analyst presentation and status
projection. The frontend does not create results, alert conclusions, scores,
or severity.

## Development proxy and runtime

Vite proxies `/health`, `/runtime`, `/results`, `/alerts`, `/events`, and
`/replay` to FastAPI. Hash navigation avoids route collisions and server-side
SPA fallback logic. For a demo, build once, then run only:

```bash
python -m uvicorn evidencegate.api.app:app --host 127.0.0.1 --port 8000
```
