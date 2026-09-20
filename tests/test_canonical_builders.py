from datetime import datetime, timedelta, timezone

import pytest

from evidencegate.domain.enums import (
    CapabilityState, DirectionBasis, Finality, IdentityBasis, QualityState,
    SourceKind, TimestampSemantics, VisibilityCapability, WireDirection,
)
from evidencegate.domain.events import RoleAssignment, VisibilityProfile
from evidencegate.domain.payloads import DNSObservation, PacketObservation, QUICObservation, TLSObservation
from evidencegate.domain.quality import EvidenceQuality
from evidencegate.ingest.builders import (
    DNSCanonicalBuilder, PacketCanonicalBuilder, QUICCanonicalBuilder,
    TLSCanonicalBuilder, merge_quality, parser_error_result, present_fields_from_payload,
)
from evidencegate.ingest.source import RawSourceRecord, SourceManifest


NOW = datetime(2026, 2, 1, tzinfo=timezone.utc)


def manifest(**changes):
    values = dict(
        source_id="replay-a", source_kind=SourceKind.PCAP, capture_start=None,
        capture_end=None, timestamp_semantics=TimestampSemantics.SOURCE_EVENT_TIME,
        input_observation_contract="parsed_v1",
        direction_basis=DirectionBasis.CAPTURE_INTERFACE,
        wire_direction=WireDirection.FORWARD,
    )
    values.update(changes)
    return SourceManifest(**values)


def packet(src="10.0.0.1", dst="10.0.0.2"):
    return PacketObservation(
        lengths={"ip": 20}, observed_l2_facts={}, observed_l3_facts={},
        observed_l4_facts={}, src_address=src, dst_address=dst, src_port=53,
        dst_port=53000, flags=None, sequence_facts=None, fragmentation=None,
        raw_reference=None,
    )


def test_packet_builder_is_deterministic_neutral_and_preserves_ingest_time():
    record = RawSourceRecord(packet(), NOW, "17", Finality.CURRENT)
    ingest = NOW + timedelta(seconds=2)
    kwargs = dict(
        record=record, manifest=manifest(), quality_ref="quality:replay-a",
        ingest_time=ingest,
        declared_observed_fields={"src_address", "dst_address", "src_port", "dst_port"},
    )
    first = PacketCanonicalBuilder().canonicalize(**kwargs)
    second = PacketCanonicalBuilder().canonicalize(**kwargs)
    assert first == second
    assert first.observation_id == "packet:replay-a:17"
    assert first.provenance_ref == "prov:replay-a:17"
    assert first.ingest_time == ingest
    assert first.identity.observed_identifiers == ("10.0.0.1", "10.0.0.2")
    assert first.identity.identifier_basis is IdentityBasis.OBSERVED_IDENTIFIER
    assert first.identity.role_assignments == ()
    assert first.visibility.state(VisibilityCapability.PACKET_FACTS) is CapabilityState.AVAILABLE
    assert first.visibility.state(VisibilityCapability.FORWARD_FACTS) is CapabilityState.AVAILABLE
    assert first.visibility.state(VisibilityCapability.REVERSE_FACTS) is CapabilityState.UNAVAILABLE


def test_reverse_only_packet_never_synthesizes_forward_facts():
    observation = PacketCanonicalBuilder().canonicalize(
        RawSourceRecord(packet(), NOW, 18),
        manifest(wire_direction=WireDirection.REVERSE), "quality", NOW,
        {"src_address", "dst_address"},
    )
    assert observation.visibility.state(VisibilityCapability.REVERSE_FACTS) is CapabilityState.AVAILABLE
    assert observation.visibility.state(VisibilityCapability.FORWARD_FACTS) is CapabilityState.UNAVAILABLE


def test_present_fields_are_source_declared_and_unknown_remains_present():
    payload = packet(src="UNKNOWN", dst=None)
    assert present_fields_from_payload(payload, {"src_address"}) == frozenset({"src_address"})
    with pytest.raises(ValueError, match="None-valued"):
        present_fields_from_payload(payload, {"dst_address"})


def test_dns_clear_visibility_requires_explicit_decoding_and_observed_qname():
    dns = DNSObservation("flow", True, 1, "example.test", "A", None, None, None, "UDP", False)
    record = RawSourceRecord(dns, NOW, 19)
    opaque = DNSCanonicalBuilder().canonicalize(
        record=record, manifest=manifest(), quality_ref="quality", ingest_time=NOW,
        declared_observed_fields={"qname"}, clear_dns_fields=False,
    )
    clear = DNSCanonicalBuilder().canonicalize(
        record=record, manifest=manifest(), quality_ref="quality", ingest_time=NOW,
        declared_observed_fields={"qname"}, clear_dns_fields=True,
    )
    assert opaque.visibility.state(VisibilityCapability.CLEAR_DNS_FIELDS) is CapabilityState.UNKNOWN
    assert clear.visibility.state(VisibilityCapability.CLEAR_DNS_FIELDS) is CapabilityState.AVAILABLE


def test_tls_capabilities_are_independent():
    handshake = TLSObservation("f", "complete", "1", {"version": "1.3"}, None, None, None, None)
    records = TLSObservation("f", "complete", "1", None, {"length": 10}, None, None, None)
    hand_obs = TLSCanonicalBuilder().canonicalize(
        RawSourceRecord(handshake, NOW, 20), manifest(), "quality", NOW,
        {"parsed_handshake_metadata"}, handshake_metadata=True,
    )
    record_obs = TLSCanonicalBuilder().canonicalize(
        RawSourceRecord(records, NOW, 21), manifest(), "quality", NOW,
        {"parsed_record_metadata"}, record_metadata=True,
    )
    assert hand_obs.visibility.state(VisibilityCapability.TLS_HANDSHAKE_METADATA) is CapabilityState.AVAILABLE
    assert hand_obs.visibility.state(VisibilityCapability.TLS_RECORD_METADATA) is CapabilityState.UNKNOWN
    assert record_obs.visibility.state(VisibilityCapability.TLS_RECORD_METADATA) is CapabilityState.AVAILABLE
    assert record_obs.visibility.state(VisibilityCapability.TLS_HANDSHAKE_METADATA) is CapabilityState.UNKNOWN


def test_quic_outer_metadata_does_not_claim_tls_metadata():
    quic = QUICObservation("f", "1", "long", 1200, ["cid"], "1", 0, NOW, [])
    observation = QUICCanonicalBuilder().canonicalize(
        RawSourceRecord(quic, NOW, 22), manifest(), "quality", NOW,
        {"version", "header_type", "length"}, outer_metadata=True,
    )
    assert observation.visibility.state(VisibilityCapability.QUIC_OUTER_METADATA) is CapabilityState.AVAILABLE
    assert observation.visibility.state(VisibilityCapability.TLS_HANDSHAKE_METADATA) is CapabilityState.UNKNOWN
    assert observation.visibility.state(VisibilityCapability.TLS_RECORD_METADATA) is CapabilityState.UNKNOWN


def test_source_quality_propagates_without_improvement():
    source_quality = EvidenceQuality(sampling=QualityState.DEGRADED, packet_loss=QualityState.UNKNOWN)
    observation = PacketCanonicalBuilder().canonicalize(
        RawSourceRecord(packet(), NOW, 23), manifest(quality=source_quality), "quality", NOW,
        {"src_address", "dst_address"},
    )
    assert observation.quality == source_quality


def test_contradictory_quality_fails_loudly():
    with pytest.raises(ValueError, match="contradictory quality"):
        merge_quality(
            EvidenceQuality(sampling=QualityState.CLEAR),
            EvidenceQuality(sampling=QualityState.DEGRADED),
        )


def test_contradictory_visibility_fails_loudly():
    with pytest.raises(ValueError, match="contradictory visibility"):
        DNSCanonicalBuilder().canonicalize(
            record=RawSourceRecord(DNSObservation("f", True, 1, "x", None, None, None, None, "UDP", False), NOW, 24),
            manifest=manifest(visibility=VisibilityProfile(unavailable=frozenset({VisibilityCapability.CLEAR_DNS_FIELDS}))),
            quality_ref="quality", ingest_time=NOW, declared_observed_fields={"qname"},
            clear_dns_fields=True,
        )


def test_explicit_role_assignment_is_the_only_role_path():
    assignment = RoleAssignment("10.0.0.1", "client", IdentityBasis.SOURCE_DECLARED_ROLE)
    observation = PacketCanonicalBuilder().canonicalize(
        RawSourceRecord(packet(), NOW, 25), manifest(), "quality", NOW,
        {"src_address", "dst_address"}, role_assignments=(assignment,),
    )
    assert observation.identity.role_assignments == (assignment,)


def test_parser_failure_is_a_typed_control_result():
    result = parser_error_result(RawSourceRecord(b"bad", NOW, 26), manifest(), NOW, "truncated")
    assert result.observations == ()
    assert result.control_events[0].control_event_id == "parser-error:replay-a:26"
