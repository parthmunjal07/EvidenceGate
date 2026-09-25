# Final MVP demo script (about 105 seconds)

## Before the demo

- Start the EvidenceGate app and open **Traffic Lab**.
- Confirm the runtime is online. If the DGA model is unavailable, leave the model notice visible and do not promise a lexical score.
- Use the prepared scenarios only. This MVP replays typed NDJSON and offline PCAP; it does not capture live traffic.

## Run of show

| Time | Action and narration |
| --- | --- |
| 0:00–0:15 | **Traffic Lab.** “This is a passive replay runtime. I’m selecting a prepared mixed DDoS and Recon source. These are supplied records, not generated packets.” Point to source type and replay rate. Start **DDoS + Recon TCP**. |
| 0:15–0:40 | **Follow the live workbench.** Point to records read and observations as they update. “Each accepted source record is canonicalized once. The observation then carries its own visibility and quality facts.” Point to the actual observation feed and path stages as telemetry arrives. |
| 0:40–0:58 | **Show routing.** Point to the eligible analytics for the latest observation. If multiple branches appear, follow each branch and explain that the router selected each lane independently. “The runtime evaluates the branches reached by this observation; it does not assume every analytic applies.” |
| 0:58–1:17 | **Show readiness and independent results.** Point to each analytic’s reported readiness and the New Evidence feed. “Stateful mechanisms report their own readiness. These Results are persisted records, and remain independent even when they came from the same observation.” Open Evidence if a detail is useful. |
| 1:17–1:34 | **Show missing evidence.** Return to Traffic Lab and run **One-way SYN visibility**. Point to the resulting limitation when present. “The source is one-way, so reverse evidence is unavailable. The runtime surfaces that limitation instead of suggesting the missing evidence was observed.” |
| 1:34–1:45 | **Close on analyst interpretation.** Open a persisted result or Analyst Queue item. “The analyst view summarizes what was observed, what evidence conditions apply, and what the result does not establish.” |

## Demo guardrails

- Describe counts as source records, observations, and persisted Results; use packets only for the PCAP source where packet counting is confirmed.
- Treat readiness labels as runtime-reported states. The visual path advances only when corresponding telemetry arrives.
- Describe review items as analyst attention, not confirmed attacks. Do not infer intent, ownership, malware, or maliciousness from a factual measurement.
- If a branch or limitation does not appear for the selected input, report what the runtime actually shows; do not imply that a result was expected.
- Keep the architecture/implementation matrix available for questions about deferred live capture, flow-export inputs, correlation ML, or distributed processing.
