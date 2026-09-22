# PCAP Input and Current-Stack Benchmark Report

> **PRE-DGA / CONTROLLED MVP / NOT PRODUCTION THROUGHPUT**

## Parser choice

The production adapter uses `dpkt>=1.9.8,<2` (BSD-3-Clause). It is a small,
established parser with an iterator-based classic-PCAP reader and direct
Ethernet, IPv4, TCP, UDP, and ICMP support. Scapy was not needed because packet
construction, active networking, interface control, and its larger dependency
surface are outside this passive replay scope. PcapPlusPlus bindings were not
needed because the Python-only `dpkt` surface covers the admitted facts.
Hand-built bytes exist only in `scripts/generate_pcap_fixtures.py`, which is
explicitly a test-fixture generator.

## Source and canonical contract

`PcapReplaySource` opens an existing classic-PCAP file read-only and yields one
`ReplaySourceRecord` per packet in file order. It does not cache the capture.
Packet position starts at 1 and increases monotonically. Capture timestamps are
timezone-aware UTC event times; `ReplayRunner` supplies an independent current
ingest time. Positive replay speed uses capture-time spacing, while capacity
characterization uses speed 0.

Each record passes through the existing `ReplayCanonicalizer`,
`PacketCanonicalBuilder`, visibility/quality merge, router, default runtime,
finalizer, and SQLite writer. The raw reference is bounded to
`pcap:<source-id>:packet:<position>` and no packet payload bytes enter the
canonical payload or results.

Supported facts are IPv4 addresses, protocol number, IP/captured length, TCP
and UDP ports, TCP flags, TCP sequence/acknowledgement integers, ICMP type/code,
IPv4 fragment offset/more-fragments facts using `DDOS_FRAGMENT_FACT_V1`, capture
timestamp, and bounded raw reference. Ethernet is the admitted link type. IPv6
and non-Ethernet frames fail explicitly for this MVP. Malformed/truncated input
raises a location-aware replay validation error; it is never treated as an
ordinary observation.

## Direction, visibility, roles, and quality

The trusted sidecar declares optional A-side and B-side IPv4 networks. Only
A-to-B becomes `FORWARD` and B-to-A becomes `REVERSE`; all other tuples are
`UNKNOWN`. No private-address, port, flag, or endpoint-order heuristic exists.
Source visibility is separately declared as `BOTH`, `FORWARD`, `REVERSE`, or
`UNKNOWN`, so a bidirectional source keeps BOTH visibility on each packet while
packet direction changes.

Endpoint `initiator_id`/`target_id` roles and target/protocol/port
`service_id` mappings are attached only when explicitly declared. Missing roles
remain missing and affected lanes fail closed. `DDOS_REFLECTION_FACT_V1` can be
attached only by a strict packet-position sidecar entry; generic UDP does not
route to DDOS-CV. Packet loss, sampling, and capture gaps default to unknown in
the controlled PCAP manifests; successful parsing is explicitly declared
clear. A PCAP file is not treated as proof of perfect capture quality.

## Parity and product integration

The controlled private-network fixtures contain a complete TCP handshake, an
incomplete SYN, a retransmitted SYN, mixed DDoS/Recon SYN activity, UDP demand,
ICMP, a fragmented IPv4 datagram, a one-way projection, and explicitly declared
reflection shape. No public endpoint or active traffic is involved. The typed
NDJSON parity bundle and raw PCAP produce equal canonical packet facts,
direction, roles, visibility, quality, and router target sets. End-to-end tests
exercise DDOS-A/B/CV/D/E2/E3 and RECON-H/V/2D/TCP, including exact SYN
retransmission recognition.

The allowlisted `raw_pcap_ddos_recon` dashboard scenario executes the actual
PCAP adapter through runtime, SQLite, REST-visible results, and persisted-result
notifications. Public replay accepts only scenario IDs—never paths, uploads,
URLs, or network locations. `/runtime` additively reports
`TYPED_NDJSON_REPLAY` and `RAW_PCAP_REPLAY`; replay status reports its source
type.

DNS message extraction was inspected but deferred: `dpkt` can expose basic DNS
fields, but introducing packet-to-multiple-observation DNS semantics and parser
provenance was not necessary for the DDoS/Recon PCAP goal. TLS/QUIC decryption
and parsing, live capture, NetFlow, IPFIX, and sFlow are deferred as future
`InputSource` implementations.

## Real current-stack characterization

`scripts/benchmark_current_stack.py` uses both equivalent typed NDJSON and raw
PCAP sources with the real canonicalizer, default 16 targets, routing, mechanism
state, finalization, and disk-backed SQLite. It records environment/dependency
versions, source and lane configuration, separate pipeline counters, persist
latency percentiles, RSS, state/reorder occupancy, database size, quality gaps,
capacity events, and drops. The generated artifacts are:

- `benchmark_results/current_stack_real_benchmark.json`
- `CURRENT_STACK_REAL_BENCHMARK_REPORT.md`

Both measured fixture runs read 11 inputs, emitted 11 canonical observations,
routed 42 mechanism updates, and finalized/persisted 35 results with zero input
drops, runtime-work drops, quality gaps, state-capacity events, or reorder-
capacity events. Exact wall time, persist p50/p95/p99, RSS, and SQLite size are
preserved in the artifacts. These short single-host results are descriptive
only. They are not a sustainable rate, production sizing result, final-stack
result, or headline throughput claim, and the harness must be rerun after DGA
model integration.

The historical dummy-plugin, in-memory SQLite, intentionally dropping benchmark
remains in the repository but is marked **SUPERSEDED FOR FINAL THROUGHPUT
CLAIMS** and is not cited as current evidence.
