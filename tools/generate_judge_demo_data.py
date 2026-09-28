#!/usr/bin/env python3
"""Regenerate deterministic, safe, runtime-owned judge demo inputs."""

from __future__ import annotations

import json
from pathlib import Path

import dpkt


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "evidencegate" / "demo_data"
BASE_TIME = "2026-09-27T05:30:{second:02d}Z"


def manifest(
    source_id: str,
    semantics: str,
    direction_basis: str,
    visibility: dict[str, list[str]],
    quality: dict[str, str],
    count: int,
    *,
    start: str | None = None,
    end: str | None = None,
) -> dict:
    value = {
        "schema_version": "evidencegate-replay-manifest-v1",
        "source_id": source_id,
        "source_kind": "DERIVED",
        "input_observation_contract": "REPLAY_TYPED_V1",
        "timestamp_semantics": semantics,
        "direction_basis": direction_basis,
        "wire_direction": "FORWARD",
        "visibility": visibility,
        "quality": quality,
        "event_time_order": "NONDECREASING",
        "record_count": count,
    }
    if start:
        value["capture_start"] = start
    if end:
        value["capture_end"] = end
    return value


def packet_record(
    position: int,
    timestamp: str,
    src: str,
    dst: str,
    sport: int | None,
    dport: int | None,
    protocol: int,
    flags: list[str] | None,
    *,
    ip_length: int = 40,
    role_service: str | None = None,
) -> dict:
    payload = {
        "lengths": {"ip": ip_length},
        "observed_l2_facts": {},
        "observed_l3_facts": {},
        "observed_l4_facts": {"protocol": protocol},
        "src_address": src,
        "dst_address": dst,
        "src_port": sport,
        "dst_port": dport,
        "flags": flags,
        "sequence_facts": None,
        "fragmentation": None,
        "raw_reference": None,
        "protocol": protocol,
    }
    present = ["lengths", "protocol", "observed_l4_facts", "src_address", "dst_address"]
    if sport is not None:
        present += ["src_port", "dst_port"]
    if flags is not None:
        present.append("flags")
    roles = [
        {"identifier": src, "role": "initiator_id", "basis": "SOURCE_DECLARED_ROLE"},
        {"identifier": dst, "role": "target_id", "basis": "SOURCE_DECLARED_ROLE"},
    ]
    if role_service:
        roles.append(
            {"identifier": role_service, "role": "service_id", "basis": "SOURCE_DECLARED_ROLE"}
        )
    return {
        "schema_version": "evidencegate-replay-record-v1",
        "position": position,
        "timestamp": timestamp,
        "finality": "CURRENT",
        "observation_type": "PACKET",
        "payload": payload,
        "declared_observed_fields": present,
        "role_assignments": roles,
        "canonicalization_options": {},
    }


def flow_record(
    position: int,
    timestamp: str,
    start: str,
    end: str,
    client: str,
    peer: str,
    peer_port: int,
    byte_count: int,
) -> dict:
    payload = {
        "flow_id_basis": "controlled-flow-record",
        "endpoints": [client, peer],
        "protocol": 6,
        "start_time": start,
        "end_time": end,
        "export_time": end,
        "supplied_directional_counters": {"bytes_c2s": byte_count},
        "exporter_semantics": "controlled-demo-exporter",
        "sampling": None,
        "documented_end_state": None,
    }
    roles = [
        {"identifier": "client-a", "role": "client_id", "basis": "SOURCE_DECLARED_ROLE"},
        {"identifier": peer, "role": "peer_id", "basis": "SOURCE_DECLARED_ROLE"},
        {"identifier": str(peer_port), "role": "peer_port", "basis": "SOURCE_DECLARED_ROLE"},
    ]
    return {
        "schema_version": "evidencegate-replay-record-v1",
        "position": position,
        "timestamp": timestamp,
        "finality": "TERMINAL",
        "observation_type": "FLOW",
        "payload": payload,
        "declared_observed_fields": [
            "flow_id_basis",
            "endpoints",
            "protocol",
            "start_time",
            "end_time",
            "export_time",
            "supplied_directional_counters",
            "exporter_semantics",
        ],
        "role_assignments": roles,
        "canonicalization_options": {},
    }


def dns_record(
    position: int, second: int, qname: str, qtype: str, message_length: int, flow: str
) -> dict:
    minute, second = divmod(second, 60)
    payload = {
        "flow_reference": flow,
        "qr_state_decoded": True,
        "transaction_id": 26145 + position,
        "qname": qname,
        "qtype": qtype,
        "qclass": "IN",
        "rcode": None,
        "answers": None,
        "transport": "UDP",
        "truncation": False,
        "raw_qname_ref": f"controlled-dns-record-{position}",
        "parser_version": "controlled-demo-parser-v1",
        "parser_status": "OK",
        "message_length": message_length,
    }
    return {
        "schema_version": "evidencegate-replay-record-v1",
        "position": position,
        "timestamp": f"2026-09-27T05:{30 + minute:02d}:{second:02d}Z",
        "finality": "CURRENT",
        "observation_type": "DNS",
        "payload": payload,
        "declared_observed_fields": [
            "flow_reference",
            "qr_state_decoded",
            "transaction_id",
            "qname",
            "qtype",
            "qclass",
            "transport",
            "truncation",
            "raw_qname_ref",
            "parser_version",
            "parser_status",
            "message_length",
        ],
        "role_assignments": [],
        "canonicalization_options": {"clear_dns_fields": True},
    }


def write_bundle(
    name: str,
    source_id: str,
    records: list[dict],
    *,
    semantics: str,
    direction_basis: str,
    visibility: dict[str, list[str]],
    quality: dict[str, str],
    start: str | None = None,
    end: str | None = None,
) -> None:
    folder = DATA / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "manifest.json").write_text(
        json.dumps(
            manifest(
                source_id,
                semantics,
                direction_basis,
                visibility,
                quality,
                len(records),
                start=start,
                end=end,
            ),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (folder / "records.ndjson").write_text(
        "".join(
            json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n" for record in records
        ),
        encoding="utf-8",
    )


def ip(value: str) -> bytes:
    return bytes(map(int, value.split(".")))


def ethernet(packet: dpkt.ip.IP) -> bytes:
    return bytes(
        dpkt.ethernet.Ethernet(
            dst=b"\x02\x00\x00\x00\x00\x02",
            src=b"\x02\x00\x00\x00\x00\x01",
            type=dpkt.ethernet.ETH_TYPE_IP,
            data=packet,
        )
    )


def tcp(src: str, dst: str, sport: int, dport: int, flags: int, sequence: int) -> bytes:
    segment = dpkt.tcp.TCP(sport=sport, dport=dport, flags=flags, seq=sequence)
    segment.off = 5
    packet = dpkt.ip.IP(
        src=ip(src), dst=ip(dst), p=dpkt.ip.IP_PROTO_TCP, ttl=64, id=sequence & 0xFFFF, data=segment
    )
    packet.len = 20 + len(segment)
    return ethernet(packet)


def udp(src: str, dst: str, sport: int, dport: int, sequence: int) -> bytes:
    segment = dpkt.udp.UDP(sport=sport, dport=dport, data=b"controlled-observation")
    segment.ulen = 8 + len(segment.data)
    packet = dpkt.ip.IP(
        src=ip(src), dst=ip(dst), p=dpkt.ip.IP_PROTO_UDP, ttl=64, id=sequence, data=segment
    )
    packet.len = 20 + len(segment)
    return ethernet(packet)


def icmp(src: str, dst: str, sequence: int) -> bytes:
    packet = dpkt.ip.IP(
        src=ip(src),
        dst=ip(dst),
        p=dpkt.ip.IP_PROTO_ICMP,
        ttl=64,
        id=sequence,
        data=dpkt.icmp.ICMP(type=8, code=0),
    )
    packet.len = 20 + len(packet.data)
    return ethernet(packet)


def unknown(src: str, dst: str, sequence: int) -> bytes:
    packet = dpkt.ip.IP(src=ip(src), dst=ip(dst), p=99, ttl=64, id=sequence, data=b"\x00")
    packet.len = 21
    return ethernet(packet)


def write_pcap() -> None:
    base = 1_790_476_200.0  # 2026-09-27T05:30:00Z
    target = "192.0.2.10"
    sources = [f"198.51.100.{n}" for n in range(10, 19)]
    specs: list[tuple[float, bytes]] = []
    syns = [
        (10, 50000, 443),
        (11, 50001, 443),
        (12, 50002, 443),
        (13, 50003, 22),
        (14, 50004, 22),
        (15, 50005, 80),
        (16, 50006, 8443),
        (17, 50007, 443),
        (18, 50008, 25),
    ]
    for i, (host, sport, port) in enumerate(syns):
        specs.append(
            (
                base + i * 0.1,
                tcp(f"198.51.100.{host}", target, sport, port, dpkt.tcp.TH_SYN, 1000 + i),
            )
        )
    specs += [
        (base + 1.1, tcp(target, sources[0], 443, 50000, dpkt.tcp.TH_SYN | dpkt.tcp.TH_ACK, 2000)),
        (base + 1.2, udp(sources[1], target, 53001, 53, 11)),
        (base + 1.3, udp(sources[2], target, 53123, 123, 12)),
        (base + 1.4, icmp(sources[3], target, 13)),
        (base + 1.5, unknown(sources[4], target, 14)),
        (base + 1.6, icmp(sources[5], "192.0.2.11", 15)),
        (base + 1.7, tcp(sources[6], "192.0.2.11", 50106, 9443, dpkt.tcp.TH_SYN, 1016)),
        (base + 1.8, udp(sources[7], "192.0.2.11", 53118, 7777, 18)),
        (base + 1.9, unknown(sources[8], "192.0.2.11", 19)),
    ]
    folder = DATA / "raw_pcap_ddos_recon_v2"
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / "capture.pcap").open("wb") as stream:
        writer = dpkt.pcap.Writer(stream, linktype=dpkt.pcap.DLT_EN10MB)
        writer.writepkts(specs)
        writer.close()
    sidecar = {
        "schema_version": "evidencegate-pcap-manifest-v1",
        "source_id": "judge-controlled-raw-pcap-v2",
        "capture_file": "capture.pcap",
        "capture_start": "2026-09-27T05:30:00Z",
        "capture_end": "2026-09-27T05:30:02Z",
        "packet_count": len(specs),
        "visibility": "BOTH",
        "quality": {
            "packet_loss": "UNKNOWN",
            "sampling": "UNKNOWN",
            "parser": "CLEAR",
            "capture_gap": "UNKNOWN",
        },
        "direction_policy": {"a_networks": ["198.51.100.0/24"], "b_networks": ["192.0.2.0/24"]},
        "endpoint_roles": {
            **{host: ["initiator_id"] for host in sources},
            "192.0.2.10": ["target_id"],
            "192.0.2.11": ["target_id"],
        },
        "services": [
            {
                "target_address": "192.0.2.10",
                "protocol": 6,
                "port": 443,
                "service_id": "service/https",
            },
            {
                "target_address": "192.0.2.10",
                "protocol": 6,
                "port": 22,
                "service_id": "service/ssh",
            },
            {
                "target_address": "192.0.2.10",
                "protocol": 6,
                "port": 80,
                "service_id": "service/http",
            },
            {
                "target_address": "192.0.2.10",
                "protocol": 6,
                "port": 25,
                "service_id": "service/smtp",
            },
            {
                "target_address": "192.0.2.10",
                "protocol": 17,
                "port": 53,
                "service_id": "service/dns-udp",
            },
            {
                "target_address": "192.0.2.10",
                "protocol": 17,
                "port": 123,
                "service_id": "service/ntp-udp",
            },
        ],
        "reflection_facts": {},
    }
    (folder / "manifest.json").write_text(
        json.dumps(sidecar, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def main() -> None:
    clear_quality = {key: "CLEAR" for key in ("packet_loss", "sampling", "parser", "capture_gap")}
    limited_quality = {**clear_quality, "packet_loss": "UNKNOWN", "capture_gap": "UNKNOWN"}
    packet_vis = {
        "available": ["PACKET_FACTS", "FORWARD_FACTS"],
        "unavailable": ["REVERSE_FACTS"],
        "degraded": [],
    }

    mixed_specs = [
        (10, 50000, 443, 6, ["SYN"], "service/https"),
        (11, 50001, 443, 6, ["SYN"], "service/https"),
        (12, 50002, 443, 6, ["SYN"], "service/https"),
        (13, 50003, 22, 6, ["SYN"], "service/ssh"),
        (14, 50004, 80, 6, ["SYN"], "service/http"),
        (15, 50005, 443, 6, ["SYN"], "service/https"),
        (16, 50006, 25, 6, ["SYN"], "service/smtp"),
        (17, 53017, 53, 17, None, "service/dns-udp"),
        (18, None, None, 1, None, None),
        (19, None, None, 99, None, None),
        (20, 50020, 8443, 6, ["SYN"], "service/tcp-8443"),
        (21, 53021, 123, 17, None, "service/ntp-udp"),
    ]
    mixed = [
        packet_record(
            i,
            f"2026-09-27T05:30:{i - 1:02d}Z",
            f"198.51.100.{host}",
            "192.0.2.10",
            sport,
            dport,
            proto,
            flags,
            role_service=service,
        )
        for i, (host, sport, dport, proto, flags, service) in enumerate(mixed_specs, 1)
    ]
    write_bundle(
        "mixed_ddos_recon_v2",
        "judge-mixed-ddos-recon-v2",
        mixed,
        semantics="SOURCE_EVENT_TIME",
        direction_basis="CAPTURE_INTERFACE",
        visibility=packet_vis,
        quality=limited_quality,
        start="2026-09-27T05:30:00Z",
        end="2026-09-27T05:30:11Z",
    )

    one_way_specs = [
        (10, 51000, 443, 6, ["SYN"], "service/https"),
        (11, 51001, 443, 6, ["SYN"], "service/https"),
        (12, 51002, 22, 6, ["SYN"], "service/ssh"),
        (13, 51003, 443, 6, ["SYN"], "service/https"),
        (14, 51004, 8443, 6, ["SYN"], "service/tcp-8443"),
        (15, None, None, 1, None, None),
        (16, 53016, 53, 17, None, "service/dns-udp"),
        (17, None, None, 99, None, None),
    ]
    one_way = [
        packet_record(
            i,
            f"2026-09-27T05:31:{i - 1:02d}Z",
            f"198.51.100.{host}",
            "192.0.2.20",
            sport,
            dport,
            proto,
            flags,
            role_service=service,
        )
        for i, (host, sport, dport, proto, flags, service) in enumerate(one_way_specs, 1)
    ]
    write_bundle(
        "ddos_one_way_v2",
        "judge-ddos-one-way-v2",
        one_way,
        semantics="SOURCE_EVENT_TIME",
        direction_basis="CAPTURE_INTERFACE",
        visibility=packet_vis,
        quality=clear_quality,
        start="2026-09-27T05:31:00Z",
        end="2026-09-27T05:31:07Z",
    )

    flow_specs = sorted(
        [
            (0, "198.51.100.44", 443, 100, 1),
            (41, "198.51.100.44", 443, 87, 2),
            (103, "198.51.100.44", 443, 126, 1),
            (178, "198.51.100.44", 443, 93, 3),
            (249, "198.51.100.44", 443, 111, 2),
            (66, "198.51.100.88", 8443, 45, 1),
            (217, "192.0.2.77", 443, 58, 1),
        ]
    )
    c2 = []
    for pos, (offset, peer, port, count, duration) in enumerate(flow_specs, 1):
        minute, second = divmod(offset, 60)
        stamp = f"2026-09-27T05:{30 + minute:02d}:{second:02d}Z"
        end = f"2026-09-27T05:{30 + minute:02d}:{min(second + duration, 59):02d}Z"
        client = "192.0.2.44"
        c2.append(flow_record(pos, stamp, stamp, end, client, peer, port, count))
    write_bundle(
        "c2_recurrence_v2",
        "judge-c2-recurrence-v2",
        c2,
        semantics="FLOW_START",
        direction_basis="CLIENT_SERVER_ROLE",
        visibility={
            "available": ["FORWARD_FACTS"],
            "unavailable": ["REVERSE_FACTS"],
            "degraded": [],
        },
        quality={
            "packet_loss": "UNKNOWN",
            "sampling": "UNKNOWN",
            "parser": "CLEAR",
            "capture_gap": "UNKNOWN",
        },
        start="2026-09-27T05:30:00Z",
        end="2026-09-27T05:34:11Z",
    )

    dns_specs = [
        (0, "qjwomrpkvtnsxa.example.com", "A", 55),
        (19, "api-status.example.net", "A", 58),
        (48, "xkqvbnrptzlmwe.example.org", "AAAA", 67),
        (91, "updates.example.net", "A", 52),
        (137, "mznxqplvkrwtsa.example.org", "A", 64),
        (194, "docs.example.com", "AAAA", 60),
    ]
    dns = [
        dns_record(i, sec, name, typ, length, f"controlled-dns-flow-{i}")
        for i, (sec, name, typ, length) in enumerate(dns_specs, 1)
    ]
    write_bundle(
        "dga_dns_v2",
        "judge-dga-dns-v2",
        dns,
        semantics="SOURCE_EVENT_TIME",
        direction_basis="CLIENT_SERVER_ROLE",
        visibility={
            "available": ["CLEAR_DNS_FIELDS", "FORWARD_FACTS"],
            "unavailable": [],
            "degraded": [],
        },
        quality={
            "packet_loss": "UNKNOWN",
            "sampling": "UNKNOWN",
            "parser": "CLEAR",
            "capture_gap": "UNKNOWN",
        },
        start="2026-09-27T05:30:00Z",
        end="2026-09-27T05:33:14Z",
    )
    write_pcap()


if __name__ == "__main__":
    main()
