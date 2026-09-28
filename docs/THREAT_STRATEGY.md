# Threat strategy

EvidenceGate starts with the observable unit and its limits, then selects a mechanism whose output does not exceed that evidence. “Active” means registered in the current MVP; it does not mean validated as a universal detector.

## DDoS

**Observable and mechanism.** Packet/flow demand and visible TCP state can support independent measurements: SYN state, UDP and ICMP demand, fragment demand, reflection-victim context where explicitly available, apparent source diversity, and connection churn. One-way arrival counts can remain visible when replies disappear.

**Tested / negative result.** Research and controlled replay measured protocol/state mechanisms and one-way degradation. No universal threshold or model was justified. Apparent source diversity is not proof of spoofing, and demand is not victim-exhaustion truth.

**Active MVP.** Seven independent factual mechanisms (`ddos.syn_state`, `ddos.udp_demand`, `ddos.reflection_victim`, `ddos.source_diversity`, `ddos.icmp_demand`, `ddos.fragment_demand`, `ddos.connection_churn`). **ML: NOT ACTIVE.** Transparent measurements match the available facts; labels for victim impact and broad operational hard negatives are insufficient for a stronger learned claim.

**Hard negatives.** Flash crowds, legitimate high-volume services, monitoring, asymmetric visibility, NAT, and load-balancer behavior.

**Claim ceiling and missing evidence.** Observed demand/state evidence, not confirmed DDoS, victim exhaustion, impact, source identity, or spoofing. Promotion to impact claims would need independent victim-side availability/capacity truth and representative benign peak-demand captures.

## C2 / beaconing

**Observable and mechanism.** Repeated, time-stamped communication between explicit client, peer, and service roles can support bounded recurrence and timing history. Current `c2.r1` only accepts trusted `FLOW_START` events whose canonical event time equals flow start, with explicit identity and bounded state.

**Tested / negative result.** Cross-profile tests varied sharply; strong within-profile separation did not transfer uniformly. The IoT-23 M0 result fell from training AUROC 1.000 to validation 0.460, known-family test 0.025, and unseen-family test 0.244. TQH-C2 profiles also differed; strong separation in one profile did not warrant a general C2 classifier. See the experiment ledger for units and limits.

**Active MVP.** `c2.r1` emits recurrence measurement evidence. **ML: REJECTED for universal classification.** The deployed mechanism describes timing/history without calling the peer C2 or compromised.

**Hard negatives.** Software updates, telemetry, health checks, cloud/SaaS polling, API polling, remote management, and scheduled jobs.

**Claim ceiling and missing evidence.** Recurrent communication evidence, not C2, malware, compromise, or benignness. Stronger promotion needs leakage-resistant temporal and family splits, labeled benign lookalikes, independent incident truth, and validation across profiles.

## DGA and DNS tunnelling

**Observable and mechanism.** For typed DNS observations, the DGA model assesses normalized domain lexical representation. A separate DNS lane records structural and transaction evidence. Both can be produced from the same observation, but neither is fused into a tunnel or compromise verdict. Raw-PCAP DNS extraction is not implemented.

**Tested / negative result.** DGA lexical ML passed a controlled MVP human gate as `DGA-A1-M1-R1`; the evidence supports a narrow DGA-labelled resemblance meaning, with original-run traceability limitations. Held-out family degradation and broad CrUX/source-shift collisions prevent open-world accuracy claims. The frozen length/entropy/uniqueness DNS heuristic was rejected after an unseen OzymanDNS miss, a fast-tunnel miss, low-rate collisions, and lack of population false-positive evidence.

**Active MVP.** DGA lexical model (`dga.m1`) is active only when the exact verified artifact and dependency contract are available; otherwise it fails closed as unavailable. DNS-T1 structural/transaction evidence is active separately. **ML: ACTIVE for DGA lexical review only; NOT ACTIVE for DNS tunnel classification.**

**Hard negatives.** Popular domains, generated-looking but benign labels, CDNs, telemetry, tracking, service discovery, and legitimate high-entropy or long names.

**Claim ceiling and missing evidence.** DGA-labelled lexical resemblance; not malware, infection, C2, DNS tunnel, exfiltration, ownership, or intent. DNS evidence is not a tunnel verdict. Promotion needs robust family/source holdouts, population-representative benign DNS, explicit operational false-positive budgets, and independent maliciousness/tunnel truth.

## Encrypted sessions

**Observable and mechanism.** Visible TLS handshake or QUIC outer/session metadata can describe protocol context. Missing fields, ECH, loss, and partial capture reduce evidence. TLS is not QUIC; encrypted payload meaning is unavailable.

**Tested / negative result.** An annotated network dataset audit found substantial exact duplicate rows and IDs with mixed labeled/unlabeled status; diagnostic hard-negative collisions and source shift further weaken record-level classification. Records were not defensible causal session truth, so the record-level model was not promoted.

**Active MVP.** `encrypted_session.enc_a` produces visible context only. **ML: NOT ACTIVE.** Current labels and sample unit do not support a reliable payload or maliciousness interpretation.

**Hard negatives.** Browsers, software updates, CDNs, enterprise proxies, telemetry, QUIC services, and shared hosting.

**Claim ceiling and missing evidence.** Visible encrypted-session context, not malicious payload or malware. Promotion needs deduplicated, source-aware, causally identified sessions, consistent labels, representative hard negatives, and protocol-specific validation.

## Reconnaissance

**Observable and mechanism.** Destination-host breadth, destination-port breadth, host-by-port geometry, and visible TCP activity/outcome are measurable when direction and endpoint roles are available.

**Tested / negative result.** A controlled exercise contained 835 events across 16 scenario families; its projections (505 source-to-target and 330 target-to-source) were not detector-performance estimates. Matched horizontal breadth collided with authorized inventory in 24 of 28 selected cases. No recon ML was promoted.

**Active MVP.** `recon.h`, `recon.v`, `recon.2d`, and `recon.tcp` record factual breadth/activity evidence. **ML: NOT ACTIVE.** Measurements expose what was observed without inferring authorization or intent.

**Hard negatives.** Authorized inventory, vulnerability scans, monitoring fan-out, health checks, retries, service discovery, and asset management.

**Claim ceiling and missing evidence.** Scan-like network activity, not malicious intent, unauthorized access, attacker identity, or compromise. Promotion needs ground truth for authorization and intent, representative benign scanner behavior, and temporally separated evaluation.

## Data transfer / exfiltration

**Observable and mechanism.** Directional transfer magnitude can be measured from flow/packet evidence available to the sensor. The current `unusual_transfer.m1` mechanism reports magnitude; it does not decide that the transfer is unusual.

**Tested / negative result.** A six-record generated mechanics fixture verifies mechanics only. No reviewed dataset satisfied authorization and sensitivity label truth for semantic exfiltration evaluation; no semantic exfiltration model was admitted.

**Active MVP.** `unusual_transfer.m1` provides transfer-magnitude evidence. **ML: NOT ACTIVE.** The available evidence does not encode authorization, data sensitivity, or theft.

**Hard negatives.** Backups, software distribution, cloud synchronization, replication, media delivery, and authorized bulk exports.

**Claim ceiling and missing evidence.** Transfer evidence only. Transfer is not unusualness, unauthorized access, sensitive data, or theft. Promotion needs independent authorization logs, sensitivity ground truth, causal transfer records, benign bulk-transfer coverage, and a leakage-resistant split.
