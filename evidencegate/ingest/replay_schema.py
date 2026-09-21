"""Strict versioned schema for passive typed-NDJSON replay bundles."""
from __future__ import annotations

import json
import types
from types import MappingProxyType
from dataclasses import MISSING, dataclass, fields
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Union, get_args, get_origin, get_type_hints

from evidencegate.domain.enums import (
    DirectionBasis, Finality, IdentityBasis, ObservationType, QualityState,
    SourceKind, TimestampSemantics, VisibilityCapability, WireDirection,
)
from evidencegate.domain.events import RoleAssignment, VisibilityProfile
from evidencegate.domain.payloads import (
    DNSObservation, FlowObservation, PacketObservation, QUICObservation,
    TLSObservation,
)
from evidencegate.domain.quality import EvidenceQuality
from evidencegate.ingest.source import RawSourceRecord, SourceManifest


MANIFEST_SCHEMA_VERSION = "evidencegate-replay-manifest-v1"
RECORD_SCHEMA_VERSION = "evidencegate-replay-record-v1"
INPUT_CONTRACT = "REPLAY_TYPED_V1"
EVENT_TIME_ORDER = "NONDECREASING"


class ReplayValidationError(ValueError):
    """A safe, location-aware replay bundle validation failure."""

    def __init__(self, source_id: str, position: object, error_type: str, detail: str):
        self.source_id = source_id
        self.position = position
        self.error_type = error_type
        self.detail = detail
        super().__init__(
            f"replay source {source_id!r} at {position!r}: {error_type}: {detail}"
        )


@dataclass(frozen=True, slots=True)
class ReplayManifest:
    schema_version: str
    source_manifest: SourceManifest
    event_time_order: str
    record_count: int | None


@dataclass(frozen=True, slots=True)
class ReplaySourceRecord(RawSourceRecord):
    observation_type: ObservationType = ObservationType.PACKET
    declared_observed_fields: tuple[str, ...] = ()
    role_assignments: tuple[RoleAssignment, ...] = ()
    canonicalization_options: Mapping[str, bool] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        RawSourceRecord.__post_init__(self)
        object.__setattr__(
            self, "canonicalization_options",
            MappingProxyType(dict(self.canonicalization_options or {})),
        )


_PAYLOAD_TYPES = {
    ObservationType.PACKET: PacketObservation,
    ObservationType.FLOW: FlowObservation,
    ObservationType.DNS: DNSObservation,
    ObservationType.TLS: TLSObservation,
    ObservationType.QUIC: QUICObservation,
}
_OPTIONS = {
    ObservationType.PACKET: frozenset(),
    ObservationType.FLOW: frozenset(),
    ObservationType.DNS: frozenset({"clear_dns_fields"}),
    ObservationType.TLS: frozenset({"handshake_metadata", "record_metadata"}),
    ObservationType.QUIC: frozenset({"outer_metadata"}),
}


def parse_datetime(value: object, name: str) -> datetime:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{name} is not valid ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return parsed


def _enum(enum_type: type, value: object, name: str):
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    try:
        return enum_type(value)
    except ValueError as exc:
        raise ValueError(f"unknown {name}: {value!r}") from exc


def _typed(value: object, annotation: object, name: str) -> object:
    origin, args = get_origin(annotation), get_args(annotation)
    if origin in (Union, types.UnionType):
        if value is None and type(None) in args:
            return None
        errors = []
        for option in args:
            if option is type(None):
                continue
            try:
                return _typed(value, option, name)
            except (TypeError, ValueError) as exc:
                errors.append(str(exc))
        raise TypeError(errors[0] if errors else f"{name} has invalid type")
    if annotation is datetime:
        return parse_datetime(value, name)
    if annotation is Any:
        return value
    if origin is list:
        if not isinstance(value, list):
            raise TypeError(f"{name} must be an array")
        return [_typed(item, args[0], f"{name}[]") for item in value]
    if origin is tuple:
        if not isinstance(value, list):
            raise TypeError(f"{name} must be an array")
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(_typed(item, args[0], f"{name}[]") for item in value)
        if len(value) != len(args):
            raise ValueError(f"{name} must contain {len(args)} items")
        return tuple(_typed(item, item_type, f"{name}[]")
                     for item, item_type in zip(value, args))
    if origin is dict:
        if not isinstance(value, dict):
            raise TypeError(f"{name} must be an object")
        return {
            _typed(key, args[0], f"{name} key"): _typed(item, args[1], f"{name}.{key}")
            for key, item in value.items()
        }
    if annotation is int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{name} must be an integer")
        return value
    if annotation is bool:
        if not isinstance(value, bool):
            raise TypeError(f"{name} must be a boolean")
        return value
    if annotation is str:
        if not isinstance(value, str):
            raise TypeError(f"{name} must be a string")
        return value
    return value


def _payload(payload_type: type, value: object):
    if not isinstance(value, dict):
        raise TypeError("payload must be an object")
    definitions = {field.name: field for field in fields(payload_type)}
    unknown = set(value) - set(definitions)
    if unknown:
        raise ValueError(f"unknown payload fields: {sorted(unknown)}")
    hints = get_type_hints(payload_type)
    converted = {}
    for name, definition in definitions.items():
        if name in value:
            converted[name] = _typed(value[name], hints[name], f"payload.{name}")
        elif definition.default is MISSING and definition.default_factory is MISSING:
            raise ValueError(f"missing payload field: {name}")
    return payload_type(**converted)


def _visibility(value: object) -> VisibilityProfile:
    if value is None:
        return VisibilityProfile()
    if not isinstance(value, dict) or set(value) - {"available", "unavailable", "degraded"}:
        raise ValueError("visibility must contain only available/unavailable/degraded")
    return VisibilityProfile(**{
        name: frozenset(_enum(VisibilityCapability, item, f"visibility.{name}")
                        for item in value.get(name, []))
        for name in ("available", "unavailable", "degraded")
    })


def _quality(value: object) -> EvidenceQuality:
    if value is None:
        return EvidenceQuality()
    names = {"packet_loss", "sampling", "parser", "capture_gap"}
    if not isinstance(value, dict) or set(value) - names:
        raise ValueError("quality contains unknown fields")
    return EvidenceQuality(**{
        name: _enum(QualityState, value.get(name, "UNKNOWN"), f"quality.{name}")
        for name in names
    })


def parse_manifest(path: Path) -> ReplayManifest:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReplayValidationError("<unknown>", "manifest.json", type(exc).__name__, str(exc)) from exc
    required = {
        "schema_version", "source_id", "source_kind", "input_observation_contract",
        "timestamp_semantics", "direction_basis", "wire_direction", "visibility",
        "quality", "event_time_order",
    }
    allowed = required | {"record_count", "capture_start", "capture_end"}
    if not isinstance(value, dict):
        raise ReplayValidationError("<unknown>", "manifest.json", "SchemaError", "manifest must be an object")
    source_id = value.get("source_id", "<unknown>")
    try:
        missing, unknown = required - set(value), set(value) - allowed
        if missing or unknown:
            raise ValueError(f"missing={sorted(missing)} unknown={sorted(unknown)}")
        if value["schema_version"] != MANIFEST_SCHEMA_VERSION:
            raise ValueError("unsupported manifest schema_version")
        if value["input_observation_contract"] != INPUT_CONTRACT:
            raise ValueError("unsupported input_observation_contract")
        if value["event_time_order"] != EVENT_TIME_ORDER:
            raise ValueError("only NONDECREASING event_time_order is supported")
        if not isinstance(source_id, str) or not source_id:
            raise ValueError("source_id must be a non-empty string")
        if value["source_kind"] != SourceKind.DERIVED.value:
            raise ValueError("typed replay source_kind must be DERIVED")
        count = value.get("record_count")
        if count is not None and (isinstance(count, bool) or not isinstance(count, int) or count < 0):
            raise ValueError("record_count must be a non-negative integer")
        manifest = SourceManifest(
            source_id=source_id, source_kind=SourceKind.DERIVED,
            capture_start=(parse_datetime(value["capture_start"], "capture_start")
                           if value.get("capture_start") is not None else None),
            capture_end=(parse_datetime(value["capture_end"], "capture_end")
                         if value.get("capture_end") is not None else None),
            timestamp_semantics=_enum(TimestampSemantics, value["timestamp_semantics"], "timestamp_semantics"),
            input_observation_contract=INPUT_CONTRACT,
            direction_basis=_enum(DirectionBasis, value["direction_basis"], "direction_basis"),
            wire_direction=_enum(WireDirection, value["wire_direction"], "wire_direction"),
            visibility=_visibility(value["visibility"]), quality=_quality(value["quality"]),
        )
        if manifest.capture_start and manifest.capture_end and manifest.capture_end < manifest.capture_start:
            raise ValueError("capture_end cannot precede capture_start")
        return ReplayManifest(value["schema_version"], manifest, value["event_time_order"], count)
    except (TypeError, ValueError) as exc:
        raise ReplayValidationError(str(source_id), "manifest.json", type(exc).__name__, str(exc)) from exc


def parse_record_line(text: str, *, source_id: str, line_number: int) -> ReplaySourceRecord:
    try:
        value = json.loads(text)
        required = {
            "schema_version", "position", "timestamp", "finality", "observation_type",
            "payload", "declared_observed_fields", "role_assignments",
            "canonicalization_options",
        }
        if not isinstance(value, dict):
            raise TypeError("record must be an object")
        if set(value) != required:
            raise ValueError(
                f"missing={sorted(required - set(value))} unknown={sorted(set(value) - required)}"
            )
        if value["schema_version"] != RECORD_SCHEMA_VERSION:
            raise ValueError("unsupported record schema_version")
        position = value["position"]
        if isinstance(position, bool) or not isinstance(position, (str, int)) or position == "":
            raise TypeError("position must be a non-empty string or integer")
        observation_type = _enum(ObservationType, value["observation_type"], "observation_type")
        payload = _payload(_PAYLOAD_TYPES[observation_type], value["payload"])
        declared = value["declared_observed_fields"]
        if not isinstance(declared, list) or any(not isinstance(item, str) for item in declared):
            raise TypeError("declared_observed_fields must be an array of strings")
        valid_fields = {field.name for field in fields(payload)}
        unknown_fields = set(declared) - valid_fields
        if unknown_fields:
            raise ValueError(f"unknown declared fields: {sorted(unknown_fields)}")
        if len(set(declared)) != len(declared):
            raise ValueError("declared_observed_fields must not contain duplicates")
        roles_value = value["role_assignments"]
        if not isinstance(roles_value, list):
            raise TypeError("role_assignments must be an array")
        roles = []
        for index, role in enumerate(roles_value):
            if not isinstance(role, dict) or set(role) != {"identifier", "role", "basis"}:
                raise ValueError(f"role_assignments[{index}] has invalid fields")
            if not isinstance(role["identifier"], str) or not role["identifier"]:
                raise ValueError(f"role_assignments[{index}].identifier must be non-empty")
            if not isinstance(role["role"], str) or not role["role"]:
                raise ValueError(f"role_assignments[{index}].role must be non-empty")
            roles.append(RoleAssignment(
                role["identifier"], role["role"],
                _enum(IdentityBasis, role["basis"], "role basis"),
            ))
        options = value["canonicalization_options"]
        if not isinstance(options, dict):
            raise TypeError("canonicalization_options must be an object")
        unknown_options = set(options) - _OPTIONS[observation_type]
        if unknown_options or any(not isinstance(item, bool) for item in options.values()):
            raise ValueError(f"invalid canonicalization options: {sorted(unknown_options)}")
        return ReplaySourceRecord(
            raw_data=payload, timestamp=parse_datetime(value["timestamp"], "timestamp"),
            position=position, finality=_enum(Finality, value["finality"], "finality"),
            observation_type=observation_type,
            declared_observed_fields=tuple(declared), role_assignments=tuple(roles),
            canonicalization_options=dict(options),
        )
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ReplayValidationError(source_id, f"line {line_number}", type(exc).__name__, str(exc)) from exc
