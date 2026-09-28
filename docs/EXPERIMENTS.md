# Experiments and evidence ledger

This ledger records durable decisions, including negative results. `EXP-*` identifiers below are documentation identifiers created for this ledger; they are not claimed as historical experiment IDs. Machine-readable benchmark records are preserved in [`../benchmark_results/`](../benchmark_results/). Research-package findings are summarized at the level needed to explain current choices.

| ID | Family | Question / input contract | Baseline or evidence | Result and decision | Limitation |
|---|---|---|---|---|---|
| EXP-DDOS-01 | DDoS | Can a universal DDoS model/threshold represent one-way observed traffic? | Passive demand/state mechanisms and controlled cases | No universal threshold/model justified. **REJECTED** | No victim exhaustion or impact truth across environments |
| EXP-DDOS-02 | DDoS | Can separate factual mechanisms retain useful demand/state under replay? | Seven provider mechanisms; capacity JSON and fixtures | Mechanism evidence admitted to controlled MVP. **ADMITTED** | Review evidence only; does not prove DDoS or impact |
| EXP-C2-01 | C2 | Does an IoT-23 M0 classifier generalize across splits/families? | IoT-23 flow-based model | AUROC: train 1.000, validation .460, known-family test .025, unseen-family test .244. **REJECTED** | Split/profile transfer and dataset labeling bound the result |
| EXP-C2-02 | C2 | Do timing features transfer across TQH-C2 profiles? | TQH-C2 v1.2.0 causal episodes, K=5; 50,133 episodes | Profile performance varied; updated B had zero positive episodes; updated C AUROC .2517 / PR-AUC .394; D AUROC .9999 still had FPR .3604 at the validation-derived 1% region. Universal classifier **REJECTED** | Profile composition and operational negatives prevent broad semantics |
| EXP-C2-03 | C2 | Can recurrence/history be reported without a C2 verdict? | Explicit FLOW_START, canonical event time, roles and bounded state | `c2.r1` recurrence measurement admitted. **ADMITTED** | Periodicity also describes benign automation |
| EXP-DGA-01 | DGA | Is lexical DGA evidence suitable for a bounded controlled MVP? | DGA-A1-M1-R1; human-gated artifact and representation | Controlled lexical review use admitted. **ADMITTED** | Original-run traceability limitation remains; no production/open-world guarantee |
| EXP-DGA-02 | DGA | Does known-family separation establish unseen-family performance? | Held-out-family and source-shift validation | Degradation and CrUX collisions block broad accuracy claims. **MEASUREMENT_ONLY** | Research operating regions do not imply a deployed population rate |
| EXP-DNS-01 | DNS tunnelling | Does frozen length/entropy/uniqueness identify tunnels generally? | Transparent lexical heuristic vs tunnel observations | OzymanDNS and fast-tunnel misses, low-rate collision, no population FPR evidence; heuristic **REJECTED** | Sparse tunnel coverage and population truth |
| EXP-DNS-02 | DNS tunnelling | Can transparent structure/transaction evidence be exposed? | Typed DNS observations | Structural lane retained; no tunnel verdict. **ADMITTED** | Raw-PCAP DNS extraction is not implemented |
| EXP-ENC-01 | Encrypted | Can record-level labels support session maliciousness inference? | Annotated network records; duplicate/mixed-label audit and hard negatives | Model not promoted. **REJECTED** | Records did not provide clean causal session truth; source shift remains |
| EXP-RECON-01 | Recon | Do breadth measurements separate scans from authorized activity? | 835 controlled events / 16 families; selected matched cases | 505/330 directional projections are scenario counts; horizontal breadth collided in 24/28 selected authorized-inventory cases. ML **REJECTED** | Not a representative performance or population false-positive study |
| EXP-RECON-02 | Recon | Can host, port, geometry and visible TCP facts be measured? | Replay fixtures and four factual providers | Measurements retained for controlled MVP. **ADMITTED** | Authorization and malicious intent remain unknown |
| EXP-EXFIL-01 | Transfer | Does a dataset contain authorization and sensitivity truth for exfiltration ML? | Reviewed public/project corpus candidates | No candidate passed the full truth/authorization requirement. **INSUFFICIENT** | Semantic theft labels unavailable |
| EXP-EXFIL-02 | Transfer | Does the transfer mechanism report directional magnitude? | Six-record generated mechanics fixture | Transfer-magnitude path retained. **MEASUREMENT_ONLY** | Fixture tests mechanics, not online PCAP detection or FPR |
| EXP-CORR-01 | Cross-family | Can a learned relevance ranker be validated on independent packet-derived multi-family truth? | Research ranker concept vs available Result relationships | Ranker not promoted; current deterministic factual relations retained. **REJECTED** | Insufficient independent joint truth; no causality claim |
| EXP-PCAP-01 | Input | Can recorded classic Ethernet PCAP feed the current replay pipeline? | Offline PCAP and explicit sidecar contracts | Replay path retained. **ADMITTED** | Small replay samples; no live capture, NetFlow/IPFIX/sFlow, or raw-PCAP DNS lane |
| EXP-STREAM-01 | Streaming | What controlled offered rate passed the final acceptance workload? | `final_mvp_acceptance.json` | One 30-second run at 50 observations/s: 1,500 offered, accepted and processed; zero drops/control errors; about 0.202 s drain. **MEASUREMENT_ONLY** | Single acceptance replicate on the recorded Windows/Python/i5-13450HX environment; not an SLA/capacity promise |
| EXP-PRODUCT-01 | Product evidence | Do persisted Results support family views and cross-family review? | API/composer behavior and implementation | Independent Results, family evidence and factual links are implemented. **ADMITTED** | Presentation/linkage is not a detector metric, verdict, or learned correlation |

## Decision counts

Across the 18 entries above: **ADMITTED 7**, **MEASUREMENT_ONLY 3**, **REJECTED 7**, **DEFERRED 0**, **INSUFFICIENT 1**. These counts refer to ledger entries, not an overall threat-family score.

## Interpreting the evidence

- Controlled and generated data answer narrow mechanics or measurement questions. They do not estimate population performance unless the sampling design supports it.
- An AUROC or diagnostic false-positive operating region is not a deployed accuracy or alert rate. Sample units and split design matter.
- A rejected model or heuristic remains a useful negative result. The current product uses a simpler mechanism where that is the strongest claim the evidence supports.
- The 50 observations/s acceptance result is one recorded development run. A separate sustained benchmark candidate and other current-stack rates answer different workloads; they must not be blended into a production capacity claim.
- DGA availability depends on the exact externally held model artifact. Artifact validation and fail-closed behavior are described in [DEPLOYMENT.md](DEPLOYMENT.md).

## Public dataset references

These links identify source owners or project pages, not endorsements of EvidenceGate results: [IoT-23 dataset](https://www.stratosphereips.org/datasets-iot23), [TQH-C2 v1.2.0](https://zenodo.org/records/21523144), [OpenSetDGA benchmark](https://inseclab.uit.edu.vn/opensetdga-a-benchmark-for-open-set-domain-generation-algorithm-detection/), [CAIDA DDoS 2007 dataset](https://www.caida.org/catalog/datasets/ddos-20070804_dataset/), and [Chrome UX Report on BigQuery](https://developer.chrome.com/docs/crux/bigquery).
