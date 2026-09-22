"""M9-01 DDOS-A-B0 factual TCP SYN/state evidence contract."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from evidencegate.domain.enums import (
    AvailabilityBasis, DirectionBasis, EvidenceReadiness, Finality, IdentityBasis,
    ObservationType, QualityState, ResultType, ScientificStatus, SourceKind,
    VisibilityCapability, WireDirection,
)
from evidencegate.domain.events import (
    NetworkObservationEnvelope, ObservationIdentity, RoleAssignment,
    VisibilityProfile,
)
from evidencegate.domain.governance import LaneGovernance
from evidencegate.domain.payloads import PacketObservation
from evidencegate.domain.quality import EvidenceQuality
from evidencegate.persistence.sqlite import SqliteWriter
from evidencegate.ingest.replay import NdjsonReplaySource, ReplayRunner, validate_bundle
from evidencegate.plugins.providers.ddos import (
    DDOS_A_CLAIM_CEILING, DdosASynPlugin, DdosASynState, DdosShellPlugin,
)
from evidencegate.plugins.providers.ddos_config import DdosASynConfig
from evidencegate.plugins.providers.registry import build_mvp_provider_registry
from evidencegate.results.types import (
    InsufficientEvidence, QualityDegraded, ReviewFinding, ThreatAlert,
)
from evidencegate.routing.router import LaneTarget, RelevanceRouter
from evidencegate.runtime.dispatcher import EventTimeReorderPolicy
from evidencegate.runtime.supervisor import RuntimeSupervisor


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
LANE = LaneTarget("ddos.syn_state")
SCHEMA = "evidencegate/persistence/schema.sql"


def config(**changes) -> DdosASynConfig:
    values = dict(
        config_id="test-ddos-a",
        syn_state_ttl=timedelta(seconds=5),
        target_role_label="target_id",
        service_role_label="service_id",
        tcp_protocol_number=6,
        config_status="POC_OR_EXPERIMENT_ONLY",
        science_admitted=False,
    )
    values.update(changes)
    return DdosASynConfig(**values)


def governance() -> LaneGovernance:
    return LaneGovernance(
        analytic_lane=str(LANE),
        scientific_status=ScientificStatus.EVIDENCE_CONSTRUCTION,
        scientific_phase="factual TCP SYN and captured state evidence",
        scientific_blockers=("default runtime capacities not human-gated",),
        claim_ceiling=DDOS_A_CLAIM_CEILING,
        governance_version="ddos-a-b0-0.1.0",
        effective_at=NOW,
        allowed_result_types=(
            ResultType.REVIEW_FINDING, ResultType.INSUFFICIENT_EVIDENCE,
            ResultType.QUALITY_DEGRADED,
        ),
        ingest_permitted=True,
    )


def roles(*, duplicate=None, omit=None):
    values = [
        RoleAssignment(
            "10.0.0.2", "target_id", IdentityBasis.SOURCE_DECLARED_ROLE
        ),
        RoleAssignment(
            "tcp/443", "service_id", IdentityBasis.SOURCE_DECLARED_ROLE
        ),
    ]
    if omit:
        values = [item for item in values if item.role != omit]
    if duplicate:
        values.append(RoleAssignment(
            "duplicate", duplicate, IdentityBasis.POLICY_DECLARED_ROLE
        ))
    return tuple(values)


def visibility(*, both=True) -> VisibilityProfile:
    if both:
        return VisibilityProfile(available=frozenset({
            VisibilityCapability.PACKET_FACTS,
            VisibilityCapability.FORWARD_FACTS,
            VisibilityCapability.REVERSE_FACTS,
        }))
    return VisibilityProfile(
        available=frozenset({
            VisibilityCapability.PACKET_FACTS,
            VisibilityCapability.FORWARD_FACTS,
        }),
        unavailable=frozenset({VisibilityCapability.REVERSE_FACTS}),
    )


def packet(
    second: int, flags: list[str], direction: WireDirection, *,
    observation_id: str | None = None, protocol: int | None = 6,
    role_assignments=None, visible=None, quality=EvidenceQuality(),
    sequence_facts=None, present_fields=None,
) -> NetworkObservationEnvelope:
    reverse = direction is WireDirection.REVERSE
    payload = PacketObservation(
        lengths={}, observed_l2_facts={}, observed_l3_facts={},
        observed_l4_facts={},
        src_address="10.0.0.2" if reverse else "192.0.2.10",
        dst_address="192.0.2.10" if reverse else "10.0.0.2",
        src_port=443 if reverse else 51000,
        dst_port=51000 if reverse else 443,
        flags=flags, sequence_facts=sequence_facts,
        fragmentation=None, raw_reference=None, protocol=protocol,
    )
    observed = present_fields or frozenset({
        "protocol", "src_address", "dst_address", "src_port", "dst_port",
        "flags",
    })
    if protocol is None:
        observed = observed - {"protocol"}
    when = NOW + timedelta(seconds=second)
    return NetworkObservationEnvelope(
        observation_id=observation_id or f"packet-{second}-{'-'.join(flags)}",
        schema_version="1.1", observation_type=ObservationType.PACKET,
        event_time=when, causal_available_time=when, ingest_time=when,
        source_id="controlled-ddos-fixture", source_kind=SourceKind.PCAP,
        source_position=str(second), observation_contract="packet-v1",
        wire_direction=direction,
        direction_basis=(DirectionBasis.CAPTURE_INTERFACE
                         if direction is not WireDirection.UNKNOWN
                         else DirectionBasis.UNKNOWN),
        finality=Finality.CURRENT,
        availability_basis=AvailabilityBasis.IMMEDIATE,
        provenance_ref=f"prov:{second}", quality_ref=(
            f"quality:{second}" if QualityState.DEGRADED in (
                quality.packet_loss, quality.sampling, quality.parser,
                quality.capture_gap,
            ) else ""
        ),
        present_fields=observed, typed_payload=payload,
        visibility=visible or visibility(), quality=quality,
        identity=ObservationIdentity(
            observed_identifiers=("192.0.2.10", "10.0.0.2"),
            identifier_basis=IdentityBasis.OBSERVED_IDENTIFIER,
            role_assignments=roles() if role_assignments is None else role_assignments,
        ),
    )


async def run(observations, *, watermark_second: int, plugin=None):
    mechanism = plugin or DdosASynPlugin(config(), max_state_entries=16)
    results, controls = [], []

    async def writer(result, target):
        results.append(result)

    async def control_writer(event):
        controls.append(event)

    supervisor = RuntimeSupervisor(
        {LANE: mechanism}, {LANE: governance()}, writer, shard_count=1,
        control_sink=control_writer,
        reorder_policies={LANE: EventTimeReorderPolicy(
            max_buffered_events_per_key=8,
            max_buffered_events_total=32,
        )},
    )
    supervisor.start_all()
    try:
        for observation in observations:
            await supervisor.ingest_observation(observation)
        await supervisor.dispatchers[LANE].queue.join()
        await supervisor.advance_watermark(
            LANE, NOW + timedelta(seconds=watermark_second)
        )
        entry = None
        if observations:
            key = mechanism.state_key(observations[0])
            if key is not None:
                entry = supervisor.state_stores[LANE].read(
                    mechanism.manifest().plugin_id, key,
                    NOW + timedelta(seconds=watermark_second),
                )
        return mechanism, results, controls, entry
    finally:
        await supervisor.stop_all()


def test_packet_protocol_tail_field_is_backward_compatible_and_config_is_frozen():
    old = PacketObservation({}, {}, {}, {}, "a", "b", 1, 2, ["SYN"], None, None, None)
    assert old.protocol is None
    reference = DdosASynConfig.reference_poc_v1()
    assert reference.syn_state_ttl == timedelta(seconds=5)
    assert reference.config_status == "POC_OR_EXPERIMENT_ONLY"
    assert reference.science_admitted is False
    changed_id = replace(reference, config_id="provenance-only-change")
    assert changed_id.canonical_hash == reference.canonical_hash
    assert replace(reference, tcp_protocol_number=7).canonical_hash != reference.canonical_hash


def test_explicit_tcp_protocol_roles_direction_and_supported_flags_are_required():
    plugin = DdosASynPlugin(config(), max_state_entries=16)
    good = packet(0, ["SYN"], WireDirection.FORWARD)
    assert plugin.route(good)
    assert not plugin.route(packet(0, ["SYN"], WireDirection.FORWARD, protocol=None))
    assert not plugin.route(packet(0, ["SYN"], WireDirection.FORWARD, protocol=17))
    assert not plugin.route(replace(
        good, present_fields=good.present_fields - {"protocol"}
    ))
    assert not plugin.route(packet(
        0, ["SYN"], WireDirection.UNKNOWN, visible=VisibilityProfile(
            available=frozenset({VisibilityCapability.PACKET_FACTS})
        )
    ))
    assert not plugin.route(packet(
        0, ["FIN"], WireDirection.FORWARD
    ))
    for invalid_roles in (
        roles(omit="target_id"), roles(omit="service_id"),
        roles(duplicate="target_id"), roles(duplicate="service_id"), (),
    ):
        assert not plugin.route(packet(
            0, ["SYN"], WireDirection.FORWARD,
            role_assignments=invalid_roles,
        ))


def test_normalized_visible_tuple_is_direction_independent_and_role_scoped():
    plugin = DdosASynPlugin(config(), max_state_entries=16)
    syn = packet(0, ["SYN"], WireDirection.FORWARD)
    synack = packet(1, ["SYN", "ACK"], WireDirection.REVERSE)
    assert plugin.state_key(syn) == plugin.state_key(synack)
    changed_role = replace(
        syn,
        identity=replace(syn.identity, role_assignments=(
            RoleAssignment(
                "other-target", "target_id", IdentityBasis.SOURCE_DECLARED_ROLE
            ),
            roles()[1],
        )),
    )
    assert plugin.state_key(changed_role) != plugin.state_key(syn)


@pytest.mark.asyncio
async def test_complete_both_progression_versions_provenance_and_no_later_expiry():
    observations = (
        packet(0, ["SYN"], WireDirection.FORWARD, observation_id="syn"),
        packet(1, ["SYN", "ACK"], WireDirection.REVERSE, observation_id="synack"),
        packet(2, ["ACK"], WireDirection.FORWARD, observation_id="ack"),
    )
    plugin, results, _, entry = await run(observations, watermark_second=10)
    assert [item.evidence.to_value()["state_after"] for item in results] == [
        "SYN_SEEN", "SYNACK_SEEN", "ACK_SEEN",
    ]
    assert [item.state_version for item in results] == [None, 1, 2]
    assert all(isinstance(item, ReviewFinding) for item in results)
    assert results[-1].source_observation_ids == ("ack", "syn", "synack")
    assert results[-1].evidence.to_value()["evidence_kind"] == (
        "CAPTURED_TCP_HANDSHAKE_PROGRESSION_FACT"
    )
    assert results[-1].claim_ceiling == DDOS_A_CLAIM_CEILING
    assert results[-1].config_hash == plugin.config.canonical_hash
    assert results[-1].model_refs == ()
    assert entry is None


@pytest.mark.asyncio
async def test_both_timeout_emits_captured_incomplete_via_real_watermark_expiry():
    _, results, controls, entry = await run((
        packet(0, ["SYN"], WireDirection.FORWARD, observation_id="syn"),
    ), watermark_second=5)
    assert entry is None and len(results) == 2
    expired = results[-1]
    assert isinstance(expired, ReviewFinding)
    evidence = expired.evidence.to_value()
    assert evidence["evidence_kind"] == "CAPTURED_INCOMPLETE_SYN_STATE_EVIDENCE"
    assert evidence["state_before"] == "SYN_SEEN"
    assert evidence["state_after"] == "EXPIRED"
    assert expired.source_observation_ids == ("syn",)
    assert expired.state_version == 1
    assert any(event.control_type.value == "WATERMARK_ADVANCED" for event in controls)


@pytest.mark.asyncio
async def test_forward_only_timeout_abstains_from_reverse_state_claim():
    _, results, _, _ = await run((packet(
        0, ["SYN"], WireDirection.FORWARD, observation_id="syn",
        visible=visibility(both=False),
    ),), watermark_second=5)
    expired = results[-1]
    assert isinstance(expired, InsufficientEvidence)
    evidence = expired.evidence.to_value()
    assert evidence["evidence_kind"] == "REVERSE_TCP_STATE_UNOBSERVABLE"
    assert evidence["missing_evidence"] == ["reverse TCP state evidence"]
    assert "did not reach" not in evidence["statement"]


@pytest.mark.asyncio
async def test_degraded_quality_timeout_preserves_lower_bound_and_weakens_result():
    degraded = EvidenceQuality(
        packet_loss=QualityState.DEGRADED,
        sampling=QualityState.CLEAR,
        parser=QualityState.CLEAR,
        capture_gap=QualityState.CLEAR,
    )
    _, results, _, _ = await run((packet(
        0, ["SYN"], WireDirection.FORWARD, observation_id="syn",
        quality=degraded,
    ),), watermark_second=5)
    expired = results[-1]
    assert isinstance(expired, QualityDegraded)
    evidence = expired.evidence.to_value()
    assert evidence["observed_syn"] is True
    assert evidence["evidence_kind"] == "TCP_SYN_STATE_QUALITY_DEGRADED"
    assert evidence["capture_quality"]["packet_loss"] == "DEGRADED"


@pytest.mark.asyncio
async def test_rst_finalizes_existing_attempt_and_deletes_state():
    _, results, _, entry = await run((
        packet(0, ["SYN"], WireDirection.FORWARD, observation_id="syn"),
        packet(1, ["RST"], WireDirection.REVERSE, observation_id="rst"),
    ), watermark_second=10)
    assert entry is None and len(results) == 2
    assert results[-1].evidence.to_value()["state_after"] == "RST_SEEN"
    assert results[-1].source_observation_ids == ("rst", "syn")


@pytest.mark.asyncio
async def test_midstream_and_wrong_direction_fail_closed_without_persistent_state():
    cases = (
        packet(0, ["SYN", "ACK"], WireDirection.REVERSE),
        packet(0, ["ACK"], WireDirection.FORWARD),
        packet(0, ["RST"], WireDirection.REVERSE),
        packet(0, ["SYN", "ACK"], WireDirection.FORWARD),
        packet(0, ["SYN"], WireDirection.REVERSE),
    )
    for item in cases:
        _, results, _, entry = await run((item,), watermark_second=1)
        assert len(results) == 1 and isinstance(results[0], InsufficientEvidence)
        assert results[0].status_snapshot.readiness is EvidenceReadiness.ABSTAINING
        assert results[0].evidence.to_value()["state_after"] == "UNKNOWN"
        assert results[0].evidence.to_value()["observed_syn"] is False
        assert entry is None


@pytest.mark.asyncio
async def test_retransmission_deduplicates_only_with_declared_sequence_contract():
    with_sequence = (
        packet(0, ["SYN"], WireDirection.FORWARD, observation_id="syn-1",
               sequence_facts={"seq": 100}),
        packet(1, ["SYN"], WireDirection.FORWARD, observation_id="syn-2",
               sequence_facts={"seq": 100}),
    )
    _, results, _, _ = await run(with_sequence, watermark_second=2)
    evidence = results[-1].evidence.to_value()
    assert evidence["raw_syn_observations"] == 2
    assert evidence["recognized_retransmissions"] == 1
    assert evidence["retransmission_deduplication_status"] == (
        "AVAILABLE_RETRANSMISSION_RECOGNIZED"
    )

    without_sequence = tuple(replace(
        item, typed_payload=replace(item.typed_payload, sequence_facts=None)
    ) for item in with_sequence)
    _, results, _, _ = await run(without_sequence, watermark_second=2)
    evidence = results[-1].evidence.to_value()
    assert evidence["raw_syn_observations"] == 2
    assert evidence["recognized_retransmissions"] == 0
    assert evidence["retransmission_deduplication_status"] == "UNAVAILABLE"

    unknown_contract = tuple(replace(
        item, typed_payload=replace(
            item.typed_payload, sequence_facts={"tcp_sequence": 100}
        )
    ) for item in with_sequence)
    _, results, _, _ = await run(unknown_contract, watermark_second=2)
    assert results[-1].evidence.to_value()[
        "retransmission_deduplication_status"
    ] == "UNAVAILABLE"


@pytest.mark.asyncio
async def test_reordered_arrival_is_deterministic_before_watermark():
    ordered = (
        packet(0, ["SYN"], WireDirection.FORWARD, observation_id="syn"),
        packet(1, ["SYN", "ACK"], WireDirection.REVERSE, observation_id="synack"),
        packet(2, ["ACK"], WireDirection.FORWARD, observation_id="ack"),
    )
    first = await run(ordered, watermark_second=3)
    second = await run(tuple(reversed(ordered)), watermark_second=3)
    assert tuple(item.result_id for item in first[1]) == tuple(
        item.result_id for item in second[1]
    )


@pytest.mark.asyncio
async def test_sqlite_v3_round_trip_preserves_ddos_a_result(tmp_path):
    plugin, results, _, _ = await run((
        packet(0, ["SYN"], WireDirection.FORWARD, observation_id="syn"),
        packet(1, ["SYN", "ACK"], WireDirection.REVERSE, observation_id="synack"),
        packet(2, ["ACK"], WireDirection.FORWARD, observation_id="ack"),
    ), watermark_second=3)
    result = results[-1]
    writer = SqliteWriter(tmp_path / "ddos-a.db", SCHEMA)
    writer.connect()
    try:
        await writer.write_result(result)
        stored = await writer.get_result(result.result_id)
        assert stored == result
        assert stored.mechanism_id == "DDOS-A-B0"
        assert stored.config_hash == plugin.config.canonical_hash
        assert stored.source_observation_ids == ("ack", "syn", "synack")
        assert stored.state_version == 2
        assert stored.quality_snapshot == result.quality_snapshot
        assert stored.visibility_snapshot == result.visibility_snapshot
        assert stored.claim_ceiling == DDOS_A_CLAIM_CEILING
    finally:
        writer.close()


def test_no_alert_scoring_fields_and_default_ddos_remains_shell():
    plugin = DdosASynPlugin(config(), max_state_entries=16)
    assert ResultType.THREAT_ALERT not in plugin.manifest().allowed_result_types
    assert plugin.manifest().state_resource_policy.max_entries == 16
    assert plugin.manifest().state_resource_policy.max_ttl == timedelta(seconds=5)
    plugins, _ = build_mvp_provider_registry(NOW)
    assert isinstance(plugins["ddos"], DdosShellPlugin)
    assert "ddos.syn_state" not in plugins
    assert plugins["c2.r1"].manifest().mechanism_id == "C2-M1"
    assert not any(isinstance(value, ThreatAlert) for value in ())


def test_explicit_lane_routes_independently_from_default_shell():
    mechanism = DdosASynPlugin(config(), max_state_entries=16)
    default, _ = build_mvp_provider_registry(NOW)
    router = RelevanceRouter({
        LaneTarget("ddos"): default["ddos"],
        LANE: mechanism,
    })
    assert set(router.route(packet(0, ["SYN"], WireDirection.FORWARD))) == {
        "ddos", "ddos.syn_state",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("name, expected", (
    ("ddos_syn_complete_both", 3),
    ("ddos_syn_incomplete_both", 2),
    ("ddos_syn_forward_only", 2),
    ("ddos_syn_rst", 2),
    ("ddos_syn_midstream", 1),
    ("ddos_syn_retransmission", 2),
))
async def test_controlled_mechanics_replay_fixtures_are_valid(name, expected):
    bundle = Path(__file__).parent / "fixtures" / "replay" / name
    assert await validate_bundle(bundle) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("name, terminal_kind, terminal_type", (
    ("ddos_syn_complete_both", "CAPTURED_TCP_HANDSHAKE_PROGRESSION_FACT", ReviewFinding),
    ("ddos_syn_incomplete_both", "CAPTURED_INCOMPLETE_SYN_STATE_EVIDENCE", ReviewFinding),
    ("ddos_syn_forward_only", "REVERSE_TCP_STATE_UNOBSERVABLE", InsufficientEvidence),
    ("ddos_syn_rst", "CAPTURED_TCP_RESET_FACT", ReviewFinding),
    ("ddos_syn_midstream", "TCP_STATE_HISTORY_INSUFFICIENT", InsufficientEvidence),
    ("ddos_syn_retransmission", "SYN_ARRIVAL_FACT", ReviewFinding),
))
async def test_controlled_fixtures_execute_through_replay_runtime(
    name, terminal_kind, terminal_type
):
    bundle = Path(__file__).parent / "fixtures" / "replay" / name
    mechanism = DdosASynPlugin(config(), max_state_entries=16)
    results = []

    async def writer(result, target):
        results.append(result)

    supervisor = RuntimeSupervisor(
        {LANE: mechanism}, {LANE: governance()}, writer, shard_count=1,
        reorder_policies={LANE: EventTimeReorderPolicy(8, 32)},
    )
    summary = await ReplayRunner(
        NdjsonReplaySource(bundle), supervisor, clock=lambda: NOW
    ).run()
    assert summary.records_read > 0 and results
    assert isinstance(results[-1], terminal_type)
    assert results[-1].evidence.to_value()["evidence_kind"] == terminal_kind
