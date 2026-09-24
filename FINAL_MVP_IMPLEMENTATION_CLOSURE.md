# Final MVP Implementation Closure

Status: controlled MVP implementation frozen under decision
`MVP-DEC-FINAL-ALERT-THROUGHPUT-V1` (Rachit / Control Room, approved
2026-09-23). Baseline HEAD: `745539ac58f80a902a77332cc9440410dbc41429`.
Final implementation HEAD is the M17 commit recorded in Git; this report is
part of that commit.

## Scope and runtime

Six official SIH categories are presented through seven EvidenceGate lanes:
DDoS factual mechanisms; C2-R1 recurrence measurement; DGA-A1/M1-R1 lexical
model evidence; DNS-T1 structural observation; ENC-A handshake/fingerprint
evidence; Recon H/V/2D/TCP measurements; and Exfil-M1 transfer magnitude.
The separate DGA and DNS lanes belong to the combined official DGA/DNS
category. Their Results are never fused.

The exact 16 default active targets are:

1. `ddos.syn_state`
2. `ddos.udp_demand`
3. `ddos.reflection_victim`
4. `ddos.source_diversity`
5. `ddos.icmp_demand`
6. `ddos.fragment_demand`
7. `ddos.connection_churn`
8. `c2.r1`
9. `dga.m1`
10. `dns_tunnelling.t1`
11. `encrypted_session.enc_a`
12. `recon.h`
13. `recon.v`
14. `recon.2d`
15. `recon.tcp`
16. `unusual_transfer.m1`

Passive inputs are typed NDJSON replay and incremental offline raw PCAP replay
with an explicit trusted sidecar. Canonical observations route through the
fixed target registry into mechanism plugins, bounded keyed state and
event-time reorder where required, immutable Result finalization, and
disk-backed SQLite. Queue, state, and reorder capacities are explicit and
independent. The active ML is limited to DGA-A1/M1-R1. Its Drive-owned,
untracked `DGA_M1_R1_SERIALIZED_MODEL.joblib` has SHA-256
`39da209d2cfd869dd284e10b8a07adc04826c95146712cc6854a69b9873890df`
and Drive ID `16YbGrjsC_aCluWGa8-bC0mN5DVPO_T-Y`.

The FastAPI application exposes authoritative `/results` and
`/results/{result_id}`, active `/alerts`, `/runtime`, health, allowlisted replay,
SSE persisted-result notifications, and a dashboard. `SIH_ALERT_POLICY_V1`
projects persisted Results at query time. Analyst alerts are attention records,
not confirmed malicious activity. Only `REVIEW_FINDING` enters the analyst
queue; quality, prerequisites, insufficiency, analytic unavailability, and
plugin records appear as separate statuses. `REVIEW` is analyst priority;
status `INFO` and `ATTENTION` are separate. DGA uses its actual lexical
`MODEL_SCORE`, not calibrated attack probability. Non-DGA numeric confidence
is null with a mechanism-specific statistical or observed-evidence basis.
Source Result IDs, exact claim ceilings, visibility, quality, model/governance
and provenance references survive projection. One observation may produce
multiple independent alerts without fusion.

## Controlled operating claim

On the measured development machine, the controlled MVP sustained a configured offered rate of 50 input observations/s for 30 seconds with zero input/runtime drops under the declared mixed workload.

This is the approved controlled SIH demo operating claim. M16 found 75
observations/s to be the highest repeatedly sustainable point; 100 was not
sustainable. Neither this report nor the M17 acceptance asserts production
capacity, network line rate, attack rate, or an SLA. The M17 acceptance uses
the same nine-observation mixed workload, a three-second excluded warm-up,
real DGA inference, disk-backed SQLite, and the active `/alerts` presentation
API queried during measured load. The query-time projection is outside the
ingestion hot path; the acceptance explicitly records its API read samples.

## Verification

The final post-activation measurement and regression results are recorded in
`SUSTAINED_FINAL_MVP_BENCHMARK_REPORT.md` and
`benchmark_results/final_mvp_acceptance.json`. The historical M16 sweep is
preserved in `benchmark_results/sustained_final_mvp_benchmark.json`.

The M17 measured run passed: 1,500 offered/accepted/processed observations,
50.009 actual offered observations/s, 2,837 persisted Results, zero input or
runtime drops, zero queue/state/reorder/persistence failures, peak backlog 70,
final backlog zero, backlog slope -0.029 items/s, and 0.201802-second drain.
Processing p50/p95/p99 was 186.3378/883.2264/1,017.04 ms; end-to-end evidence
p50/p95/p99 was 312.552/983.132/1,165.4749 ms. Peak RSS was 244,203,520
bytes. Active `/alerts` returned HTTP 200 before and after the measured phase;
the after-drain newest-500 projection held 411 alerts and 89 separate status
items. See the benchmark report for the transparent setup-run history.

Final regression: 439 tests passed, zero failed; `python -m compileall -q
evidencegate scripts` passed; `git diff --check` passed. The manual ASGI
application smoke ran the allowlisted `dga_lexical` and `mixed_ddos_recon`
replays against disk-backed SQLite with the verified DGA model. It returned
10 Results, 9 analyst alerts, and 1 separate status item; a projected source
Result resolved through `/results/{result_id}`. No DGA model binary is tracked.

## Limits and deferred capability

- Raw-PCAP DNS extraction is deferred; the seven-lane mixed rate uses typed
  observations.
- Live interface capture and NetFlow/IPFIX/sFlow adapters are deferred.
- Non-DGA numeric attack probability is not defined. DGA model score is not
  calibrated maliciousness probability.
- The evidence cannot establish malware, authorization, sensitive content,
  theft, or intent beyond each mechanism's exact claim ceiling.
- Measurements are specific to one development machine and controlled
  fixtures; there is no production capacity claim or production SLA.
