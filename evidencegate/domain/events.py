from dataclasses import dataclass, fields
from typing import Any, Optional
from datetime import datetime
from evidencegate.domain.enums import (
    AvailabilityBasis, CapabilityState, ControlType, DirectionBasis, Finality,
    IdentityBasis, ObservationType, QualityState, SourceKind, VisibilityCapability,
    WireDirection,
)
from evidencegate.domain.payloads import (
    DNSObservation, FlowObservation, NetworkPayloadType, PacketObservation,
    QUICObservation, TLSObservation,
)
from evidencegate.domain.quality import EvidenceQuality


@dataclass(frozen=True, slots=True)
class RoleAssignment:
    identifier: str
    role: str
    basis: IdentityBasis

    def __post_init__(self) -> None:
        if self.basis not in (IdentityBasis.SOURCE_DECLARED_ROLE, IdentityBasis.POLICY_DECLARED_ROLE):
            raise ValueError("role assignments require an explicit trusted role basis")


@dataclass(frozen=True, slots=True)
class ObservationIdentity:
    observed_identifiers: tuple[str, ...] = ()
    identifier_basis: IdentityBasis = IdentityBasis.UNKNOWN
    role_assignments: tuple[RoleAssignment, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.identifier_basis, IdentityBasis):
            raise TypeError("identifier_basis must be IdentityBasis")
        if self.observed_identifiers and self.identifier_basis is IdentityBasis.UNKNOWN:
            raise ValueError("observed identifiers require an identity basis")


@dataclass(frozen=True, slots=True)
class VisibilityProfile:
    available: frozenset[VisibilityCapability] = frozenset()
    unavailable: frozenset[VisibilityCapability] = frozenset()
    degraded: frozenset[VisibilityCapability] = frozenset()

    def __post_init__(self) -> None:
        collections = (self.available, self.unavailable, self.degraded)
        if any(not isinstance(items, frozenset) for items in collections):
            raise TypeError("visibility states must be frozenset[VisibilityCapability]")
        if any(not isinstance(item, VisibilityCapability) for items in collections for item in items):
            raise TypeError("visibility facts must use VisibilityCapability")
        if (self.available & self.unavailable or self.available & self.degraded
                or self.unavailable & self.degraded):
            raise ValueError("a visibility capability cannot have contradictory states")

    def state(self, capability: VisibilityCapability) -> CapabilityState:
        if capability in self.available:
            return CapabilityState.AVAILABLE
        if capability in self.unavailable:
            return CapabilityState.UNAVAILABLE
        if capability in self.degraded:
            return CapabilityState.DEGRADED
        return CapabilityState.UNKNOWN

    def with_facts(
        self,
        *,
        available: frozenset[VisibilityCapability] = frozenset(),
        unavailable: frozenset[VisibilityCapability] = frozenset(),
    ) -> "VisibilityProfile":
        return VisibilityProfile(
            available=(self.available | available) - unavailable,
            unavailable=(self.unavailable | unavailable) - available,
            degraded=self.degraded - available - unavailable,
        )

@dataclass(frozen=True, slots=True)
class NetworkObservationEnvelope:
    """
    present_fields is authoritative for whether a field was observed.
    None means the field was absent or not supplied.
    'UNKNOWN' means the field was observed, but its factual value could not be determined.
    """
    observation_id: str
    schema_version: str
    observation_type: ObservationType
    event_time: datetime
    causal_available_time: datetime
    ingest_time: datetime
    source_id: str
    source_kind: SourceKind
    source_position: str
    observation_contract: str
    wire_direction: WireDirection
    direction_basis: DirectionBasis
    finality: Finality
    availability_basis: AvailabilityBasis
    provenance_ref: str
    quality_ref: str
    present_fields: frozenset[str]
    typed_payload: NetworkPayloadType
    visibility: VisibilityProfile = VisibilityProfile()
    identity: ObservationIdentity = ObservationIdentity()
    quality: EvidenceQuality = EvidenceQuality()

    def __post_init__(self) -> None:
        typed_values = (
            (self.observation_type, ObservationType, "observation_type"),
            (self.source_kind, SourceKind, "source_kind"),
            (self.wire_direction, WireDirection, "wire_direction"),
            (self.direction_basis, DirectionBasis, "direction_basis"),
            (self.finality, Finality, "finality"),
            (self.availability_basis, AvailabilityBasis, "availability_basis"),
        )
        for value, expected, name in typed_values:
            if not isinstance(value, expected):
                raise TypeError(f"{name} must be {expected.__name__}")
        if not isinstance(self.visibility, VisibilityProfile):
            raise TypeError("visibility must be VisibilityProfile")
        if not isinstance(self.identity, ObservationIdentity):
            raise TypeError("identity must be ObservationIdentity")
        if not isinstance(self.quality, EvidenceQuality):
            raise TypeError("quality must be EvidenceQuality")
        for name, value in (
            ("event_time", self.event_time),
            ("causal_available_time", self.causal_available_time),
            ("ingest_time", self.ingest_time),
        ):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{name} must be timezone-aware")
        if self.causal_available_time < self.event_time:
            raise ValueError("causal_available_time cannot precede event_time")
        if self.wire_direction is not WireDirection.UNKNOWN and self.direction_basis is DirectionBasis.UNKNOWN:
            raise ValueError("known wire direction requires an explicit direction basis")
        directional_capability = {
            WireDirection.FORWARD: VisibilityCapability.FORWARD_FACTS,
            WireDirection.REVERSE: VisibilityCapability.REVERSE_FACTS,
        }.get(self.wire_direction)
        if (directional_capability is not None
                and self.visibility.state(directional_capability) is CapabilityState.UNAVAILABLE):
            raise ValueError("known wire direction contradicts unavailable directional facts")
        if not isinstance(self.present_fields, frozenset):
            raise TypeError("present_fields must be frozenset[str]")
        if any(not isinstance(name, str) for name in self.present_fields):
            raise TypeError("present_fields entries must be strings")
        if (not self.quality_ref and QualityState.DEGRADED in (
                self.quality.packet_loss, self.quality.sampling,
                self.quality.parser, self.quality.capture_gap)):
            raise ValueError("degraded source quality requires quality_ref provenance")

        payload_types = {
            ObservationType.PACKET: PacketObservation,
            ObservationType.FLOW: FlowObservation,
            ObservationType.DNS: DNSObservation,
            ObservationType.TLS: TLSObservation,
            ObservationType.QUIC: QUICObservation,
        }
        expected_payload = payload_types[self.observation_type]
        if not isinstance(self.typed_payload, expected_payload):
            raise TypeError(f"{self.observation_type.value} requires {expected_payload.__name__}")
        payload_fields = {field.name for field in fields(self.typed_payload)}
        impossible = self.present_fields - payload_fields
        if impossible:
            raise ValueError(f"present_fields not valid for payload: {sorted(impossible)}")
        absent = {name for name in self.present_fields if getattr(self.typed_payload, name) is None}
        if absent:
            raise ValueError(f"None-valued fields cannot be present: {sorted(absent)}")

@dataclass(frozen=True, slots=True)
class RuntimeControlEvent:
    control_event_id: str
    schema_version: str
    control_type: ControlType
    ingest_time: datetime
    typed_payload: Any
    event_time: Optional[datetime] = None
    source_id: Optional[str] = None
    lane_id: Optional[str] = None
    provenance_ref: Optional[str] = None
    quality_ref: Optional[str] = None

# Unions
NetworkObservation = NetworkObservationEnvelope
CanonicalEvent = NetworkObservation | RuntimeControlEvent
