# Deployment and verification

EvidenceGate is a single-process research prototype. This guide covers local replay, the optional restricted DGA artifact, and the repository's Railway container settings. It does not provide production sizing.

## Prerequisites

- Python 3.11 or newer.
- Node.js 24.21 or newer for building the frontend.
- Git and PowerShell on Windows, or equivalent shell commands on another platform.

## Local setup

From the repository root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[test,quality]"
Push-Location frontend
npm ci
npm run build
Pop-Location
python -m uvicorn evidencegate.api.app:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/`. Health is available at `/health`. The scenario API is allowlisted; arbitrary local paths and remote URLs are not accepted as replay inputs. Supported source modes are typed/NDJSON replay and offline classic Ethernet PCAP replay. There is no live NIC, NetFlow/IPFIX/sFlow, or raw-PCAP DNS extraction.

The default database path is selected by the application. To select an explicit local path, set `EVIDENCEGATE_DB` before starting the server, for example:

```powershell
$env:EVIDENCEGATE_DB = "$PWD\data\evidencegate.db"
```

Create that directory first. SQLite persistence is local application state; back it up or clear it only using your normal data-management process.

## DGA model artifact

The restricted model bytes are not committed to the repository. EvidenceGate can run without them. In that state, the DGA provider fails closed and emits `ANALYTIC_UNAVAILABLE`; it does not substitute a model, emit fabricated DGA evidence, or interpret unavailability as zero findings.

When authorized to use the exact artifact, install it at a location outside the source tree or another approved local location, then configure `EVIDENCEGATE_DGA_MODEL` to that file. Verify all of the following against [`../artifacts/dga/DGA_M1_R1_ARTIFACT_MANIFEST.json`](../artifacts/dga/DGA_M1_R1_ARTIFACT_MANIFEST.json):

| Field | Required value |
|---|---|
| Model ID | `DGA-A1-M1-R1` |
| Filename | `DGA_M1_R1_SERIALIZED_MODEL.joblib` |
| Size | 5,720,970 bytes |
| SHA-256 | `39da209d2cfd869dd284e10b8a07adc04826c95146712cc6854a69b9873890df` |
| Runtime dependencies | `joblib==1.6.0`, `scikit-learn==1.6.1`, `tldextract==5.1.3` |

Install the optional dependency extra with `python -m pip install -e ".[dga-m1]"`. For a local SHA-256 check in PowerShell, use `Get-FileHash -Algorithm SHA256 <path>`. A mismatch or missing file must leave the analytic unavailable. Do not commit restricted bytes, private storage URLs, credentials, or local user paths.

## Container and Railway notes

The Docker build compiles the frontend and runs the Python application in one container. Railway is configured for one application process; persistent SQLite data should live on a mounted volume at `/data`. Set:

```text
EVIDENCEGATE_PUBLIC_MODE=1
EVIDENCEGATE_DB=/data/evidencegate.db
EVIDENCEGATE_DGA_MODEL=/data/DGA_M1_R1_SERIALIZED_MODEL.joblib
```

The DGA path is optional for service startup but required for verified DGA readiness. Provide the artifact through an authorized private deployment mechanism and validate its hash during release preparation. Set `EVIDENCEGATE_PUBLIC_MODE=1` to disable the interactive API documentation endpoints. The app sends `X-Robots-Tag: noindex, nofollow, noarchive, nosnippet` and serves a disallow-all `robots.txt`; verify the deployed response headers and body in the target environment. Keep internal/test scenarios disabled in public mode. Never put private artifact locators or deployment tokens in repository files.

Use a single application process with the current SQLite/state assumptions. Multi-replica deployment, distributed state, production sizing, and an availability/SLA target have not been validated.

## Health and manual check

1. Start the service and request `GET /health`; it should return a successful health response.
2. Open the workbench and confirm that the allowlisted replay catalogue loads.
3. Run one typed replay scenario and confirm the resulting independent evidence appears in Results.
4. Run the offline PCAP replay scenario and check that packet-derived evidence appears.
5. If testing DGA, verify model readiness and exact artifact hash first. Without the artifact, verify fail-closed unavailability.

Repository checks are listed in the README. The recorded benchmark files are controlled measurements for their individual workloads, not deployment capacity guidance.
