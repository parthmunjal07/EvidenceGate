# SIH26145 EvidenceGate Runtime (MVP)

EvidenceGate is a strictly-bounded, single-host Python runtime application that
incrementally ingests, canonicalizes, routes, and persists immutable network
observations and factual analytic results.

The implemented mechanisms are DGA-A1/M1-R1, DNS-T1, ENC-A, CAT6-EX-M1, C2-R1 recurrence
measurement, DDOS-A-B0 SYN/state, and factual bounded DDoS demand/context
mechanisms for UDP, victim reflection shape, apparent source diversity, ICMP,
fragments, and TCP initiating-attempt churn. All seven factual DDoS mechanisms
are default active. Category-5 Recon horizontal breadth, target-port breadth,
host-by-port geometry, and captured TCP probing-state measurements are also
default active. The former `ddos` and `recon` provider shells are not default
runtime targets.

DGA is **DEFAULT ACTIVE M1-R1 LEXICAL MODEL EVIDENCE**. It verifies and reuses
the exact Drive-owned artifact identified by the repository manifest. There is
no DGA maliciousness threshold and no malware, infection, C2, tunnelling,
exfiltration, ownership, or intent conclusion. DNS-T1 remains an independent
structural observation; one clear-DNS observation may produce both immutable
results without fusion. Active ML is limited to the DGA-A1/M1-R1 lexical model;
the other mechanisms remain transparent rules, statistics, state, and context.

Gate A remains `SCIENTIFICALLY_CONSISTENT_REBUILD WITH ORIGINAL-RUN TRACEABILITY
LIMITATION`, not a bit-identical historical reproduction. Recovered R1 execution
files remain separate history, reference a different serialization hash, and
show a later evaluation-pipeline failure.

The DDoS SYN lane uses controlled-MVP engineering bounds of 1024 state keys,
16 reordered events per key, and 2048 reordered events lane-wide. Each DDoS
window lane uses 512 state keys, 256 reordered events per key, and 2048 reordered
events lane-wide; bounded apparent-source and visible-tuple sets retain at most
256 values where applicable. The five-second SYN TTL and one-second event-time
measurement window remain controlled reference/POC configuration, not attack
thresholds.

Each default Recon lane uses controlled-MVP bounds of 1024 state keys, 16
retained events per key, 16 reordered events per key, and 1024 reordered events
lane-wide, with a 3600-second state TTL and 60/3600-second observation horizons.
Truncation is reported as lower-bound evidence. These limits and windows are
controlled-MVP configuration, not production sizing or malicious-scan
thresholds. There is no DDoS verdict, malicious-scan verdict, universal score,
confidence/severity ranking, or active DDoS/Recon ML.

C2-R1 is default active with controlled-MVP engineering bounds of
1024 state keys, 16 pending reordered events per key, and 2048 pending reordered
events lane-wide. These are tested controlled-MVP engineering containment bounds,
not production sizing or C2/scientific thresholds. Supported passive inputs are
structured typed-NDJSON replay and offline raw-PCAP replay. PCAP processing is
incremental and read-only: capture timestamps remain event time, current replay
arrival is ingest time, and direction, visibility, endpoint roles, services, and
reflection facts come only from an explicit trusted sidecar. Live interface
capture and NetFlow/IPFIX/sFlow input are not implemented.

## Setup, Run, and Test Instructions

### Prerequisites
- Python 3.11+
- `pip` / `venv`

### Installation
```bash
python -m venv .venv
```

Activate it with `.venv\Scripts\Activate.ps1` on PowerShell or
`source .venv/bin/activate` on Linux/macOS, then install the package:

```bash
python -m pip install -e ".[test,dga-m1,benchmark]"
```

### Running the System
EvidenceGate exposes the dashboard, durable API, live result-notification
stream, and controlled replay service from one FastAPI process. SQLite data is
stored in `evidencegate.db` by default.

```bash
python -m uvicorn evidencegate.api.app:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/`. Choose an allowlisted replay in the left panel,
watch persisted results arrive, and open a result to inspect its evidence,
visibility, quality, claim limit, and provenance. The application creates and
migrates the database automatically. Set `EVIDENCEGATE_DB` before startup to use
a different SQLite file. Set `EVIDENCEGATE_DGA_MODEL` to the explicit local path
of `DGA_M1_R1_SERIALIZED_MODEL.joblib`. If the exact artifact cannot be verified,
the `dga.m1` lane stays registered and emits `ANALYTIC_UNAVAILABLE`; it never
substitutes a model or reports zero detections.

The API is documented at `http://127.0.0.1:8000/docs` and provides:

- `GET /health`
- `GET /results` and `GET /results/{result_id}`
- `GET /events` (Server-Sent Events)
- `POST /replay` and `GET /replay/status`
- `GET /runtime`

`POST /replay` accepts only scenario IDs returned by `GET /runtime`; it never
accepts filesystem paths or network locations. Example:

```bash
curl -X POST http://127.0.0.1:8000/replay \
  -H "Content-Type: application/json" \
  -d '{"scenario":"mixed_ddos_recon","speed":0}'
```

Replay a versioned finite bundle through the same streaming runtime:

```bash
python scripts/replay.py --bundle tests/fixtures/replay/dns_forward --database evidencegate.db --speed 0
```

Replay a passive raw PCAP with its trusted adapter manifest:

```bash
python scripts/replay.py \
  --pcap tests/fixtures/pcap/raw_ddos_recon/capture.pcap \
  --manifest tests/fixtures/pcap/raw_ddos_recon/manifest.json \
  --database evidencegate.db --speed 0
```

Replay bundles contain a `manifest.json` plus line-oriented `records.ndjson`.
They are opened read-only and contain source/network facts only, never analytic
results. `--speed 0` disables pacing; a positive value replays event-time spacing
at that multiplier. Use `--validate-only` to validate without running analytics.

### Testing the System
The system is protected by a suite of invariants derived directly from the Implementation Contract.
```bash
pytest

python -m compileall -q evidencegate scripts

# Characterize the final 16-target stack with real DGA inference and SQLite
python scripts/benchmark_final_mvp.py
```

This benchmark is explicitly **CONTROLLED MVP CHARACTERIZATION / NOT PRODUCTION
SIZING**. The typed workload exercises DGA; the separate raw-PCAP workload does
not because raw-PCAP DNS extraction remains deferred. The M13 pre-DGA benchmark
and historical dummy-plugin saturation benchmark remain superseded history.

## Dependency and License Inventory
The MVP runtime utilizes the following minimal open-source packages:
- `fastapi` (MIT) - API, lifecycle, static dashboard, and SSE routing.
- `dpkt` 1.9.x (BSD-3-Clause) - incremental offline PCAP and packet parsing.
- `uvicorn` (BSD) - ASGI application server.
- `pydantic` (MIT) - Strongly-typed immutable validation for domain objects.
- `prometheus-client` (Apache 2.0) - Instrumenting bounded health metrics.
- `pytest` / `pytest-asyncio` (MIT / Apache) - Contract verification framework.
- `httpx` (BSD) - ASGI integration testing only.
- `psutil` (BSD) - Baseline system health tracking for benchmarks.
- `scikit-learn` 1.6.1 / `joblib` 1.6.0 - verified DGA M1-R1 inference only.
- `tldextract` 5.1.3 - offline bundled-PSL DGA representation with private suffixes.

## Explicit Scientific No-Go Boundaries
The runtime infrastructure enforces strict boundaries separating operational plumbing from scientific analytic responsibility. 
- **No Global Detectors**: The runtime does not evaluate, tune, or judge threats. It brokers information.
- **No Thresholds**: The runtime does not define global thresholds for volume, bytes, or time gaps.
- **No Invented Context**: Absence of a signal, failure to admit an observation, or an unavailable analytic lane **must never** be silently translated into a "benign" or "no threat" claim.
- **Scaffold Separation**: Scaffold pipelines (used for tests) are structurally prevented from emitting `ThreatAlert` outcomes or attaching confidence/severity rankings.
- **No Dynamic External Plugins**: Analytics are integrated statically. The MVP prohibits hot-reloading random external binaries.

## Documentation Reference
See the `docs/` folder for comprehensive manuals:
- [Architecture & Data Flow](docs/ARCHITECTURE_AND_DATA_FLOW.md)
- [Plugin Author Contract](docs/PLUGIN_AUTHOR_CONTRACT.md)
- [API & Persistence](docs/API_AND_PERSISTENCE.md)
- [Troubleshooting & Runbook](docs/TROUBLESHOOTING_RUNBOOK.md)
