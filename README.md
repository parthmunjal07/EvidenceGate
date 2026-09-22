# SIH26145 EvidenceGate Runtime (MVP)

EvidenceGate is a strictly-bounded, single-host Python runtime application that
incrementally ingests, canonicalizes, routes, and persists immutable network
observations and factual analytic results.

The implemented mechanisms are DNS-T1, ENC-A, CAT6-EX-M1, C2-R1 recurrence
measurement, DDOS-A-B0 SYN/state, and factual bounded DDoS demand/context
mechanisms for UDP, victim reflection shape, apparent source diversity, ICMP,
fragments, and TCP initiating-attempt churn. All seven factual DDoS mechanisms
are default active. Category-5 Recon horizontal breadth, target-port breadth,
host-by-port geometry, and captured TCP probing-state measurements are also
default active. The former `ddos` and `recon` provider shells are not default
runtime targets.

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
not production sizing or C2/scientific thresholds. Structured typed-NDJSON replay
ingest supports source-wide one-way direction and explicit per-record direction
for mixed-direction captures; raw-PCAP ingest and live capture are not.

## Setup, Run, and Test Instructions

### Prerequisites
- Python 3.14+
- `pip` / `virtualenv`

### Installation
```bash
# 1. Create and activate a virtual environment
python3.14 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies (see Dependency Inventory below)
pip install -r pyproject.toml
```

### Running the System
EvidenceGate exposes a FastAPI interface and internal SQLite persistence. 
```bash
# Start the web server (development mode)
uvicorn evidencegate.api.app:app --host 0.0.0.1 --port 8000
```
*Note: The MVP runs using an in-memory or generic SQLite file database. Ensure the SQLite schema is initialized via `evidencegate/persistence/schema.sql`.*

Replay a versioned finite bundle through the same streaming runtime:

```bash
python scripts/replay.py --bundle tests/fixtures/replay/dns_forward --database evidencegate.db --speed 0
```

Replay bundles contain a `manifest.json` plus line-oriented `records.ndjson`.
They are opened read-only and contain source/network facts only, never analytic
results. `--speed 0` disables pacing; a positive value replays event-time spacing
at that multiplier. Use `--validate-only` to validate without running analytics.

### Testing the System
The system is protected by a suite of invariants derived directly from the Implementation Contract.
```bash
# Execute the contract invariants test suite
pytest tests/test_ic_invariants.py -v

# Run the performance baseline benchmark
python scripts/benchmark.py
```

## Dependency and License Inventory
The MVP runtime utilizes the following minimal open-source packages:
- `fastapi` (MIT) - API endpoint shell and WebSocket routing.
- `uvicorn` (BSD) - ASGI application server.
- `pydantic` (MIT) - Strongly-typed immutable validation for domain objects.
- `prometheus-client` (Apache 2.0) - Instrumenting bounded health metrics.
- `pytest` / `pytest-asyncio` (MIT / Apache) - Contract verification framework.
- `psutil` (BSD) - Baseline system health tracking for benchmarks.

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
