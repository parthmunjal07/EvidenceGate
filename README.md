# EvidenceGate

Passive, visibility-aware cyber-threat evidence construction for unidirectional network traffic.

EvidenceGate is a research prototype for the Smart India Hackathon 2026 problem statement SIH26145, “AI-Based Detection of Cyber Threats in Unidirectional IP Traffic.” It turns recorded passive network observations into bounded, reviewable evidence while preserving what the sensor could not see. A result supports investigation; it does not by itself establish an attack, intent, identity, or impact.

## The problem

A passive sensor may observe only one direction of a conversation. Replies, handshakes, completion, and application context may be absent because of placement, packet loss, sampling, encryption, or capture boundaries. Systems that treat missing fields as zero or assume a complete bidirectional flow can make stronger claims than the evidence supports.

EvidenceGate records visibility and quality with each observation. When required evidence is absent or degraded, the corresponding analytic degrades or becomes unavailable; missing evidence is not interpreted as benign activity.

## The solution

```text
Recorded input → canonical observations → visibility, quality and identity
 → zero-to-many threat mechanisms → independent Results → family evidence
 → deterministic investigation links → analyst workbench
```

The parser canonicalizes once, shared facts are routed early, and stateful mechanisms use bounded state. Independent mechanisms can consume one observation without collapsing their findings into a single threat score. The immutable `Result` is the scientific record. The analyst queue is a versioned presentation of evidence that merits attention, not a list of confirmed attacks.

## What is implemented

- Typed and NDJSON replay, plus offline classic Ethernet PCAP replay. There is no live NIC capture or NetFlow/IPFIX/sFlow ingestion.
- TCP, UDP, ICMP, fragment, DNS, TLS/QUIC, and flow-level observations with explicit direction, visibility, quality, and source identity where available.
- Six official threat families, represented with separate DGA and DNS lanes and independent factual DDoS mechanisms.
- Bounded C2 recurrence/history; a DGA lexical model; transparent DNS structure/transaction evidence; visible encrypted-session context; factual reconnaissance and demand/state measurements; and directional transfer magnitude.
- Persistent results in SQLite, REST and server-sent event interfaces, a browser analyst workbench, family evidence views, and deterministic factual cross-family investigation links.
- An allowlisted replay catalogue for demo inputs. Replay requests do not accept arbitrary paths or URLs.

## Threat coverage

| Family | Current MVP evidence | ML status | Claim ceiling |
|---|---|---|---|
| DDoS | Independent TCP state, protocol demand, source-diversity and connection-churn measurements | Not active | Observed demand/state; not victim exhaustion or confirmed DDoS |
| C2 / beaconing | Bounded recurrence and timing history | Not active | Recurrent communication evidence; not C2 or compromise |
| DGA | DGA-A1-M1-R1 lexical model | Active, controlled MVP | DGA-labelled lexical resemblance; not malware or infection |
| DNS tunnelling | Structural and transaction measurements | Not active | DNS structure/transaction evidence; not a tunnel verdict |
| Encrypted sessions | Visible TLS/QUIC outer and handshake context | Not active | Session context; not payload meaning or maliciousness |
| Reconnaissance | Host, port, host-by-port breadth and visible TCP activity/outcome | Not active | Scan-like activity evidence; not authorization or intent |
| Data transfer | Directional transfer magnitude | Not active | Transfer evidence; not unusualness, unauthorized access, or theft |

## Why ML is not everywhere

“AI-based” does not require a classifier for every family. Before admitting a model, the project asks what the sensor observes, what the sample unit is, whether labels represent the intended claim, whether hard negatives and leakage-resistant splits exist, and what a model adds over a transparent baseline. DGA lexical ML passed a limited admission gate for controlled MVP use, with explicit source-shift and unseen-family limits. For the other families, present evidence supports measurements, rules, bounded state, and context—not stronger learned semantics. Rejecting unsupported model claims is a scientific decision, not an unimplemented feature.

## Judge demo

Follow the 2–4 minute walkthrough in [docs/JUDGE_DEMO.md](docs/JUDGE_DEMO.md). It shows one-way visibility, one-to-many evidence routing, independent DGA and DNS evidence, bounded C2 recurrence, visible encrypted-session context, offline PCAP replay, and factual investigation links without causal claims.

## Quick start

Requires Python 3.11 or newer and Node.js 24.21 or newer. From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test,quality]"
cd frontend
npm ci
npm run build
cd ..
python -m uvicorn evidencegate.api.app:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/`. Check `http://127.0.0.1:8000/health`. For input limits, model artifact setup, public mode, persistence, and deployment, see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## Verification

```powershell
ruff check .
ruff format --check .
python -m pytest -q
python -m compileall -q evidencegate scripts
cd frontend
npm run lint
npm run format:check
npm run typecheck
npm run test:run
npm run build
```

These checks verify repository behavior; benchmark values in [benchmark_results/](benchmark_results/) are controlled development measurements, not production capacity or an SLA.

## Limitations

EvidenceGate is not a production IDS, live capture system, incident attribution service, or universal threat classifier. It does not infer benignness from absence, recover encrypted payload, establish authorization or intent, or prove impact. Each family has separate hard negatives and missing evidence; see [docs/SCIENTIFIC_BOUNDARIES.md](docs/SCIENTIFIC_BOUNDARIES.md) and [docs/THREAT_STRATEGY.md](docs/THREAT_STRATEGY.md). The architecture and current/deferred boundary are in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md); experiment decisions are in [docs/EXPERIMENTS.md](docs/EXPERIMENTS.md).
