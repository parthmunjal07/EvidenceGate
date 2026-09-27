"""Passive, incremental classic-PCAP input adapter backed by dpkt.

This module opens existing files read-only.  It contains no capture, injection,
socket, or network-interface operations.  Direction and semantic roles come
only from the trusted sidecar manifest; packet tuples are never interpreted as
roles by heuristic.
"""
from __future__ import annotations

import asyncio
import ipaddress
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import AsyncIterator, Mapping

import dpkt

from evidencegate.domain.enums import (
    DirectionBasis, Finality, IdentityBasis, QualityState, SourceKind,
    TimestampSemantics, VisibilityCapability, WireDirection,
)
from evidencegate.domain.events import RoleAssignment, VisibilityProfile
from evidencegate.domain.payloads import PacketObservation
from evidencegate.domain.quality import EvidenceQuality
from evidencegate.ingest.replay_schema import ReplaySourceRecord, ReplayValidationError
from evidencegate.ingest.source import SourceManifest


PCAP_MANIFEST_SCHEMA_VERSION = "evidencegate-pcap-manifest-v1"
PCAP_INPUT_CONTRACT = "RAW_PCAP_PACKET_V1"
SUPPORTED_LINKTYPE = dpkt.pcap.DLT_EN10MB


@dataclass(frozen=True, slots=True)
class ServiceMapping:
    target_address: str
    protocol: int
    port: int
    service_id: str
    basis: IdentityBasis = IdentityBasis.POLICY_DECLARED_ROLE


@dataclass(frozen=True, slots=True)
class PcapDirectionPolicy:
    """Trusted A/B network policy; no address-class or port inference."""

    a_networks: tuple[ipaddress.IPv4Network, ...] = ()
    b_networks: tuple[ipaddress.IPv4Network, ...] = ()

    def classify(self, source: str, destination: str) -> WireDirection:
        src, dst = ipaddress.ip_address(source), ipaddress.ip_address(destination)
        src_a = any(src in network for network in self.a_networks)
        src_b = any(src in network for network in self.b_networks)
        dst_a = any(dst in network for network in self.a_networks)
        dst_b = any(dst in network for network in self.b_networks)
        if src_a and dst_b and not src_b and not dst_a:
            return WireDirection.FORWARD
        if src_b and dst_a and not src_a and not dst_b:
            return WireDirection.REVERSE
        return WireDirection.UNKNOWN

    @property
    def configured(self) -> bool:
        return bool(self.a_networks and self.b_networks)


@dataclass(frozen=True, slots=True)
class PcapAdapterManifest:
    source_manifest: SourceManifest
    capture_file: str
    visibility_mode: str
    direction_policy: PcapDirectionPolicy
    endpoint_roles: Mapping[str, tuple[str, ...]]
    services: tuple[ServiceMapping, ...]
    reflection_facts: Mapping[int, Mapping[str, object]]
    packet_count: int | None


def _enum_value(enum_type: type, value: object, name: str):
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    try:
        return enum_type(value)
    except ValueError as exc:
        raise ValueError(f"unknown {name}: {value!r}") from exc


def _parse_time(value: object, name: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{name} must be an ISO-8601 string or null")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return parsed


def _parse_networks(value: object, name: str) -> tuple[ipaddress.IPv4Network, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise TypeError(f"{name} must be an array of IPv4 CIDR strings")
    networks: list[ipaddress.IPv4Network] = []
    for item in value:
        network = ipaddress.ip_network(item, strict=False)
        if not isinstance(network, ipaddress.IPv4Network):
            raise ValueError(f"{name} supports IPv4 only")
        networks.append(network)
    return tuple(networks)


def _visibility(mode: object) -> VisibilityProfile:
    if mode == "BOTH":
        return VisibilityProfile(available=frozenset({
            VisibilityCapability.FORWARD_FACTS,
            VisibilityCapability.REVERSE_FACTS,
        }))
    if mode == "FORWARD":
        return VisibilityProfile(
            available=frozenset({VisibilityCapability.FORWARD_FACTS}),
            unavailable=frozenset({VisibilityCapability.REVERSE_FACTS}),
        )
    if mode == "REVERSE":
        return VisibilityProfile(
            available=frozenset({VisibilityCapability.REVERSE_FACTS}),
            unavailable=frozenset({VisibilityCapability.FORWARD_FACTS}),
        )
    if mode == "UNKNOWN":
        return VisibilityProfile()
    raise ValueError("visibility must be BOTH, FORWARD, REVERSE, or UNKNOWN")


def parse_pcap_manifest(path: str | Path) -> PcapAdapterManifest:
    """Parse the strict trusted adapter sidecar without reading packet data."""
    manifest_path = Path(path)
    try:
        value = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReplayValidationError("<unknown>", manifest_path.name, type(exc).__name__, str(exc)) from exc
    required = {
        "schema_version", "source_id", "capture_file", "visibility", "quality",
        "direction_policy", "endpoint_roles", "services", "reflection_facts",
    }
    allowed = required | {"capture_start", "capture_end", "packet_count"}
    source_id = value.get("source_id", "<unknown>") if isinstance(value, dict) else "<unknown>"
    try:
        if not isinstance(value, dict):
            raise TypeError("manifest must be an object")
        missing, unknown = required - set(value), set(value) - allowed
        if missing or unknown:
            raise ValueError(f"missing={sorted(missing)} unknown={sorted(unknown)}")
        if value["schema_version"] != PCAP_MANIFEST_SCHEMA_VERSION:
            raise ValueError("unsupported schema_version")
        if not isinstance(source_id, str) or not source_id:
            raise ValueError("source_id must be a non-empty string")
        capture_file = value["capture_file"]
        if (not isinstance(capture_file, str) or not capture_file
                or Path(capture_file).name != capture_file):
            raise ValueError("capture_file must be a single relative filename")
        direction_value = value["direction_policy"]
        if not isinstance(direction_value, dict) or set(direction_value) != {"a_networks", "b_networks"}:
            raise ValueError("direction_policy requires only a_networks and b_networks")
        direction = PcapDirectionPolicy(
            _parse_networks(direction_value["a_networks"], "direction_policy.a_networks"),
            _parse_networks(direction_value["b_networks"], "direction_policy.b_networks"),
        )
        if bool(direction.a_networks) != bool(direction.b_networks):
            raise ValueError("direction policy requires both A-side and B-side networks")

        roles_value = value["endpoint_roles"]
        if not isinstance(roles_value, dict):
            raise TypeError("endpoint_roles must be an object")
        roles: dict[str, tuple[str, ...]] = {}
        for address, labels in roles_value.items():
            parsed_address = ipaddress.ip_address(address)
            if not isinstance(parsed_address, ipaddress.IPv4Address):
                raise ValueError("endpoint_roles supports IPv4 only")
            if (not isinstance(labels, list) or not labels
                    or any(not isinstance(label, str) or not label for label in labels)):
                raise TypeError("endpoint role values must be non-empty string arrays")
            if len(set(labels)) != len(labels):
                raise ValueError("endpoint role values must not contain duplicates")
            roles[str(parsed_address)] = tuple(labels)

        services_value = value["services"]
        if not isinstance(services_value, list):
            raise TypeError("services must be an array")
        services: list[ServiceMapping] = []
        service_keys: set[tuple[str, int, int]] = set()
        for entry in services_value:
            required = {"target_address", "protocol", "port", "service_id"}
            if not isinstance(entry, dict) or not required.issubset(entry) or set(entry) - required - {"basis"}:
                raise ValueError("each service requires target_address, protocol, port, service_id and optional basis")
            target = ipaddress.ip_address(entry["target_address"])
            protocol, port, service_id = entry["protocol"], entry["port"], entry["service_id"]
            if not isinstance(target, ipaddress.IPv4Address):
                raise ValueError("service target must be IPv4")
            if (isinstance(protocol, bool) or not isinstance(protocol, int) or not 0 <= protocol <= 255
                    or isinstance(port, bool) or not isinstance(port, int) or not 0 <= port <= 65535
                    or not isinstance(service_id, str) or not service_id):
                raise ValueError("invalid service mapping")
            key = (str(target), protocol, port)
            if key in service_keys:
                raise ValueError("service mappings must not duplicate target/protocol/port")
            service_keys.add(key)
            basis_value = entry.get("basis", IdentityBasis.POLICY_DECLARED_ROLE.value)
            try:
                basis = IdentityBasis(basis_value)
            except (TypeError, ValueError) as exc:
                raise ValueError("service basis must be a recognized identity basis") from exc
            if basis is not IdentityBasis.POLICY_DECLARED_ROLE:
                raise ValueError("configured PCAP service roles must use POLICY_DECLARED_ROLE")
            services.append(ServiceMapping(str(target), protocol, port, service_id, basis))

        reflection_value = value["reflection_facts"]
        if not isinstance(reflection_value, dict):
            raise TypeError("reflection_facts must be an object keyed by packet position")
        reflections: dict[int, Mapping[str, object]] = {}
        for key, facts in reflection_value.items():
            position = int(key)
            if str(position) != key or position < 1:
                raise ValueError("reflection fact keys must be positive canonical integers")
            if (not isinstance(facts, dict)
                    or set(facts) != {"fact_contract", "response_like", "protocol_context"}
                    or facts["fact_contract"] != "DDOS_REFLECTION_FACT_V1"
                    or facts["response_like"] is not True
                    or not isinstance(facts["protocol_context"], str)
                    or not facts["protocol_context"].strip()):
                raise ValueError("invalid DDOS_REFLECTION_FACT_V1 sidecar fact")
            reflections[position] = MappingProxyType(dict(facts))

        quality_value = value["quality"]
        quality_names = {"packet_loss", "sampling", "parser", "capture_gap"}
        if not isinstance(quality_value, dict) or set(quality_value) != quality_names:
            raise ValueError(f"quality requires exactly {sorted(quality_names)}")
        quality = EvidenceQuality(**{
            name: _enum_value(QualityState, quality_value[name], f"quality.{name}")
            for name in quality_names
        })
        count = value.get("packet_count")
        if count is not None and (isinstance(count, bool) or not isinstance(count, int) or count < 0):
            raise ValueError("packet_count must be a non-negative integer")
        start, end = _parse_time(value.get("capture_start"), "capture_start"), _parse_time(value.get("capture_end"), "capture_end")
        if start and end and end < start:
            raise ValueError("capture_end cannot precede capture_start")
        visibility_mode = value["visibility"]
        source = SourceManifest(
            source_id=source_id, source_kind=SourceKind.PCAP,
            capture_start=start, capture_end=end,
            timestamp_semantics=TimestampSemantics.SOURCE_EVENT_TIME,
            input_observation_contract=PCAP_INPUT_CONTRACT,
            direction_basis=(DirectionBasis.LOCAL_EXTERNAL_POLICY
                             if direction.configured else DirectionBasis.UNKNOWN),
            wire_direction=WireDirection.UNKNOWN,
            visibility=_visibility(visibility_mode), quality=quality,
        )
        return PcapAdapterManifest(
            source, capture_file, str(visibility_mode), direction,
            MappingProxyType(roles), tuple(services),
            MappingProxyType(reflections), count,
        )
    except (TypeError, ValueError) as exc:
        raise ReplayValidationError(str(source_id), manifest_path.name, type(exc).__name__, str(exc)) from exc


class PcapReplaySource:
    """Stream Ethernet/IPv4 packets from one existing classic-PCAP file."""

    source_type = "PCAP"

    def __init__(self, capture: str | Path, manifest: str | Path):
        self.capture_path, self.manifest_path = Path(capture), Path(manifest)
        self.bundle = self.capture_path.parent
        self.source_id = "<unopened>"
        self.source_kind = SourceKind.PCAP
        self.adapter_manifest: PcapAdapterManifest | None = None
        self._file = None
        self._reader = None
        self._paused = asyncio.Event()
        self._paused.set()
        self._opened = False
        self._consumed = False

    async def open(self) -> SourceManifest:
        if self._opened:
            raise RuntimeError("pcap source is already open")
        adapter = parse_pcap_manifest(self.manifest_path)
        self.source_id = adapter.source_manifest.source_id
        if self.capture_path.name != adapter.capture_file:
            raise ReplayValidationError(
                self.source_id, "manifest", "CaptureIdentityError",
                "capture path filename does not match manifest capture_file",
            )
        try:
            self._file = self.capture_path.open("rb")
            self._reader = dpkt.pcap.Reader(self._file)
            if self._reader.datalink() != SUPPORTED_LINKTYPE:
                raise ReplayValidationError(
                    self.source_id, "pcap header", "UnsupportedLinkType",
                    f"only Ethernet linktype {SUPPORTED_LINKTYPE} is supported",
                )
        except ReplayValidationError:
            if self._file is not None:
                self._file.close()
            self._file = self._reader = None
            raise
        except (OSError, ValueError, dpkt.dpkt.Error) as exc:
            if self._file is not None:
                self._file.close()
            self._file = self._reader = None
            raise ReplayValidationError(self.source_id, "pcap header", type(exc).__name__, str(exc)) from exc
        self.adapter_manifest = adapter
        self._opened = True
        return adapter.source_manifest

    async def records(self) -> AsyncIterator[ReplaySourceRecord]:
        if not self._opened or self._reader is None or self.adapter_manifest is None:
            raise RuntimeError("open() must be called before records()")
        if self._consumed:
            raise RuntimeError("records() may be consumed only once per source")
        self._consumed = True
        count = 0
        iterator = iter(self._reader)
        while True:
            await self._paused.wait()
            try:
                timestamp, packet_bytes = next(iterator)
            except StopIteration:
                break
            except (ValueError, dpkt.dpkt.Error) as exc:
                raise ReplayValidationError(
                    self.source_id, count + 1, type(exc).__name__, str(exc)
                ) from exc
            count += 1
            try:
                yield self._packet_record(count, timestamp, packet_bytes)
            except ReplayValidationError:
                raise
            except (ValueError, TypeError, dpkt.dpkt.Error) as exc:
                raise ReplayValidationError(
                    self.source_id, count, type(exc).__name__, str(exc)
                ) from exc
        expected = self.adapter_manifest.packet_count
        if expected is not None and count != expected:
            raise ReplayValidationError(
                self.source_id, "EOF", "PacketCountError",
                f"manifest declares {expected}, read {count}",
            )

    def _packet_record(self, position: int, timestamp: float, packet_bytes: bytes) -> ReplaySourceRecord:
        if self.adapter_manifest is None:
            raise RuntimeError("source is not open")
        ethernet = dpkt.ethernet.Ethernet(packet_bytes)
        if ethernet.type == dpkt.ethernet.ETH_TYPE_IP6:
            raise ReplayValidationError(self.source_id, position, "UnsupportedProtocol", "IPv6 is not supported by RAW_PCAP_PACKET_V1")
        if ethernet.type != dpkt.ethernet.ETH_TYPE_IP or not isinstance(ethernet.data, dpkt.ip.IP):
            raise ReplayValidationError(self.source_id, position, "UnsupportedProtocol", f"Ethernet type {ethernet.type} is not supported")
        ip = ethernet.data
        source, destination = str(ipaddress.ip_address(ip.src)), str(ipaddress.ip_address(ip.dst))
        direction = self.adapter_manifest.direction_policy.classify(source, destination)
        fragment_offset = int(ip.offset)
        more_fragments = bool(ip.mf)
        fragmentation = {
            "fact_contract": "DDOS_FRAGMENT_FACT_V1",
            "is_fragment": bool(fragment_offset or more_fragments),
            "offset": fragment_offset,
            "more_fragments": more_fragments,
        }
        lengths = {"captured": len(packet_bytes), "ip": int(ip.len)}
        l2_facts = {"ethernet_type": int(ethernet.type)}
        l3_facts = {
            "header_length": int(ip.hl) * 4,
            "identification": int(ip.id),
            "ttl": int(ip.ttl),
            "fragment_offset_units": "8_octets",
        }
        l4_facts: dict[str, object] = {"protocol": int(ip.p)}
        src_port = dst_port = None
        flags: list[str] | None = None
        sequence_facts: dict[str, int] | None = None
        if fragment_offset == 0 and isinstance(ip.data, dpkt.tcp.TCP):
            tcp = ip.data
            src_port, dst_port = int(tcp.sport), int(tcp.dport)
            flags = [name for bit, name in (
                (dpkt.tcp.TH_FIN, "FIN"), (dpkt.tcp.TH_SYN, "SYN"),
                (dpkt.tcp.TH_RST, "RST"), (dpkt.tcp.TH_PUSH, "PSH"),
                (dpkt.tcp.TH_ACK, "ACK"), (dpkt.tcp.TH_URG, "URG"),
                (dpkt.tcp.TH_ECE, "ECE"), (dpkt.tcp.TH_CWR, "CWR"),
            ) if tcp.flags & bit]
            sequence_facts = {"seq": int(tcp.seq), "ack": int(tcp.ack)}
            l4_facts.update({"header_length": int(tcp.off) * 4})
        elif fragment_offset == 0 and isinstance(ip.data, dpkt.udp.UDP):
            udp = ip.data
            src_port, dst_port = int(udp.sport), int(udp.dport)
            l4_facts.update({"length": int(udp.ulen)})
        elif fragment_offset == 0 and isinstance(ip.data, dpkt.icmp.ICMP):
            icmp = ip.data
            l4_facts.update({"type": int(icmp.type), "code": int(icmp.code)})
        reflection = self.adapter_manifest.reflection_facts.get(position)
        if reflection is not None:
            if ip.p != dpkt.ip.IP_PROTO_UDP:
                raise ReplayValidationError(self.source_id, position, "ReflectionContractError", "reflection facts require UDP")
            l4_facts = dict(reflection)

        roles: list[RoleAssignment] = []
        for address in (source, destination):
            for role in self.adapter_manifest.endpoint_roles.get(address, ()):
                roles.append(RoleAssignment(address, role, IdentityBasis.POLICY_DECLARED_ROLE))
        for service in self.adapter_manifest.services:
            target_side_port = (
                dst_port if destination == service.target_address else
                src_port if source == service.target_address else None
            )
            if ip.p == service.protocol and target_side_port == service.port:
                roles.append(RoleAssignment(service.service_id, "service_id", service.basis))

        payload = PacketObservation(
            lengths=lengths, observed_l2_facts=l2_facts,
            observed_l3_facts=l3_facts, observed_l4_facts=l4_facts,
            src_address=source, dst_address=destination,
            src_port=src_port, dst_port=dst_port, flags=flags,
            sequence_facts=sequence_facts, fragmentation=fragmentation,
            raw_reference=f"pcap:{self.source_id}:packet:{position}",
            protocol=int(ip.p),
        )
        declared = [
            "lengths", "observed_l2_facts", "observed_l3_facts",
            "observed_l4_facts", "src_address", "dst_address", "fragmentation",
            "raw_reference", "protocol",
        ]
        if src_port is not None:
            declared.extend(("src_port", "dst_port"))
        if flags is not None:
            declared.extend(("flags", "sequence_facts"))
        return ReplaySourceRecord(
            raw_data=payload,
            timestamp=datetime.fromtimestamp(float(timestamp), tz=timezone.utc),
            position=position, finality=Finality.CURRENT,
            declared_observed_fields=tuple(declared), role_assignments=tuple(roles),
            canonicalization_options={}, wire_direction=direction,
        )

    async def pause(self) -> None:
        self._paused.clear()

    async def resume(self) -> None:
        self._paused.set()

    async def close(self) -> None:
        if self._file is not None:
            self._file.close()
        self._file = self._reader = None
        self._opened = False


async def validate_pcap(capture: str | Path, manifest: str | Path) -> int:
    """Parse and canonicalize every packet without invoking analytics."""
    from evidencegate.ingest.replay import ReplayCanonicalizer

    source = PcapReplaySource(capture, manifest)
    source_manifest = await source.open()
    canonicalizer = ReplayCanonicalizer()
    count = 0
    records = source.records()
    try:
        async for record in records:
            canonicalizer.canonicalize(
                record, source_manifest,
                f"quality:{source_manifest.source_id}:{record.position}",
                datetime.now(timezone.utc),
            )
            count += 1
    finally:
        await records.aclose()
        await source.close()
    return count
