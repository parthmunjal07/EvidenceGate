# Recon Controlled Resource Characterization

This is a deterministic synthetic mechanics run. It is not production traffic,
does not establish production throughput, and does not activate runtime defaults.

Reproduce from the repository root with
`python -m scripts.benchmark_recon_capacity`.

## Workload

- Observations: 1024
- Independent mechanism results: 4096
- Elapsed seconds: 20.453894
- Observations/second (this run only): 50.06
- Mechanism updates/second (this run only): 200.26

## Bounded state

- Total state entries: 1600
- Total retained events: 4096
- Serialized state payload bytes (engineering proxy): 707048
- Measured exact-set memberships: `{"h_distinct_host_memberships": 1024, "two_d_distinct_pair_memberships": 1024, "v_distinct_port_memberships": 1024}`
- Tracemalloc current/peak bytes: 3647277 / 5811943
- Per lane: `{"recon.2d": {"entries": 64, "retained_events": 1024, "serialized_payload_bytes": 95466}, "recon.h": {"entries": 256, "retained_events": 1024, "serialized_payload_bytes": 144042}, "recon.tcp": {"entries": 1024, "retained_events": 1024, "serialized_payload_bytes": 323498}, "recon.v": {"entries": 256, "retained_events": 1024, "serialized_payload_bytes": 144042}}`

## Reorder occupancy

`{"recon.2d": {"peak_per_key": 16, "peak_total": 1024, "pending_before_watermark": 1024}, "recon.h": {"peak_per_key": 4, "peak_total": 1024, "pending_before_watermark": 1024}, "recon.tcp": {"peak_per_key": 1, "peak_total": 1024, "pending_before_watermark": 1024}, "recon.v": {"peak_per_key": 4, "peak_total": 1024, "pending_before_watermark": 1024}}`

Quality gaps: `{}`
Runtime error controls: 0

## Engineering interpretation

The run supplies a measured point, not a final capacity decision. A follow-up
capacity gate should test at least 2x this key/event cardinality under the target
deployment memory limit before selecting any candidate range. No production
capacity, horizon, or reorder value is introduced by this report.
