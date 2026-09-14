# SIH26145 EvidenceGate Runtime (MVP)

EvidenceGate is a strictly-bounded, single-host Python runtime application designed to broker, route, admit, and persist immutable network observations for analytic lanes. 

**This repository represents the shared runtime infrastructure only. It does not contain an active scientific threat detector.**

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
