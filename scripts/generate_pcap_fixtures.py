#!/usr/bin/env python3
"""TEST FIXTURE GENERATOR ONLY — construct deterministic offline private PCAPs."""
from __future__ import annotations

import json
import asyncio
from dataclasses import asdict
from pathlib import Path

import dpkt

from evidencegate.ingest.pcap import PcapReplaySource


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "pcap"
BASE = 1_767_225_600.0  # 2026-01-01T00:00:00Z


def address(value: str) -> bytes:
    return bytes(int(part) for part in value.split("."))


def ethernet(ip: dpkt.ip.IP) -> bytes:
    frame = dpkt.ethernet.Ethernet(
        dst=b"\x02\x00\x00\x00\x00\x02",
        src=b"\x02\x00\x00\x00\x00\x01",
        type=dpkt.ethernet.ETH_TYPE_IP,
        data=ip,
    )
    return bytes(frame)


def tcp(src: str, dst: str, sport: int, dport: int, flags: int, seq: int, ack: int = 0) -> bytes:
    segment = dpkt.tcp.TCP(sport=sport, dport=dport, flags=flags, seq=seq, ack=ack)
    segment.off = 5
    packet = dpkt.ip.IP(src=address(src), dst=address(dst), p=dpkt.ip.IP_PROTO_TCP, ttl=64, id=seq & 0xFFFF, data=segment)
    packet.len = 20 + len(segment)
    return ethernet(packet)


def udp(src: str, dst: str, sport: int, dport: int, payload: bytes = b"fixture", *, ip_id: int = 1, more_fragments: bool = False) -> bytes:
    datagram = dpkt.udp.UDP(sport=sport, dport=dport, data=payload)
    datagram.ulen = 8 + len(payload)
    packet = dpkt.ip.IP(src=address(src), dst=address(dst), p=dpkt.ip.IP_PROTO_UDP, ttl=64, id=ip_id, data=datagram)
    packet.mf = 1 if more_fragments else 0
    packet.len = 20 + len(datagram)
    return ethernet(packet)


def icmp(src: str, dst: str) -> bytes:
    message = dpkt.icmp.ICMP(type=8, code=0, data=dpkt.icmp.ICMP.Echo(id=1, seq=1, data=b"fixture"))
    packet = dpkt.ip.IP(src=address(src), dst=address(dst), p=dpkt.ip.IP_PROTO_ICMP, ttl=64, id=88, data=message)
    packet.len = 20 + len(message)
    return ethernet(packet)


def unknown_ip(src: str, dst: str) -> bytes:
    packet = dpkt.ip.IP(src=address(src), dst=address(dst), p=99, ttl=64, id=99, data=b"\x00")
    packet.len = 21
    return ethernet(packet)


def manifest(packet_count: int, visibility: str, reflection: dict[str, object]) -> dict[str, object]:
    sources = [f"10.0.0.{item}" for item in range(10, 17)]
    return {
        "schema_version": "evidencegate-pcap-manifest-v1",
        "source_id": f"controlled-raw-pcap-{visibility.lower()}",
        "capture_file": "capture.pcap",
        "capture_start": "2026-01-01T00:00:00Z",
        "capture_end": "2026-01-01T00:00:03Z",
        "packet_count": packet_count,
        "visibility": visibility,
        "quality": {
            "packet_loss": "UNKNOWN", "sampling": "UNKNOWN",
            "parser": "CLEAR", "capture_gap": "UNKNOWN",
        },
        "direction_policy": {
            "a_networks": ["10.0.0.0/24"], "b_networks": ["10.0.1.0/24"],
        },
        "endpoint_roles": {
            **{item: ["initiator_id"] for item in sources},
            "10.0.1.10": ["target_id"],
        },
        "services": [
            {"target_address": "10.0.1.10", "protocol": 6, "port": 443, "service_id": "service/https"},
            {"target_address": "10.0.1.10", "protocol": 6, "port": 22, "service_id": "service/ssh"},
            {"target_address": "10.0.1.10", "protocol": 17, "port": 53, "service_id": "service/dns-udp"},
            {"target_address": "10.0.1.10", "protocol": 17, "port": 123, "service_id": "service/ntp-udp"},
        ],
        "reflection_facts": reflection,
    }


def write_fixture(name: str, packets: list[tuple[float, bytes]], sidecar: dict[str, object]) -> None:
    directory = FIXTURES / name
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "capture.pcap").open("wb") as handle:
        writer = dpkt.pcap.Writer(handle, linktype=dpkt.pcap.DLT_EN10MB)
        writer.writepkts(packets)
        writer.close()
    (directory / "manifest.json").write_text(
        json.dumps(sidecar, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


async def write_typed_parity() -> None:
    """Materialize the same controlled facts as typed NDJSON for parity checks."""
    pcap_bundle = FIXTURES / "raw_ddos_recon"
    source = PcapReplaySource(pcap_bundle / "capture.pcap", pcap_bundle / "manifest.json")
    source_manifest = await source.open()
    records = []
    try:
        async for item in source.records():
            records.append({
                "schema_version": "evidencegate-replay-record-v1",
                "position": item.position,
                "timestamp": item.timestamp.isoformat().replace("+00:00", "Z"),
                "finality": item.finality.value,
                "observation_type": item.observation_type.value,
                "payload": asdict(item.raw_data),
                "declared_observed_fields": list(item.declared_observed_fields),
                "role_assignments": [
                    {"identifier": role.identifier, "role": role.role, "basis": role.basis.value}
                    for role in item.role_assignments
                ],
                "canonicalization_options": {},
                "wire_direction": item.wire_direction.value,
            })
    finally:
        await source.close()
    bundle = ROOT / "tests" / "fixtures" / "replay" / "raw_ddos_recon_parity"
    bundle.mkdir(parents=True, exist_ok=True)
    replay_manifest = {
        "schema_version": "evidencegate-replay-manifest-v1",
        "source_id": "controlled-typed-parity",
        "source_kind": "DERIVED",
        "input_observation_contract": "REPLAY_TYPED_V1",
        "timestamp_semantics": "SOURCE_EVENT_TIME",
        "direction_basis": source_manifest.direction_basis.value,
        "wire_direction": "UNKNOWN",
        "visibility": {
            "available": ["FORWARD_FACTS", "REVERSE_FACTS"],
            "unavailable": [], "degraded": [],
        },
        "quality": {
            "packet_loss": "UNKNOWN", "sampling": "UNKNOWN",
            "parser": "CLEAR", "capture_gap": "UNKNOWN",
        },
        "event_time_order": "NONDECREASING", "record_count": len(records),
        "capture_start": "2026-01-01T00:00:00Z", "capture_end": "2026-01-01T00:00:03Z",
    }
    (bundle / "manifest.json").write_text(json.dumps(replay_manifest, sort_keys=True) + "\n", encoding="utf-8")
    (bundle / "records.ndjson").write_text(
        "".join(json.dumps(item, sort_keys=True) + "\n" for item in records), encoding="utf-8"
    )


def main() -> None:
    target = "10.0.1.10"
    mixed = [
        (BASE + 0.00, tcp("10.0.0.10", target, 50000, 443, dpkt.tcp.TH_SYN, 100)),
        (BASE + 0.01, tcp("10.0.0.10", target, 50000, 443, dpkt.tcp.TH_SYN, 100)),
        (BASE + 0.02, tcp(target, "10.0.0.10", 443, 50000, dpkt.tcp.TH_SYN | dpkt.tcp.TH_ACK, 200, 101)),
        (BASE + 0.03, tcp("10.0.0.10", target, 50000, 443, dpkt.tcp.TH_ACK, 101, 201)),
        (BASE + 0.10, tcp("10.0.0.11", target, 50001, 443, dpkt.tcp.TH_SYN, 300)),
        (BASE + 0.20, tcp("10.0.0.12", target, 50002, 22, dpkt.tcp.TH_SYN, 400)),
        (BASE + 0.30, udp("10.0.0.13", target, 53000, 53)),
        (BASE + 0.40, icmp("10.0.0.14", target)),
        (BASE + 0.50, udp("10.0.0.15", target, 54000, 53, b"fragment", ip_id=500, more_fragments=True)),
        (BASE + 1.20, udp("10.0.0.16", target, 123, 123, b"declared response")),
        (BASE + 3.00, unknown_ip("10.0.0.16", target)),
    ]
    write_fixture(
        "raw_ddos_recon", mixed,
        manifest(len(mixed), "BOTH", {
            "10": {
                "fact_contract": "DDOS_REFLECTION_FACT_V1",
                "response_like": True,
                "protocol_context": "controlled-ntp-response",
            }
        }),
    )
    forward = [item for index, item in enumerate(mixed, 1) if index not in {3}]
    write_fixture("one_way", forward, manifest(len(forward), "FORWARD", {}))
    asyncio.run(write_typed_parity())


if __name__ == "__main__":
    main()
