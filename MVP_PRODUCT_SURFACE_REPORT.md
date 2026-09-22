# MVP Product Surface Report

## Scope

This M12 pass adds the smallest real judge-facing product layer over the existing
EvidenceGate runtime. It changes no mechanism science, thresholds, governance,
or result finalization semantics.

## Before and after

Before this pass, `/health` was real, `/results` always returned an empty list,
and `/live` echoed browser input. Replay was available only through
`scripts/replay.py`; no active frontend tree existed.

After this pass, one lifecycle-managed FastAPI application owns the existing
SQLite repository, runs the real default 16-lane runtime against allowlisted
bundles, exposes immutable results through typed REST DTOs, broadcasts
persisted-result hints through SSE, and serves a lightweight HTML/CSS/JavaScript
dashboard.

```text
allowlisted versioned fixture
            |
            v
     real default runtime (16 lanes)
            |
       finalized Result
            |
            v
   existing SQLite repository  ----->  GET /results
            |
       commit succeeds
            |
            v
 bounded per-client SSE hints  ----->  dashboard fetches authoritative result
```

There is one analytic path and one result store. The dashboard does not compute
or inject mechanism results.

## Application boundary

`create_app(database)` constructs an application-scoped `EvidenceGateService`.
FastAPI lifespan startup connects and migrates SQLite; shutdown cancels any
active controlled replay and closes the database. There is no module-global
connection created at import time. Tests use a temporary SQLite file.

## API routes

| Route | Behavior |
| --- | --- |
| `GET /` | Same-origin static dashboard |
| `GET /health` | Application and SQLite connection health |
| `GET /results` | Durable filtered cursor query, HTTP limit 1-500 |
| `GET /results/{result_id}` | One authoritative immutable result |
| `GET /events` | Server-Sent Events persisted-result hints |
| `POST /replay` | Starts one allowlisted controlled replay |
| `GET /replay/status` | Measured replay lifecycle and counts |
| `GET /runtime` | Exact target, family, database, stream, and replay status |

OpenAPI summaries and response models describe each public route. The
application uses no cross-origin wildcard policy.

## Result representation

The API maps stored dataclasses into Pydantic DTOs and retains the immutable
result ID, schema/type/time, lane and plugin versions, governance, entity,
taxonomy, mechanism ID, status, claim ceiling, structured evidence, missing
prerequisites, source observations/sources, factual quality and visibility,
state/config/parser/model references, governing IDs, quality references, and
provenance references. Presentation family is derived from lane ownership and
does not change the mechanism or taxonomy.

No current evidence result is renamed into a threat verdict. No numeric
confidence or severity is supplied by the API or dashboard.

## SQLite cursor contract

Ordering is pinned to the durable tuple `(created_time, result_id)`.

- A normal cursor page is newest-first. `next_cursor` continues strictly before
  its tuple, so concurrent newer writes do not shift older pagination.
- `sync_cursor` has an `after.` prefix and marks the newest tuple observed by a
  client. Passing it as `cursor` continues strictly after that tuple in ascending
  order. The dashboard uses this form after reconnect or a stream gap.
- Cursor text is URL-safe base64 over the timezone-aware created time, a NUL
  separator, and the result ID. Decode, timestamp, and non-empty-ID validation
  are explicit.
- Cursors are not list indexes, random IDs, or offsets.

Filters cover lane, mechanism ID, result type, source ID, and exclusive created
time bounds (`created-after` and `created-before`).

## Live stream and slow clients

The runtime writer executes `finalize -> SQLite commit -> publish`. A failed
write emits no notification. Notifications contain only the result ID, created
time, lane, mechanism, result type, and sync cursor; REST remains authoritative.

Each subscriber owns a bounded queue. A full queue is cleared, the current hint
is dropped, and `stream_gap`/`resync_required` is delivered. The client then
continues from its durable sync cursor. One slow client cannot wait on or block
SQLite, runtime queues, or another subscriber. Missing a notification is not
reported as a scientific quality gap.

## Replay allowlist

| Scenario ID | Bundled fixture purpose |
| --- | --- |
| `mixed_ddos_recon` | Default TCP sequence routed independently to DDoS and Recon |
| `ddos_one_way` | One-way SYN visibility |
| `ddos_udp` | UDP demand/context |
| `c2_recurrence` | C2-R1 recurrence measurement |
| `dns_observation` | DNS-T1 structural observation |
| `encrypted_session` | ENC-A TLS handshake evidence |
| `transfer_magnitude` | CAT6-EX-M1 transfer magnitude |

Only registry keys cross the API boundary. The request model forbids extra
fields; a filesystem path, network location, or unknown scenario is rejected.
One replay job may run at a time with `IDLE`, `RUNNING`, `COMPLETED`, and `FAILED`
states. Counts and elapsed wall time come from the real replay runner and
persistence callback.

## Dashboard

The dashboard is same-origin static HTML, CSS, and browser JavaScript—no frontend
framework or build stack. It shows runtime state, active mechanism count, result
counts, seven presentation-family filters, allowlisted replay controls, and a
newest-first result timeline. Expanded cards separate observed references,
derived/measured evidence, missing evidence, visibility, quality, claim limit,
and provenance.

Status colors supplement explicit result-type text; they do not encode a
harmful/safe binary. DGA is shown as `ANALYTIC / MODEL NOT ACTIVE` with model
integration pending the frozen artifact and representation gate. It is never
shown as zero findings.

The initial page comes from REST. SSE result hints trigger an authoritative
single-result fetch. Browser reconnect and `stream_gap` handling use the durable
sync cursor.

## Current family state

| Family | Truthful state |
| --- | --- |
| DDoS | Active factual mechanisms |
| C2 / Beaconing | Active R1 recurrence measurement |
| DGA | Registered shell; model pending |
| DNS Tunnelling | Active T1 structural observation |
| Encrypted Sessions | Active ENC-A handshake evidence |
| Reconnaissance | Active H/V/2D/TCP measurements |
| Data Exfiltration | Active M1 transfer magnitude |

DGA and DNS Tunnelling remain independently owned mechanisms while appearing
under the official combined category where appropriate.

## Future standardized alert projection

`evidencegate.api.projection` defines a versioned `SihAlertProjection` and the
candidate `ConfidenceBasis` vocabulary. It is design-only: no route returns it,
no runtime callback creates it, and no evidence result is transformed into it.
Activation requires a separately approved semantic mapping policy or a genuine
model basis.

## Verification

The M12 tests cover empty and restarted databases, complete typed serialization,
cursor pagination, concurrent forward continuation, all filters, invalid input,
limit bounds, persist-before-publish, actual SSE endpoint output, multiple
subscribers, slow-client gap/resync, allowlist/path rejection, one-job replay,
runtime target truth, mixed DDoS/Recon zero-to-many delivery, C2, DNS, ENC-A,
transfer-magnitude presentation, DGA shell presentation, absence of fabricated
alert fields, and inactive projection wiring.

At implementation completion:

- `pytest`: 380 passed, 0 failed.
- `python -m compileall -q evidencegate scripts`: passed.
- `git diff --check`: passed.

## Limitations

- The broadcaster is intentionally process-local; history and recovery are in
  SQLite, while live hints do not survive process restart.
- The MVP permits one controlled replay at a time and has no distributed job
  coordination.
- Replay status records final runner read/emission counts when a run completes;
  persisted-result count advances during the run.
- The dashboard retains up to the pages loaded into the current browser session.
- DGA has no integrated model artifact and remains a registered shell.
- No whole-system throughput or production-readiness claim is made.
