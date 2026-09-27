# Railway deployment runbook

## Runtime shape

Railway builds the root `Dockerfile` and starts one Uvicorn process. The React
console is prebuilt into `evidencegate/api/static`. The service is single-host:
SQLite is the durable result store and the exact DGA-A1/M1-R1 model is loaded
from the same persistent volume. Do not scale this SQLite-backed service to
multiple replicas.

The checked-in `railway.json` selects Dockerfile builds, the `/health` deploy
check, and restart-on-failure. Railway mounts volumes only when the service
starts, so the model must be uploaded to the attached volume before the service
restart that should load it. [Railway Dockerfile builds](https://docs.railway.com/builds/dockerfiles)
and [volume behavior](https://docs.railway.com/volumes) describe these platform
contracts.

## Volume and variables

Attach one volume to the app service at `/data`. Set these service variables:

| Variable | Value |
| --- | --- |
| `EVIDENCEGATE_PUBLIC_MODE` | `1` |
| `EVIDENCEGATE_DB` | `/data/evidencegate.db` |
| `EVIDENCEGATE_DGA_MODEL` | `/data/DGA_M1_R1_SERIALIZED_MODEL.joblib` |
| `EVIDENCEGATE_DEV_SCENARIOS` | `0` or unset |

Never store the model or SQLite file in the container image. The verified model
is `DGA_M1_R1_SERIALIZED_MODEL.joblib`, 5,720,970 bytes, SHA-256
`39da209d2cfd869dd284e10b8a07adc04826c95146712cc6854a69b9873890df`.
The artifact remains Drive-restricted; its private locator is not a public API
field.

## Build and first deployment

1. From an authenticated terminal, link this checkout to the existing Railway
   project, production environment, and app service. Confirm `railway status`
   names the intended target before deploying. Railway documents this at
   [CLI login](https://docs.railway.com/cli/login) and
   [CLI link](https://docs.railway.com/cli/link).
2. Attach the `/data` volume and configure the variables above in the Railway
   service settings.
3. Upload the verified local artifact to `/data/DGA_M1_R1_SERIALIZED_MODEL.joblib`.
   Use `railway volume browse /` to open the interactive volume browser and
   upload the file, or use the SSH/SCP instructions in
   [Railway SSH](https://docs.railway.com/cli/ssh). A current CLI with
   `railway volume files upload` can use that command directly.
4. Verify the uploaded file's byte count and SHA-256 from the running service
   (`railway ssh -- sha256sum /data/DGA_M1_R1_SERIALIZED_MODEL.joblib`).
5. Deploy the committed source with `railway up`. Wait for the configured
   `/health` check to pass, then verify `/runtime` reports
   `dga_model_readiness: VERIFIED_READY`.

Never make the Drive file public, paste the model bytes into shell history, or
add it to Git/Docker build context. The upload target and service target must be
the same project, environment, and volume.

## Health, public-but-unlisted behavior, and smoke checks

`GET /health` returns 200 only after SQLite connects. The application serves
`X-Robots-Tag: noindex, nofollow, noarchive, nosnippet` on every response,
disables FastAPI schema pages in public mode, serves a `robots.txt` disallowing
crawling, and includes an HTML robots meta tag. These controls discourage
indexing; they are not access control. Do not put sensitive records in the
curated public demos.

After deploy, use the sequential checklist in
[`JUDGE_DEMO_RUNBOOK.md`](JUDGE_DEMO_RUNBOOK.md), check the five public scenarios,
and hard-refresh Overview, Traffic Lab, Evidence, and Investigations. Check
desktop and mobile widths. Compare the live source SHA with the committed SHA.

## Persistence and backup

The only durable app state is `/data/evidencegate.db`; replay trace is bounded
in-memory presentation telemetry. Keep the `/data` volume attached across
deployments and restarts. Do not delete or replace it during normal deploys.

Enable a Railway daily or weekly volume backup and take a manual snapshot before
a release or planned data maintenance. Railway volume backups include SQLite
files and can be restored through the service Backups panel; see
[Railway volume backups](https://docs.railway.com/volumes/backups). For an
additional logical copy, pause replays, then use the Python standard-library
SQLite backup API through the service shell:

```sh
railway ssh -- python -c "import sqlite3; src=sqlite3.connect('/data/evidencegate.db'); dst=sqlite3.connect('/data/evidencegate-backup.db'); src.backup(dst); dst.close(); src.close()"
```

Download the resulting file with Railway's volume browser or SCP. Before a
restore, stop app writes, keep the original volume snapshot, restore to a
separate backup copy where possible, and verify `/health` and `/results` before
resuming demo runs.

## Restart, rollback, and release repair

- A code release is built from the pushed Git commit. The health check gates
  traffic to the new deployment.
- For a failed release, use Railway's deployment history to redeploy the last
  known-good commit. Keep the same volume mounted; do not roll back by deleting
  storage.
- If SQLite schema or data is implicated, stop replays and restore a Railway
  volume snapshot only after identifying the correct backup timestamp.
- For a genuine live defect, fix and verify it locally, commit and push the
  repair, redeploy, and rerun the affected live scenario. Do not patch only the
  running container.

## Deferred

Live interface capture, NetFlow/IPFIX/sFlow, raw-PCAP DNS parsing, learned
correlation, distributed execution, production throughput sizing, and
production multi-tenant access control are not part of this release.
