"""Whitelisted, best-effort summaries for explaining replay source and normalization."""
from __future__ import annotations

from dataclasses import fields
from datetime import datetime
from enum import Enum
import re
from typing import Any

from evidencegate.domain.events import NetworkObservation
from evidencegate.domain.payloads import (
    DNSObservation, FlowObservation, PacketObservation, QUICObservation, TLSObservation,
)


def _value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return None


def _dict_values(value: object, allowed: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {key: _value(value[key]) for key in allowed if key in value and _value(value[key]) is not None}


def _packet_facts(payload: PacketObservation) -> dict[str, Any]:
    facts: dict[str, Any] = {}
    for key, value in (
        ("source_address", payload.src_address), ("source_port", payload.src_port),
        ("destination_address", payload.dst_address), ("destination_port", payload.dst_port),
        ("protocol_number", payload.protocol), ("flags", payload.flags),
        ("ip_length", payload.lengths.get("ip")),
        ("packet_length", payload.lengths.get("packet")),
    ):
        if value is not None:
            facts[key] = value[:12] if key == "flags" and isinstance(value, list) else value
    if payload.fragmentation:
        facts["fragmentation"] = _dict_values(payload.fragmentation, {"offset", "more_fragments", "fragment_id"})
    return facts


def _flow_facts(payload: FlowObservation) -> dict[str, Any]:
    return {
        "endpoint_a": payload.endpoints[0], "endpoint_b": payload.endpoints[1],
        "protocol_number": payload.protocol, "start_time": _value(payload.start_time),
        "end_time": _value(payload.end_time), "export_time": _value(payload.export_time),
        "directional_counters": _dict_values(
            payload.supplied_directional_counters,
            {"bytes_c2s", "packets_c2s", "bytes_s2c", "packets_s2c"},
        ),
        "documented_end_state": payload.documented_end_state,
    }


def _safe_controlled_reference(value: object) -> str | None:
    if not isinstance(value, str) or not value.startswith(("controlled-", "judge-")):
        return None
    if len(value) > 120 or not re.fullmatch(r"[A-Za-z0-9._:/-]+", value):
        return None
    return value


def _dns_facts(payload: DNSObservation) -> dict[str, Any]:
    facts = {
        "qname_rendered": payload.qname_rendered or payload.qname,
        "qname_canonical": payload.qname_canonical,
        "qtype": payload.qtype, "qclass": payload.qclass,
        "transport": payload.transport, "message_length": payload.message_length,
        "query_response_state": "decoded" if payload.qr_state_decoded else "not decoded",
        "rcode": payload.rcode, "parser_status": payload.parser_status,
    }
    return {key: value for key, value in facts.items() if value is not None}


def _tls_facts(payload: TLSObservation) -> dict[str, Any]:
    handshake = _dict_values(payload.parsed_handshake_metadata, {"message_type", "handshake_type", "sni", "server_name"})
    records = _dict_values(payload.parsed_record_metadata, {"record_type", "version", "length"})
    facts: dict[str, Any] = {"reassembly_state": payload.tcp_reassembly_state, "parser_version": payload.parser_version}
    if handshake:
        facts["handshake_metadata"] = handshake
    if records:
        facts["record_metadata"] = records
    return facts


def _quic_facts(payload: QUICObservation) -> dict[str, Any]:
    return {
        "version": payload.version, "header_type": payload.header_type,
        "packet_length": payload.length, "parser_version": payload.parser_version,
        "visibility_flags": payload.visibility_flags[:12],
    }


def _facts(payload: object) -> dict[str, Any]:
    if isinstance(payload, PacketObservation):
        return _packet_facts(payload)
    if isinstance(payload, FlowObservation):
        return _flow_facts(payload)
    if isinstance(payload, DNSObservation):
        return _dns_facts(payload)
    if isinstance(payload, TLSObservation):
        return _tls_facts(payload)
    if isinstance(payload, QUICObservation):
        return _quic_facts(payload)
    return {}


def project_source_record(record: object) -> dict[str, Any]:
    """Return a safe source summary; deliberately omits raw refs and payload bytes."""
    payload = getattr(record, "raw_data", None)
    observed = set(getattr(record, "declared_observed_fields", ()) or ())
    facts = _facts(payload)
    flow_reference = _safe_controlled_reference(getattr(payload, "flow_reference", None))
    if flow_reference and "flow_reference" in observed:
        facts["flow_reference"] = flow_reference
    if observed:
        fact_field = {
            "source_address": "src_address", "source_port": "src_port",
            "destination_address": "dst_address", "destination_port": "dst_port",
            "protocol_number": "protocol", "flags": "flags", "ip_length": "lengths",
            "packet_length": "lengths", "endpoint_a": "endpoints", "endpoint_b": "endpoints",
            "start_time": "start_time", "end_time": "end_time", "export_time": "export_time",
            "directional_counters": "supplied_directional_counters", "qname_rendered": "qname",
            "qname_canonical": "qname_canonical", "qtype": "qtype", "qclass": "qclass",
            "flow_reference": "flow_reference",
            "transport": "transport", "message_length": "message_length", "rcode": "rcode",
            "parser_status": "parser_status", "reassembly_state": "tcp_reassembly_state",
            "parser_version": "parser_version", "handshake_metadata": "parsed_handshake_metadata",
            "record_metadata": "parsed_record_metadata", "version": "version",
            "header_type": "header_type", "packet_length": "length", "visibility_flags": "visibility_flags",
        }
        facts = {key: value for key, value in facts.items() if fact_field.get(key) in observed}
    observation_type = type(payload).__name__.removesuffix("Observation").upper() if payload is not None else "UNKNOWN"
    stamp = getattr(record, "timestamp", None)
    position = getattr(record, "position", None)
    return {
        "record_number": position if isinstance(position, int) else None,
        "event_time": _value(stamp), "observation_type": observation_type,
        "facts": facts,
    }


def project_observation(observation: NetworkObservation) -> dict[str, Any]:
    """Project the actual canonical envelope through an explicit presentation whitelist."""
    roles = [
        {"identifier": role.identifier[:200], "role": role.role[:80], "basis": role.basis.value}
        for role in observation.identity.role_assignments[:16]
    ]
    return {
        "observation_id": observation.observation_id,
        "observation_type": observation.observation_type.value,
        "event_time": observation.event_time.isoformat(),
        "source_position": observation.source_position[:80],
        "wire_direction": observation.wire_direction.value,
        "direction_basis": observation.direction_basis.value,
        "finality": observation.finality.value,
        "availability_basis": observation.availability_basis.value,
        "present_fields": sorted(observation.present_fields)[:32],
        "identity": {
            "observed_identifiers": [item[:200] for item in observation.identity.observed_identifiers[:16]],
            "identifier_basis": observation.identity.identifier_basis.value,
            "role_assignments": roles,
        },
        "visibility": {
            "available": sorted(item.value for item in observation.visibility.available),
            "unavailable": sorted(item.value for item in observation.visibility.unavailable),
            "degraded": sorted(item.value for item in observation.visibility.degraded),
        },
        "quality": {
            "packet_loss": observation.quality.packet_loss.value,
            "sampling": observation.quality.sampling.value,
            "parser": observation.quality.parser.value,
            "capture_gap": observation.quality.capture_gap.value,
        },
        "facts": _facts(observation.typed_payload),
    }
