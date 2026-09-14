# SIH26145 - EvidenceGate

**Status:** IMPLEMENTATION-AUTHORITATIVE MVP
**Scope:** Shared EvidenceGate product/runtime infrastructure only.

## Scope
This repository implements the EvidenceGate runtime infrastructure according to `MVP_IMPLEMENTATION_CONTRACT_v1.md` and `MVP_SYSTEM_RESEARCH_HANDOFF_v1.2.md`. 
It provides a single-host Python application that:
- Accepts passive/replay inputs.
- Converts inputs into immutable network observations.
- Routes each observation to zero or more relevant lanes.
- Performs independent lane admission.
- Runs bounded entity-affine state where declared.
- Persists immutable results.
- Exposes generic REST/WebSocket/UI data.

## Explicit No-Go Boundaries
The runtime **does not**:
- Decide that a threat occurred.
- Silently turn absence, loss, or an unavailable analytic into a benign result.
- Infer result permissions from status names.
- Contain a detector, threshold, feature, state key, history horizon, model, label, confidence meaning, severity mapping, or correlation score. 

## Setup
Requires Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[test]
```

## Test
To run tests (contract, integration, replay, and benchmark fixtures):
```bash
pytest
```

## Run
Currently under construction. When implemented, the application will provide a FastAPI server for the REST APIs and WebSockets and run the internal runtime state loops.
