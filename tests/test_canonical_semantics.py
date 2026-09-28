"""Executable contract tests for M3-01 canonical observation semantics."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from evidencegate.admission.evaluator import AdmissionEvaluator
from evidencegate.domain.enums import (
    AdmissionReason,
    AvailabilityBasis,
    CapabilityState,
    DirectionBasis,
    Finality,
    IdentityBasis,
    ObservationType,
    QualityFact,
    QualityState,
    ResultType,
    ScientificStatus,
    SourceKind,
    TimestampSemantics,
    VisibilityCapability,
    WireDirection,
)
from evidencegate.domain.events import (
    NetworkObservationEnvelope,
    ObservationIdentity,
    RoleAssignment,
    VisibilityProfile,
)
from evidencegate.domain.governance import LaneGovernance
from evidencegate.domain.payloads import (
    DNSObservation,
    FlowObservation,
    PacketObservation,
    QUICObservation,
    TLSObservation,
)
from evidencegate.domain.quality import EvidenceQuality, QualityRequirement
from evidencegate.ingest.canonicalizer import FlowCanonicalizer
from evidencegate.ingest.source import RawSourceRecord, SourceManifest
from evidencegate.plugins.scaffolds.basic_scaffold import BasicScaffoldPlugin


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def packet(*, src: str | None = "10.0.0.1", dst: str | None = "10.0.0.2") -> PacketObservation:
    return PacketObservation(
        lengths={"ip": 20},
        observed_l2_facts={},
        observed_l3_facts={},
        observed_l4_facts={},
        src_address=src,
        dst_address=dst,
        src_port=None,
        dst_port=None,
        flags=None,
        sequence_facts=None,
        fragmentation=None,
        raw_reference=None,
    )


def envelope(
    payload=None,
    *,
    observation_type: ObservationType = ObservationType.PACKET,
    present_fields: frozenset[str] = frozenset({"src_address", "dst_address"}),
    wire_direction: WireDirection = WireDirection.UNKNOWN,
    direction_basis: DirectionBasis = DirectionBasis.UNKNOWN,
    visibility: VisibilityProfile = VisibilityProfile(),
    identity: ObservationIdentity = ObservationIdentity(),
    quality: EvidenceQuality = EvidenceQuality(),
) -> NetworkObservationEnvelope:
    if payload is None:
        payload = packet()
    return NetworkObservationEnvelope(
        observation_id="obs-1",
        schema_version="1.1",
        observation_type=observation_type,
        event_time=NOW,
        causal_available_time=NOW,
        ingest_time=NOW + timedelta(seconds=1),
        source_id="source-1",
        source_kind=SourceKind.PCAP,
        source_position="1",
        observation_contract=f"{observation_type.value.lower()}_v1",
        wire_direction=wire_direction,
        direction_basis=direction_basis,
        finality=Finality.CURRENT,
        availability_basis=AvailabilityBasis.IMMEDIATE,
        provenance_ref="prov-1",
        quality_ref="quality-1",
        present_fields=present_fields,
        typed_payload=payload,
        visibility=visibility,
        identity=identity,
        quality=quality,
    )


def governance() -> LaneGovernance:
    return LaneGovernance(
        analytic_lane="test",
        scientific_status=ScientificStatus.EVIDENCE_CONSTRUCTION,
        scientific_phase="contract",
        scientific_blockers=(),
        claim_ceiling="REVIEW_FINDING_ONLY",
        governance_version="m3",
        effective_at=NOW,
        allowed_result_types=(ResultType.REVIEW_FINDING,),
        ingest_permitted=True,
    )


def test_envelope_uses_typed_canonical_semantics() -> None:
    observation = envelope()
    assert observation.source_kind is SourceKind.PCAP
    assert observation.wire_direction is WireDirection.UNKNOWN
    assert observation.direction_basis is DirectionBasis.UNKNOWN
    assert observation.finality is Finality.CURRENT
    assert observation.availability_basis is AvailabilityBasis.IMMEDIATE
    with pytest.raises(TypeError, match="source_kind"):
        replace(observation, source_kind="PCAP")


def test_known_direction_requires_basis_and_one_way_profiles_are_valid() -> None:
    with pytest.raises(ValueError, match="direction basis"):
        envelope(wire_direction=WireDirection.FORWARD)

    forward = VisibilityProfile(
        available=frozenset({VisibilityCapability.FORWARD_FACTS}),
        unavailable=frozenset({VisibilityCapability.REVERSE_FACTS}),
    )
    reverse = VisibilityProfile(
        available=frozenset({VisibilityCapability.REVERSE_FACTS}),
        unavailable=frozenset({VisibilityCapability.FORWARD_FACTS}),
    )
    both = VisibilityProfile(
        available=frozenset(
            {
                VisibilityCapability.FORWARD_FACTS,
                VisibilityCapability.REVERSE_FACTS,
            }
        )
    )
    assert (
        envelope(
            wire_direction=WireDirection.FORWARD,
            direction_basis=DirectionBasis.CAPTURE_INTERFACE,
            visibility=forward,
        ).visibility.state(VisibilityCapability.REVERSE_FACTS)
        is CapabilityState.UNAVAILABLE
    )
    assert (
        envelope(
            wire_direction=WireDirection.REVERSE,
            direction_basis=DirectionBasis.CAPTURE_INTERFACE,
            visibility=reverse,
        ).visibility.state(VisibilityCapability.FORWARD_FACTS)
        is CapabilityState.UNAVAILABLE
    )
    assert both.state(VisibilityCapability.FORWARD_FACTS) is CapabilityState.AVAILABLE
    assert both.state(VisibilityCapability.REVERSE_FACTS) is CapabilityState.AVAILABLE


def test_present_missing_and_unknown_are_distinct() -> None:
    represented_unknown = envelope(
        packet(src="UNKNOWN", dst=None),
        present_fields=frozenset({"src_address"}),
    )
    assert "src_address" in represented_unknown.present_fields
    assert represented_unknown.typed_payload.src_address == "UNKNOWN"
    assert "dst_address" not in represented_unknown.present_fields
    assert represented_unknown.typed_payload.dst_address is None
    with pytest.raises(ValueError, match="None-valued"):
        envelope(packet(dst=None), present_fields=frozenset({"dst_address"}))


def test_identity_does_not_infer_roles_from_addresses() -> None:
    observation = envelope(
        identity=ObservationIdentity(
            observed_identifiers=("10.0.0.1", "10.0.0.2"),
            identifier_basis=IdentityBasis.OBSERVED_IDENTIFIER,
        )
    )
    assert observation.identity.role_assignments == ()

    explicit = replace(
        observation,
        identity=ObservationIdentity(
            observed_identifiers=("10.0.0.1", "10.0.0.2"),
            identifier_basis=IdentityBasis.OBSERVED_IDENTIFIER,
            role_assignments=(
                RoleAssignment(
                    "10.0.0.1",
                    "client",
                    IdentityBasis.SOURCE_DECLARED_ROLE,
                ),
            ),
        ),
    )
    assert explicit.identity.role_assignments[0].role == "client"
    with pytest.raises(ValueError, match="trusted role basis"):
        RoleAssignment("10.0.0.1", "client", IdentityBasis.OBSERVED_IDENTIFIER)


def test_flow_canonicalizer_separates_event_causal_and_ingest_time() -> None:
    event_time = NOW
    export_time = NOW + timedelta(seconds=10)
    ingest_time = NOW + timedelta(seconds=12)
    flow = FlowObservation(
        flow_id_basis="exporter-order",
        endpoints=("10.0.0.1", "10.0.0.2"),
        protocol=6,
        start_time=event_time,
        end_time=export_time,
        export_time=export_time,
        supplied_directional_counters={"a_to_b": 3},
        exporter_semantics="netflow_v9",
        sampling=None,
        documented_end_state=None,
    )
    manifest = SourceManifest(
        source_id="flow-source",
        source_kind=SourceKind.FLOW_EXPORT,
        capture_start=None,
        capture_end=None,
        timestamp_semantics=TimestampSemantics.SOURCE_EVENT_TIME,
        direction_basis=DirectionBasis.FLOW_EXPORTER,
        wire_direction=WireDirection.FORWARD,
        input_observation_contract="flow_v1",
    )
    observation = (
        FlowCanonicalizer()
        .canonicalize(
            RawSourceRecord(flow, event_time, "7", Finality.TERMINAL),
            manifest,
            "q-flow",
            ingest_time,
        )
        .observations[0]
    )

    assert observation.event_time == event_time
    assert observation.causal_available_time == export_time
    assert observation.ingest_time == ingest_time
    assert observation.finality is Finality.TERMINAL
    assert observation.availability_basis is AvailabilityBasis.FLOW_END_ONLY
    assert (
        observation.visibility.state(VisibilityCapability.FLOW_FACTS) is CapabilityState.AVAILABLE
    )
    assert (
        observation.visibility.state(VisibilityCapability.FORWARD_FACTS)
        is CapabilityState.AVAILABLE
    )
    assert (
        observation.visibility.state(VisibilityCapability.PACKET_FACTS)
        is CapabilityState.UNAVAILABLE
    )
    assert (
        observation.visibility.state(VisibilityCapability.CLEAR_DNS_FIELDS)
        is CapabilityState.UNAVAILABLE
    )
    assert observation.identity.role_assignments == ()

    unknown = (
        FlowCanonicalizer()
        .canonicalize(
            RawSourceRecord(flow, event_time, "8", Finality.UNKNOWN),
            manifest,
            "q-flow",
            ingest_time,
        )
        .observations[0]
    )
    assert unknown.finality is Finality.UNKNOWN


def test_clear_dns_capability_controls_admission_not_field_shape() -> None:
    dns = DNSObservation(
        flow_reference="f1",
        qr_state_decoded=True,
        transaction_id=1,
        qname="example.test",
        qtype="A",
        qclass="IN",
        rcode=None,
        answers=None,
        transport="UDP",
        truncation=False,
    )
    clear = envelope(
        dns,
        observation_type=ObservationType.DNS,
        present_fields=frozenset({"qname"}),
        visibility=VisibilityProfile(
            available=frozenset(
                {
                    VisibilityCapability.CLEAR_DNS_FIELDS,
                }
            )
        ),
    )
    unavailable = replace(
        clear,
        visibility=VisibilityProfile(
            unavailable=frozenset(
                {
                    VisibilityCapability.CLEAR_DNS_FIELDS,
                }
            )
        ),
    )
    manifest = replace(
        BasicScaffoldPlugin().manifest(),
        accepted_observation_types=(ObservationType.DNS,),
        required_visibility_capabilities=frozenset({VisibilityCapability.CLEAR_DNS_FIELDS}),
    )
    assert AdmissionEvaluator.evaluate(clear, manifest, governance()).admitted
    decision = AdmissionEvaluator.evaluate(unavailable, manifest, governance())
    assert not decision.admitted
    assert AdmissionReason.INSUFFICIENT_VISIBILITY in decision.reasons


def test_tls_and_quic_capabilities_are_not_interchangeable() -> None:
    tls = TLSObservation(
        flow_reference="f1",
        tcp_reassembly_state="complete",
        parser_version="1",
        parsed_handshake_metadata={"version": "1.3"},
        parsed_record_metadata=None,
        indexes=None,
        prefix_time=None,
        gaps=None,
    )
    quic = QUICObservation(
        flow_reference="f2",
        version="1",
        header_type="long",
        length=1200,
        visible_connection_ids=[],
        parser_version="1",
        index=0,
        timing=NOW,
        visibility_flags=[],
    )
    tls_observation = envelope(
        tls,
        observation_type=ObservationType.TLS,
        present_fields=frozenset({"parsed_handshake_metadata"}),
        visibility=VisibilityProfile(
            available=frozenset(
                {
                    VisibilityCapability.TLS_HANDSHAKE_METADATA,
                }
            )
        ),
    )
    quic_observation = envelope(
        quic,
        observation_type=ObservationType.QUIC,
        present_fields=frozenset({"version", "header_type", "length"}),
        visibility=VisibilityProfile(
            available=frozenset(
                {
                    VisibilityCapability.QUIC_OUTER_METADATA,
                }
            )
        ),
    )
    manifest = replace(
        BasicScaffoldPlugin().manifest(),
        accepted_observation_types=(ObservationType.TLS, ObservationType.QUIC),
        required_visibility_capabilities=frozenset(
            {
                VisibilityCapability.TLS_HANDSHAKE_METADATA,
            }
        ),
    )
    assert AdmissionEvaluator.evaluate(tls_observation, manifest, governance()).admitted
    assert not AdmissionEvaluator.evaluate(quic_observation, manifest, governance()).admitted
    assert (
        quic_observation.visibility.state(VisibilityCapability.TLS_RECORD_METADATA)
        is CapabilityState.UNKNOWN
    )


def test_quality_requirements_use_facts_not_quality_reference() -> None:
    requirement = QualityRequirement(
        QualityFact.SAMPLING,
        frozenset({QualityState.CLEAR}),
    )
    manifest = replace(
        BasicScaffoldPlugin().manifest(),
        required_quality=(requirement,),
    )
    unknown = envelope()
    assert unknown.quality_ref
    assert not AdmissionEvaluator.evaluate(unknown, manifest, governance()).admitted
    clear = replace(unknown, quality=EvidenceQuality(sampling=QualityState.CLEAR), quality_ref="")
    assert AdmissionEvaluator.evaluate(clear, manifest, governance()).admitted


@pytest.mark.parametrize(
    ("change", "error"),
    [
        ({"event_time": datetime(2026, 1, 1)}, "timezone-aware"),
        ({"causal_available_time": NOW - timedelta(seconds=1)}, "cannot precede"),
        ({"present_fields": frozenset({"qname"})}, "not valid for payload"),
        ({"observation_type": ObservationType.FLOW}, "requires FlowObservation"),
    ],
)
def test_validator_rejects_structural_contradictions(change, error) -> None:
    with pytest.raises((TypeError, ValueError), match=error):
        replace(envelope(), **change)


def test_visibility_profile_rejects_contradictory_capability_states() -> None:
    with pytest.raises(ValueError, match="contradictory"):
        VisibilityProfile(
            available=frozenset({VisibilityCapability.PACKET_FACTS}),
            unavailable=frozenset({VisibilityCapability.PACKET_FACTS}),
        )
