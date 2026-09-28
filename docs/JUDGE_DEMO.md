# Judge demo: 2–4 minutes

The demo is a guided replay through the analyst workbench. Use the current allowlisted scenarios shown by the application; the exact labels may change with the release. Clear or reset the workspace between scenarios if the screen contains prior evidence.

## Walkthrough

1. **Frame the constraint (15 seconds).** Explain that a passive sensor may see only one direction. EvidenceGate preserves visibility and missing fields instead of treating them as zeros.
2. **Mixed DDoS + Recon (30 seconds).** Replay the mixed scenario. Point to one observation routed to multiple independent factual mechanisms, then show independent Results, family evidence, and related investigation items.
3. **One-way SYN (20 seconds).** Replay the forward-only case. Show visible arrival/state facts and the missing reverse evidence. State that this is not a victim-impact verdict.
4. **DGA + DNS (30 seconds).** Replay the typed DNS scenario. Show the lexical DGA review result alongside separate DNS structural/transaction evidence. The two lanes do not fuse into a tunnel or malware conclusion. DGA requires the exact local artifact; without it, the DGA analytic should report unavailable.
5. **C2 recurrence (20 seconds).** Replay repeated flow starts with explicit roles. Show bounded recurrence/history and explain that periodicity is also common in updates and monitoring.
6. **Encrypted session (15 seconds).** Show visible handshake/outer metadata and call out that encrypted payload meaning is not available.
7. **Recorded PCAP (20 seconds).** Replay the bundled offline classic PCAP scenario to show packet-derived ingestion. It is a small recorded sample; DNS extraction from raw PCAP is not part of this demo.
8. **Close on investigation (15 seconds).** Return to related Results. Describe the relation as factual review support, not causality, common attacker, or attack-chain reconstruction.

## Suggested closing

> “EvidenceGate tells the analyst what was observed and what the sensor could not establish.”

## If the DGA artifact is unavailable

Continue the demo and show the unavailable state if present. Explain that the service does not substitute a different model or convert unavailability into a negative finding. Use the deployment guide to check the exact artifact contract; do not claim that the DGA result is active unless the UI reports readiness.

## Screenshots

Pending: this environment exposes no browser surface for a fresh capture. No historical screenshots are used. Capture current-build images under `docs/assets/` when browser access is available.

## Safe explanation for judges

EvidenceGate is an evidence-construction prototype for one-way traffic. It is not a universal classifier or production IDS. The strongest demo is the trace from observation to independent mechanism evidence to analyst review, including an explicit missing-evidence boundary.
