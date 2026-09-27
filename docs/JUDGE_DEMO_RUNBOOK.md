# Judge demo runbook

Traffic Lab presents one replay as observed source traffic, canonical
observation, sensor visibility and quality, eligible analytics, independent
Results, family evidence, and factual investigation links. The five scenarios
are deterministic controlled demonstrations, not a new evaluation dataset.

| Order | Demo | Click / point to | Say | Do not claim |
| --- | --- | --- | --- | --- |
| 1 | DDoS + Recon fan-out | Run it; open Network Observations. Select an event with multiple routes, then a row with no eligible routes. Follow the Result and family stages into Investigations. | “One controlled packet episode is normalized once and can feed several independent factual measurements; some observations have no eligible route.” | A confirmed DDoS, a malicious scan, or that Recon caused DDoS. |
| 2 | One-way SYN visibility | Run it; open a packet observation and show `FORWARD_FACTS` available and `REVERSE_FACTS` unavailable. Open the limitation Result. | “The source provides forward initiation evidence, while reverse packet facts are unavailable to this sensor view.” | A completed handshake, victim response, or DDoS confirmation. |
| 3 | C2 recurrence | Run it; step through the flow observations and show the Result sourced from earlier observations, then family evidence and its factual relation. | “The recurrence measurement builds from observed flow history and preserves the exact source observations.” | C2 confirmation, common attacker, or encrypted payload content. |
| 4 | DGA + DNS | Run it; select DNS rows and show the lexical score and the independent DNS structural Result. | “The lexical model and DNS structural mechanism report separate evidence; the score is not an infection probability.” | Malware, infection, tunnelling, or intent. |
| 5 | Recorded PCAP (optional) | Run the recorded classic PCAP; show packet-level canonical fields and the completed Results, family views, and investigation links. | “This is a controlled offline packet capture replay through the same passive observation pipeline.” | Live capture, raw-PCAP DNS parsing, or production IDS throughput. |

The headline is that EvidenceGate preserves source facts and visibility, routes
each canonical observation to zero or more independent analytics, and keeps
Results immutable when composing family evidence and review links.
