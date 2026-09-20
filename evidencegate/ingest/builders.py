"""Shared, factual construction of canonical network observations."""
from dataclasses import fields
from datetime import datetime
from typing import Iterable

from evidencegate.domain.enums import (
    AvailabilityBasis, CapabilityState, ControlType, Finality, IdentityBasis,
    ObservationType, QualityFact, QualityState, VisibilityCapability, WireDirection,
)
from evidencegate.domain.events import (
    NetworkObservationEnvelope, ObservationIdentity, RoleAssignment,
    RuntimeControlEvent, VisibilityProfile,
)
from evidencegate.domain.payloads import (
    DNSObservation, FlowObservation, NetworkPayloadType, PacketObservation,
    QUICObservation, TLSObservation,
)
from evidencegate.domain.quality import EvidenceQuality
from evidencegate.ingest.source import RawSourceRecord, SourceManifest


def present_fields_from_payload(
    payload: NetworkPayloadType, declared_observed_fields: Iterable[str],
) -> frozenset[str]:
    """Validate the adapter's factual presence declaration without inferring it."""
    valid = {field.name for field in fields(payload)}
    declared = frozenset(declared_observed_fields)
    unknown = declared - valid
    if unknown:
        raise ValueError(f"declared observed fields not valid for payload: {sorted(unknown)}")
    absent = {name for name in declared if getattr(payload, name) is None}
    if absent:
        raise ValueError(f"None-valued fields cannot be declared observed: {sorted(absent)}")
    return declared


def _profile_facts(profile: VisibilityProfile) -> dict[VisibilityCapability, CapabilityState]:
    return {capability: profile.state(capability) for capability in VisibilityCapability
            if profile.state(capability) is not CapabilityState.UNKNOWN}


def merge_visibility(*profiles: VisibilityProfile) -> VisibilityProfile:
    """Merge factual visibility declarations, rejecting disagreement."""
    merged: dict[VisibilityCapability, CapabilityState] = {}
    for profile in profiles:
        if not isinstance(profile, VisibilityProfile):
            raise TypeError("visibility declarations must be VisibilityProfile")
        for capability, state in _profile_facts(profile).items():
            prior = merged.get(capability)
            if prior is not None and prior is not state:
                raise ValueError(
                    f"contradictory visibility declarations for {capability.value}: "
                    f"{prior.value} versus {state.value}"
                )
            merged[capability] = state
    return VisibilityProfile(
        available=frozenset(cap for cap, state in merged.items()
                            if state is CapabilityState.AVAILABLE),
        unavailable=frozenset(cap for cap, state in merged.items()
                              if state is CapabilityState.UNAVAILABLE),
        degraded=frozenset(cap for cap, state in merged.items()
                            if state is CapabilityState.DEGRADED),
    )


def merge_quality(*qualities: EvidenceQuality) -> EvidenceQuality:
    """Merge factual quality declarations, rejecting disagreement."""
    values: dict[QualityFact, QualityState] = {}
    for quality in qualities:
        if not isinstance(quality, EvidenceQuality):
            raise TypeError("quality declarations must be EvidenceQuality")
        for fact in QualityFact:
            state = quality.state(fact)
            prior = values.get(fact, QualityState.UNKNOWN)
            if prior is not QualityState.UNKNOWN and state is not QualityState.UNKNOWN and prior is not state:
                raise ValueError(
                    f"contradictory quality declarations for {fact.value}: "
                    f"{prior.value} versus {state.value}"
                )
            if state is not QualityState.UNKNOWN:
                values[fact] = state
    return EvidenceQuality(
        packet_loss=values.get(QualityFact.PACKET_LOSS, QualityState.UNKNOWN),
        sampling=values.get(QualityFact.SAMPLING, QualityState.UNKNOWN),
        parser=values.get(QualityFact.PARSER, QualityState.UNKNOWN),
        capture_gap=values.get(QualityFact.CAPTURE_GAP, QualityState.UNKNOWN),
    )


def identity_from_identifiers(
    identifiers: Iterable[str | None],
    role_assignments: Iterable[RoleAssignment] = (),
) -> ObservationIdentity:
    """Construct neutral observed identity; roles must be explicit assignments."""
    observed = tuple(identifier for identifier in identifiers if identifier is not None)
    return ObservationIdentity(
        observed_identifiers=observed,
        identifier_basis=(IdentityBasis.OBSERVED_IDENTIFIER if observed
                          else IdentityBasis.UNKNOWN),
        role_assignments=tuple(role_assignments),
    )


def observation_id(observation_type: ObservationType, source_id: str, position: object) -> str:
    return f"{observation_type.value.lower()}:{source_id}:{position}"


def provenance_ref(source_id: str, position: object) -> str:
    return f"prov:{source_id}:{position}"


def _direction_visibility(direction: WireDirection) -> VisibilityProfile:
    if direction is WireDirection.FORWARD:
        return VisibilityProfile(
            available=frozenset({VisibilityCapability.FORWARD_FACTS}),
            unavailable=frozenset({VisibilityCapability.REVERSE_FACTS}),
        )
    if direction is WireDirection.REVERSE:
        return VisibilityProfile(
            available=frozenset({VisibilityCapability.REVERSE_FACTS}),
            unavailable=frozenset({VisibilityCapability.FORWARD_FACTS}),
        )
    return VisibilityProfile()


class CanonicalObservationBuilder:
    """One validated construction path for all canonical payload types."""

    def build(
        self, *, observation_type: ObservationType, payload: NetworkPayloadType,
        record: RawSourceRecord, manifest: SourceManifest, quality_ref: str,
        ingest_time: datetime, declared_observed_fields: Iterable[str],
        finality: Finality | None = None,
        availability_basis: AvailabilityBasis = AvailabilityBasis.IMMEDIATE,
        causal_available_time: datetime | None = None,
        visibility: VisibilityProfile = VisibilityProfile(),
        quality: EvidenceQuality | None = None,
        identity: ObservationIdentity | None = None,
    ) -> NetworkObservationEnvelope:
        return NetworkObservationEnvelope(
            observation_id=observation_id(observation_type, manifest.source_id, record.position),
            schema_version="1.1", observation_type=observation_type,
            event_time=record.timestamp,
            causal_available_time=(record.timestamp if causal_available_time is None
                                   else causal_available_time),
            ingest_time=ingest_time, source_id=manifest.source_id,
            source_kind=manifest.source_kind, source_position=str(record.position),
            observation_contract=manifest.input_observation_contract,
            wire_direction=manifest.wire_direction,
            direction_basis=manifest.direction_basis,
            finality=record.finality if finality is None else finality,
            availability_basis=availability_basis,
            provenance_ref=provenance_ref(manifest.source_id, record.position),
            quality_ref=quality_ref,
            present_fields=present_fields_from_payload(payload, declared_observed_fields),
            typed_payload=payload,
            visibility=merge_visibility(manifest.visibility, _direction_visibility(manifest.wire_direction), visibility),
            quality=merge_quality(manifest.quality, quality) if quality is not None else manifest.quality,
            identity=ObservationIdentity() if identity is None else identity,
        )


class _PayloadBuilder:
    observation_type: ObservationType
    payload_type: type
    capability: VisibilityCapability

    def __init__(self, common: CanonicalObservationBuilder | None = None) -> None:
        self.common = common or CanonicalObservationBuilder()

    def canonicalize(
        self, record: RawSourceRecord, manifest: SourceManifest, quality_ref: str,
        ingest_time: datetime, declared_observed_fields: Iterable[str], *,
        visibility: VisibilityProfile = VisibilityProfile(),
        quality: EvidenceQuality | None = None,
        role_assignments: Iterable[RoleAssignment] = (),
    ) -> NetworkObservationEnvelope:
        if not isinstance(record.raw_data, self.payload_type):
            raise TypeError(f"{self.observation_type.value} builder requires {self.payload_type.__name__}")
        payload = record.raw_data
        facts = merge_visibility(
            VisibilityProfile(available=frozenset({self.capability})), visibility,
        )
        identifiers: tuple[str | None, ...] = ()
        if isinstance(payload, PacketObservation):
            identifiers = (payload.src_address, payload.dst_address)
        return self.common.build(
            observation_type=self.observation_type, payload=payload, record=record,
            manifest=manifest, quality_ref=quality_ref, ingest_time=ingest_time,
            declared_observed_fields=declared_observed_fields, visibility=facts,
            quality=quality, identity=identity_from_identifiers(identifiers, role_assignments),
        )


class PacketCanonicalBuilder(_PayloadBuilder):
    observation_type = ObservationType.PACKET
    payload_type = PacketObservation
    capability = VisibilityCapability.PACKET_FACTS

    def canonicalize(self, *args: object, **kwargs: object) -> NetworkObservationEnvelope:
        declared = kwargs.get("declared_observed_fields")
        if declared is None and len(args) > 4:
            declared = args[4]
        if not declared:
            raise ValueError("packet availability requires declared observed packet facts")
        return super().canonicalize(*args, **kwargs)


class DNSCanonicalBuilder(_PayloadBuilder):
    observation_type = ObservationType.DNS
    payload_type = DNSObservation
    capability = VisibilityCapability.CLEAR_DNS_FIELDS

    def canonicalize(self, *args: object, clear_dns_fields: bool = False, **kwargs: object) -> NetworkObservationEnvelope:
        visibility = kwargs.pop("visibility", VisibilityProfile())
        if clear_dns_fields:
            declared = frozenset(kwargs["declared_observed_fields"])
            payload = args[0].raw_data if args else kwargs["record"].raw_data
            if "qname" not in declared or payload.qname is None:
                raise ValueError("clear DNS availability requires an observed qname")
            visibility = merge_visibility(
                visibility,
                VisibilityProfile(available=frozenset({VisibilityCapability.CLEAR_DNS_FIELDS})),
            )
        else:
            # A DNS-shaped payload alone carries no clear-field capability.
            return self._without_default_capability(*args, visibility=visibility, **kwargs)
        return super().canonicalize(*args, visibility=visibility, **kwargs)

    def _without_default_capability(self, *args: object, visibility: VisibilityProfile, **kwargs: object) -> NetworkObservationEnvelope:
        record = args[0] if args else kwargs["record"]
        manifest = args[1] if len(args) > 1 else kwargs["manifest"]
        quality_ref = args[2] if len(args) > 2 else kwargs["quality_ref"]
        ingest_time = args[3] if len(args) > 3 else kwargs["ingest_time"]
        declared = kwargs["declared_observed_fields"]
        quality = kwargs.get("quality")
        roles = kwargs.get("role_assignments", ())
        if not isinstance(record.raw_data, DNSObservation):
            raise TypeError("DNS builder requires DNSObservation")
        return self.common.build(
            observation_type=ObservationType.DNS, payload=record.raw_data, record=record,
            manifest=manifest, quality_ref=quality_ref, ingest_time=ingest_time,
            declared_observed_fields=declared, visibility=visibility, quality=quality,
            identity=identity_from_identifiers((), roles),
        )


class TLSCanonicalBuilder(_PayloadBuilder):
    observation_type = ObservationType.TLS
    payload_type = TLSObservation
    capability = VisibilityCapability.TLS_HANDSHAKE_METADATA

    def canonicalize(
        self, record: RawSourceRecord, manifest: SourceManifest, quality_ref: str,
        ingest_time: datetime, declared_observed_fields: Iterable[str], *,
        handshake_metadata: bool = False, record_metadata: bool = False,
        visibility: VisibilityProfile = VisibilityProfile(),
        quality: EvidenceQuality | None = None,
        role_assignments: Iterable[RoleAssignment] = (),
    ) -> NetworkObservationEnvelope:
        if not isinstance(record.raw_data, TLSObservation):
            raise TypeError("TLS builder requires TLSObservation")
        declared = present_fields_from_payload(record.raw_data, declared_observed_fields)
        available: set[VisibilityCapability] = set()
        if handshake_metadata:
            if "parsed_handshake_metadata" not in declared:
                raise ValueError("handshake availability requires observed handshake metadata")
            available.add(VisibilityCapability.TLS_HANDSHAKE_METADATA)
        if record_metadata:
            if "parsed_record_metadata" not in declared:
                raise ValueError("record availability requires observed record metadata")
            available.add(VisibilityCapability.TLS_RECORD_METADATA)
        return self.common.build(
            observation_type=ObservationType.TLS, payload=record.raw_data, record=record,
            manifest=manifest, quality_ref=quality_ref, ingest_time=ingest_time,
            declared_observed_fields=declared, visibility=merge_visibility(
                visibility, VisibilityProfile(available=frozenset(available)),
            ), quality=quality,
            identity=identity_from_identifiers((), role_assignments),
        )


class QUICCanonicalBuilder(_PayloadBuilder):
    observation_type = ObservationType.QUIC
    payload_type = QUICObservation
    capability = VisibilityCapability.QUIC_OUTER_METADATA

    def canonicalize(
        self, record: RawSourceRecord, manifest: SourceManifest, quality_ref: str,
        ingest_time: datetime, declared_observed_fields: Iterable[str], *,
        outer_metadata: bool = False,
        visibility: VisibilityProfile = VisibilityProfile(),
        quality: EvidenceQuality | None = None,
        role_assignments: Iterable[RoleAssignment] = (),
    ) -> NetworkObservationEnvelope:
        if not isinstance(record.raw_data, QUICObservation):
            raise TypeError("QUIC builder requires QUICObservation")
        declared = present_fields_from_payload(record.raw_data, declared_observed_fields)
        if outer_metadata and not declared:
            raise ValueError("QUIC outer availability requires observed outer metadata")
        return self.common.build(
            observation_type=ObservationType.QUIC, payload=record.raw_data, record=record,
            manifest=manifest, quality_ref=quality_ref, ingest_time=ingest_time,
            declared_observed_fields=declared, visibility=merge_visibility(
                visibility,
                VisibilityProfile(available=frozenset({VisibilityCapability.QUIC_OUTER_METADATA})
                                  if outer_metadata else frozenset()),
            ), quality=quality,
            identity=identity_from_identifiers((), role_assignments),
        )


def parser_error_result(
    record: RawSourceRecord, manifest: SourceManifest, ingest_time: datetime, detail: str,
) -> "CanonicalizationResult":
    """Return a factual parser-error control result when an adapter requests tolerance."""
    from evidencegate.ingest.canonicalizer import CanonicalizationResult
    event = RuntimeControlEvent(
        control_event_id=f"parser-error:{manifest.source_id}:{record.position}",
        schema_version="1.1", control_type=ControlType.PARSER_ERROR_OBSERVED,
        ingest_time=ingest_time, event_time=record.timestamp, source_id=manifest.source_id,
        provenance_ref=provenance_ref(manifest.source_id, record.position),
        typed_payload={"detail": detail},
    )
    return CanonicalizationResult(observations=(), control_events=(event,))
