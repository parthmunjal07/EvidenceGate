# Final MVP demo script (about 105 seconds)

## Before the demo

- Start the EvidenceGate app and open **Traffic Lab**. The backend resolves the verified model from the canonical repository-local artifact path when present; an explicit path or `EVIDENCEGATE_DGA_MODEL` takes precedence.
- Confirm runtime status reports `VERIFIED_READY` and the scenario-level DGA model notice is absent. If verification fails, show the unavailable status and do not promise a lexical score.
- Use the prepared scenarios only. This MVP replays typed NDJSON and offline PCAP; it does not capture live traffic.

## Run of show

| Time | Action and narration |
| --- | --- |
| 0:00–0:10 | **Passive constraint.** “EvidenceGate replays prepared passive inputs. It does not capture or inject traffic.” Point to the source type. |
| 0:10–0:30 | **Records to observations.** Start **C2 recurrence measurement**. Point to source records, canonical observations, and the observation’s visibility and quality facts. “Each accepted record is canonicalized once; analytics receive the observation with its visibility and quality constraints.” |
| 0:30–0:50 | **Zero-to-many routing.** Point to the same observation’s independently selected C2 and transfer analytics when both routes appear. “One observation can route to multiple analytics when each analytic’s real predicate admits it.” The separate **DGA lexical model evidence** QA proves independent DNS T1 and DGA M1 routes on one DNS observation. |
| 0:50–1:05 | **Mechanism-owned readiness.** Point to the analytic status reported by runtime telemetry. “Each stateful mechanism reports its own readiness; the interface does not invent a shared threshold.” |
| 1:05–1:20 | **Independent persisted Results.** Point to New Evidence, then open a result in Evidence. “Each analytic persists its own immutable Result. `/results` is the evidence authority; the runtime trace only explains the live presentation.” |
| 1:20–1:35 | **Family evidence and factual investigation.** In the mixed DDoS/Recon replay, show two family evidence views and their shared-observation link. “These mechanism Results remain independent. EvidenceGate composes related Results inside a family without averaging or rewriting them. The cross-family link supports joint investigation; it does not claim causality or a common attacker.” |
| 1:20–1:35 | **One-way missing evidence.** Run **One-way SYN visibility**. Show the forward observation, visibility limitation, and insufficient-evidence Result. “The reverse evidence is missing, so the runtime preserves that limitation.” |
| 1:35–1:45 | **Analyst interpretation.** Open the Analyst Queue item and show supported evidence and claim limits. “EvidenceGate turns passive traffic into defensible evidence without weakening the network boundary.” |

## Demo guardrails

- Describe counts as source records, observations, and persisted Results; use packets only for the PCAP source where packet counting is confirmed.
- Treat readiness labels as runtime-reported states. The visual path advances only when corresponding telemetry arrives.
- For stateful lineage, use the Result’s complete `source_observation_ids`; a triggering observation alone does not stand for the full evidence history.
- A DGA score is a model score for DGA-labelled lexical resemblance, not an attack probability.
- Describe review items as analyst attention, not confirmed attacks. Do not infer intent, ownership, malware, or maliciousness from a factual measurement.
- If a branch or limitation does not appear for the selected input, report what the runtime actually shows; do not imply that a result was expected.
- Keep the architecture/implementation matrix available for questions about deferred live capture, flow-export inputs, correlation ML, or distributed processing.
