# Recon Controlled Resource Characterization

This is a deterministic synthetic mechanics run. It is not production traffic,
does not establish production throughput, and does not activate runtime defaults.

Reproduce from the repository root with
`python -m scripts.benchmark_recon_capacity`.

## Workload

- Observations: 1024
- Independent mechanism results: 4096
- Elapsed seconds: 30.956534
- Observations/second (this run only): 33.08
- Mechanism updates/second (this run only): 132.31

## Bounded state

- Total state entries: 1600
- Total retained events: 4096
- Serialized state payload bytes (engineering proxy): 707048
- Measured exact-set memberships: `{"h_distinct_host_memberships": 1024, "two_d_distinct_pair_memberships": 1024, "v_distinct_port_memberships": 1024}`
- Tracemalloc current/peak bytes: 3654477 / 5705615
- Per lane: `{"recon.2d": {"entries": 64, "retained_events": 1024, "serialized_payload_bytes": 95466}, "recon.h": {"entries": 256, "retained_events": 1024, "serialized_payload_bytes": 144042}, "recon.tcp": {"entries": 1024, "retained_events": 1024, "serialized_payload_bytes": 323498}, "recon.v": {"entries": 256, "retained_events": 1024, "serialized_payload_bytes": 144042}}`

## Reorder occupancy

`{"recon.2d": {"peak_per_key": 16, "peak_total": 1024, "pending_before_watermark": 1024}, "recon.h": {"peak_per_key": 4, "peak_total": 1024, "pending_before_watermark": 1024}, "recon.tcp": {"peak_per_key": 1, "peak_total": 1024, "pending_before_watermark": 1024}, "recon.v": {"peak_per_key": 4, "peak_total": 1024, "pending_before_watermark": 1024}}`

Quality gaps: `{}`
Runtime error controls: 0

## Engineering interpretation

The run supplies a measured point, not a production-throughput claim or a final
capacity decision. An integration boundary run repeated the same 1,024-observation
workload with conservative candidate bounds of 1,024 state entries per lane,
16 retained events per key, 16 reorder events per key, and 1,024 reorder events
per lane. It retained all 4,096 mechanism events, emitted all 4,096 results, and
reported no quality gaps or runtime errors (5,704,927-byte tracemalloc peak).

Those exact values are therefore a controlled-MVP candidate inside the
demonstrated-clean envelope. They are not approved defaults. The tested 60- and
3,600-second measurement horizons and the historical/test horizons of 10, 30,
60, 300, 900, 1,800, and 3,600 seconds remain configuration horizons only; none
is a production scan threshold. Production sizing still requires deployment-
specific load and memory validation.
