"""Controlled mechanics validation for Category-5 Recon measurements."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from evidencegate.domain.enums import (
    AvailabilityBasis,
    DirectionBasis,
    Finality,
    IdentityBasis,
    ObservationType,
    QualityState,
    ResultType,
    ScientificStatus,
    SourceKind,
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
from evidencegate.domain.payloads import PacketObservation
from evidencegate.domain.quality import EvidenceQuality
from evidencegate.persistence.sqlite import SqliteWriter
from evidencegate.ingest.replay import NdjsonReplaySource, ReplayCanonicalizer, validate_bundle
from evidencegate.plugins.providers.recon import (
    CLAIM_CEILING,
    HARD_NEGATIVE_ALTERNATIVES,
    Recon2DPlugin,
    ReconHPlugin,
    ReconTcpPlugin,
    ReconVPlugin,
)
from evidencegate.plugins.providers.recon_config import ReconConfig
from evidencegate.plugins.providers.registry import build_mvp_provider_registry
from evidencegate.results.types import InsufficientEvidence, ReviewFinding, ThreatAlert
from evidencegate.routing.router import LaneTarget
from evidencegate.runtime.dispatcher import EventTimeReorderPolicy
from evidencegate.runtime.supervisor import RuntimeSupervisor


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
SCHEMA = "evidencegate/persistence/schema.sql"


def config(**changes) -> ReconConfig:
    values = dict(
        config_id="test-recon",
        horizons=(timedelta(seconds=10), timedelta(seconds=60)),
        max_events_per_key=8,
        state_ttl=timedelta(seconds=60),
        initiator_role_label="initiator_id",
        target_role_label="target_id",
    )
    values.update(changes)
    return ReconConfig(**values)


def packet(
    second: int,
    *,
    target: str = "192.0.2.10",
    target_port: int = 443,
    initiator_port: int = 50000,
    flags: tuple[str, ...] = ("SYN",),
    direction: WireDirection = WireDirection.FORWARD,
    observation_id: str | None = None,
    quality: EvidenceQuality = EvidenceQuality(
        packet_loss=QualityState.CLEAR,
        sampling=QualityState.CLEAR,
        parser=QualityState.CLEAR,
        capture_gap=QualityState.CLEAR,
    ),
    roles: tuple[RoleAssignment, ...] | None = None,
    protocol: int | None = 6,
) -> NetworkObservationEnvelope:
    initiator = "198.51.100.10"
    forward = direction is WireDirection.FORWARD
    payload = PacketObservation(
        lengths={"ip": 40},
        observed_l2_facts={},
        observed_l3_facts={},
        observed_l4_facts={},
        src_address=initiator if forward else target,
        dst_address=target if forward else initiator,
        src_port=initiator_port if forward else target_port,
        dst_port=target_port if forward else initiator_port,
        flags=list(flags),
        sequence_facts=None,
        fragmentation=None,
        raw_reference=f"fixture:{second}",
        protocol=protocol,
    )
    assignments = (
        roles
        if roles is not None
        else (
            RoleAssignment(initiator, "initiator_id", IdentityBasis.SOURCE_DECLARED_ROLE),
            RoleAssignment(target, "target_id", IdentityBasis.SOURCE_DECLARED_ROLE),
        )
    )
    direction_capability = (
        VisibilityCapability.FORWARD_FACTS if forward else VisibilityCapability.REVERSE_FACTS
    )
    other_capability = (
        VisibilityCapability.REVERSE_FACTS if forward else VisibilityCapability.FORWARD_FACTS
    )
    event_time = NOW + timedelta(seconds=second)
    return NetworkObservationEnvelope(
        observation_id=observation_id
        or f"packet-{second}-{target}-{target_port}-{direction.value}",
        schema_version="1.1",
        observation_type=ObservationType.PACKET,
        event_time=event_time,
        causal_available_time=event_time,
        ingest_time=event_time,
        source_id="recon-controlled-fixture",
        source_kind=SourceKind.DERIVED,
        source_position=str(second),
        observation_contract="REPLAY_TYPED_V1",
        wire_direction=direction,
        direction_basis=DirectionBasis.CAPTURE_INTERFACE,
        finality=Finality.CURRENT,
        availability_basis=AvailabilityBasis.IMMEDIATE,
        provenance_ref=f"prov:{second}",
        quality_ref=f"quality:{second}",
        present_fields=frozenset(
            {
                "lengths",
                "protocol",
                "observed_l4_facts",
                "src_address",
                "dst_address",
                "src_port",
                "dst_port",
                "flags",
                "raw_reference",
            }
        ),
        typed_payload=payload,
        visibility=VisibilityProfile(
            available=frozenset({VisibilityCapability.PACKET_FACTS, direction_capability}),
            unavailable=frozenset({other_capability}),
        ),
        identity=ObservationIdentity(
            observed_identifiers=(initiator, target),
            identifier_basis=IdentityBasis.OBSERVED_IDENTIFIER,
            role_assignments=assignments,
        ),
        quality=quality,
    )


def governance(lane: LaneTarget) -> LaneGovernance:
    return LaneGovernance(
        analytic_lane=str(lane),
        scientific_status=ScientificStatus.EVIDENCE_CONSTRUCTION,
        scientific_phase="Category-5 factual measurement mechanics",
        scientific_blockers=(),
        claim_ceiling=CLAIM_CEILING,
        governance_version="recon-mechanics-0.1.0",
        effective_at=NOW,
        allowed_result_types=(
            ResultType.REVIEW_FINDING,
            ResultType.INSUFFICIENT_EVIDENCE,
            ResultType.QUALITY_DEGRADED,
        ),
        ingest_permitted=True,
    )


async def replay(plugins, observations, *, watermark_second=None, writer=None):
    lanes = {LaneTarget(name): plugin for name, plugin in plugins.items()}
    results = []

    async def collect(result, target):
        results.append((target, result))
        if writer is not None:
            await writer(result)

    supervisor = RuntimeSupervisor(
        lanes,
        {lane: governance(lane) for lane in lanes},
        collect,
        shard_count=2,
        reorder_policies={lane: EventTimeReorderPolicy(32, 256) for lane in lanes},
    )
    supervisor.start_all()
    try:
        plans = [await supervisor.ingest_observation(item) for item in observations]
        for lane in lanes:
            await supervisor.dispatchers[lane].queue.join()
        boundary = watermark_second
        if boundary is None:
            boundary = (
                max(
                    (int((item.event_time - NOW).total_seconds()) for item in observations),
                    default=0,
                )
                + 1
            )
        for lane in lanes:
            await supervisor.advance_watermark(lane, NOW + timedelta(seconds=boundary))
        return tuple(results), tuple(plans), supervisor
    finally:
        await supervisor.stop_all()


def evidence(result):
    return result.evidence.to_value()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("name", "count"),
    (
        ("recon_activity_cases", 16),
        ("recon_forward_only", 2),
        ("recon_reverse_only", 1),
        ("recon_loss_degraded", 1),
        ("recon_midstream_response", 1),
    ),
)
async def test_typed_replay_fixtures_validate(name, count):
    assert await validate_bundle(Path("tests/fixtures/replay") / name) == count


@pytest.mark.asyncio
async def test_replay_fixture_roles_direction_and_protocol_reach_mechanisms():
    source = NdjsonReplaySource(Path("tests/fixtures/replay/recon_activity_cases"))
    manifest = await source.open()
    canonicalizer = ReplayCanonicalizer()
    try:
        observations = []
        async for record in source.records():
            observations.extend(
                canonicalizer.canonicalize(
                    record, manifest, f"quality:{record.position}", record.timestamp
                ).observations
            )
    finally:
        await source.close()
    h_plugin = ReconHPlugin(config(), max_state_entries=20)
    tcp_plugin = ReconTcpPlugin(config(), max_state_entries=20)
    assert sum(h_plugin.route(item) for item in observations) == 13
    assert sum(tcp_plugin.route(item) for item in observations) == 16


def test_config_is_explicit_immutable_and_horizons_are_not_defaults():
    value = config()
    with pytest.raises((AttributeError, TypeError)):
        value.max_events_per_key = 10
    with pytest.raises(ValueError):
        config(horizons=(timedelta(seconds=60), timedelta(seconds=10)))
    with pytest.raises(ValueError):
        config(state_ttl=timedelta(seconds=30))
    with pytest.raises(ValueError):
        config(max_events_per_key=0)
    assert value.canonical_hash == config(config_id="renamed").canonical_hash
    assert ReconConfig.controlled_fixture_v1().config_id == "recon-controlled-fixture-v1"
    mvp = ReconConfig.controlled_mvp_v1()
    assert mvp.config_id == "recon-controlled-mvp-v1"
    assert mvp.horizons == (timedelta(seconds=60), timedelta(seconds=3600))
    assert mvp.max_events_per_key == 16
    assert mvp.state_ttl == timedelta(seconds=3600)
    assert mvp.canonical_hash == replace(mvp, config_id="renamed").canonical_hash


def test_manifests_are_independent_bounded_and_default_registry_is_active():
    plugins = [
        cls(config(), max_state_entries=17)
        for cls in (ReconHPlugin, ReconVPlugin, Recon2DPlugin, ReconTcpPlugin)
    ]
    assert [item.manifest().mechanism_id for item in plugins] == [
        "RECON-H",
        "RECON-V",
        "RECON-2D",
        "RECON-TCP",
    ]
    assert all(item.manifest().state_resource_policy.max_entries == 17 for item in plugins)
    registry, _ = build_mvp_provider_registry(NOW)
    assert "recon" not in registry
    assert {str(lane) for lane in registry if str(lane).startswith("recon.")} == {
        "recon.h",
        "recon.v",
        "recon.2d",
        "recon.tcp",
    }
    for lane in ("recon.h", "recon.v", "recon.2d", "recon.tcp"):
        active = registry[lane]
        assert active.config == ReconConfig.controlled_mvp_v1()
        assert active.manifest().state_resource_policy.max_entries == 1024


def test_direction_and_trusted_roles_fail_closed():
    plugin = ReconHPlugin(config(), max_state_entries=20)
    missing_roles = packet(0, roles=())
    mismatched = packet(
        0,
        roles=(
            RoleAssignment("wrong", "initiator_id", IdentityBasis.SOURCE_DECLARED_ROLE),
            RoleAssignment("192.0.2.10", "target_id", IdentityBasis.SOURCE_DECLARED_ROLE),
        ),
    )
    unknown = replace(
        packet(0),
        wire_direction=WireDirection.UNKNOWN,
        direction_basis=DirectionBasis.UNKNOWN,
    )
    assert not plugin.route(missing_roles)
    assert not plugin.route(mismatched)
    assert not plugin.route(unknown)
    assert not plugin.route(packet(0, protocol=17))


def test_observed_l4_protocol_fallback_is_rejected():
    plugin = ReconHPlugin(config(), max_state_entries=20)
    canonical = packet(0)
    payload = replace(
        canonical.typed_payload,
        protocol=None,
        observed_l4_facts={"protocol": 6},
    )
    compatibility_only = replace(
        canonical,
        typed_payload=payload,
        present_fields=(canonical.present_fields - {"protocol"}) | {"observed_l4_facts"},
    )
    assert not plugin.route(compatibility_only)


@pytest.mark.asyncio
async def test_horizontal_breadth_deduplicates_hosts_but_counts_retries():
    plugin = ReconHPlugin(config(), max_state_entries=20)
    results, _, _ = await replay(
        {"recon.h": plugin},
        (
            packet(0, target="192.0.2.1"),
            packet(1, target="192.0.2.1", observation_id="retry"),
            packet(2, target="192.0.2.2"),
        ),
    )
    final = evidence(results[-1][1])["measurements"]
    assert final["distinct_hosts"] == 2
    assert final["attempt_count"] == 3


@pytest.mark.asyncio
async def test_vertical_breadth_deduplicates_ports_but_counts_retries():
    plugin = ReconVPlugin(config(), max_state_entries=20)
    results, _, _ = await replay(
        {"recon.v": plugin},
        (
            packet(0, target_port=22),
            packet(1, target_port=22, observation_id="retry"),
            packet(2, target_port=443),
        ),
    )
    final = evidence(results[-1][1])["measurements"]
    assert final["distinct_ports"] == 2
    assert final["attempt_count"] == 3


@pytest.mark.asyncio
async def test_2d_geometry_and_one_observation_update_multiple_mechanisms():
    plugins = {
        "recon.h": ReconHPlugin(config(), max_state_entries=20),
        "recon.v": ReconVPlugin(config(), max_state_entries=20),
        "recon.2d": Recon2DPlugin(config(), max_state_entries=20),
        "recon.tcp": ReconTcpPlugin(config(), max_state_entries=20),
    }
    observations = (
        packet(0, target="192.0.2.1", target_port=22),
        packet(1, target="192.0.2.1", target_port=443),
        packet(2, target="192.0.2.2", target_port=443),
    )
    results, plans, _ = await replay(plugins, observations)
    assert set(plans[0].selected_targets) == set(map(LaneTarget, plugins))
    assert {result.mechanism_id for _, result in results} == {
        "RECON-H",
        "RECON-V",
        "RECON-2D",
        "RECON-TCP",
    }
    geometry = [result for _, result in results if result.mechanism_id == "RECON-2D"][-1]
    assert evidence(geometry)["measurements"] == {
        "attempt_count": 3,
        "distinct_host_port_pairs": 3,
        "distinct_hosts": 2,
        "distinct_ports": 2,
        "horizon_seconds": 60.0,
    }


@pytest.mark.asyncio
async def test_multi_horizon_slow_activity_and_causal_expiry():
    plugin = Recon2DPlugin(config(), max_state_entries=20)
    results, _, supervisor = await replay(
        {"recon.2d": plugin},
        (
            packet(0, target="192.0.2.1"),
            packet(8, target="192.0.2.2"),
            packet(20, target="192.0.2.3"),
        ),
        watermark_second=81,
    )
    horizons = evidence(results[-1][1])["configured_horizons"]
    assert horizons[0]["attempt_count"] == 1
    assert horizons[1]["attempt_count"] == 3
    lane = LaneTarget("recon.2d")
    assert len(supervisor.state_stores[lane]) == 0


@pytest.mark.asyncio
async def test_forward_only_is_lower_bound_and_reverse_only_does_not_build_breadth():
    quality = EvidenceQuality(
        packet_loss=QualityState.DEGRADED,
        sampling=QualityState.DEGRADED,
        parser=QualityState.CLEAR,
        capture_gap=QualityState.CLEAR,
    )
    forward = packet(0, quality=quality)
    reverse = packet(1, flags=("SYN", "ACK"), direction=WireDirection.REVERSE)
    plugins = {
        "recon.h": ReconHPlugin(config(), max_state_entries=20),
        "recon.tcp": ReconTcpPlugin(config(), max_state_entries=20),
    }
    results, plans, _ = await replay(plugins, (forward, reverse))
    assert plans[0].selected_targets == (LaneTarget("recon.h"), LaneTarget("recon.tcp"))
    assert plans[1].selected_targets == (LaneTarget("recon.tcp"),)
    h_result = next(result for _, result in results if result.mechanism_id == "RECON-H")
    assert evidence(h_result)["quality"]["degraded"] is True
    assert evidence(h_result)["quality"]["count_interpretation"] == "OBSERVED_LOWER_BOUND"


@pytest.mark.asyncio
async def test_reverse_only_midstream_abstains_without_fabricating_attempt():
    plugin = ReconTcpPlugin(config(), max_state_entries=20)
    results, _, supervisor = await replay(
        {"recon.tcp": plugin}, (packet(0, flags=("SYN", "ACK"), direction=WireDirection.REVERSE),)
    )
    result = results[0][1]
    assert isinstance(result, InsufficientEvidence)
    assert evidence(result)["forward_attempt_reconstructed"] is False
    assert len(supervisor.state_stores[LaneTarget("recon.tcp")]) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response_flags", "field"),
    [
        (("SYN", "ACK"), "captured_syn_ack_response_count"),
        (("RST", "ACK"), "captured_rst_response_count"),
    ],
)
async def test_tcp_captured_response_facts(response_flags, field):
    plugin = ReconTcpPlugin(config(), max_state_entries=20)
    observations = [packet(0)]
    observations.append(packet(1, flags=response_flags, direction=WireDirection.REVERSE))
    if response_flags == ("SYN", "ACK"):
        observations.append(packet(2, flags=("ACK",)))
    results, _, _ = await replay({"recon.tcp": plugin}, tuple(observations))
    facts = evidence(results[-1][1])["observed_facts"]
    assert facts[field] == 1
    assert facts["captured_ack_progression_count"] == (1 if response_flags == ("SYN", "ACK") else 0)
    serialized = results[-1][1].evidence.canonical_json.lower()
    assert "open port" not in serialized and "closed port" not in serialized


@pytest.mark.asyncio
async def test_state_event_capacity_is_explicit_and_truncation_visible():
    limited = config(max_events_per_key=2)
    plugin = Recon2DPlugin(limited, max_state_entries=20)
    results, _, _ = await replay(
        {"recon.2d": plugin},
        (
            packet(0, target="192.0.2.1"),
            packet(1, target="192.0.2.2"),
            packet(2, target="192.0.2.3"),
        ),
    )
    state = evidence(results[-1][1])["state_capacity"]
    assert state == {
        "retained_event_count": 2,
        "max_events_per_key": 2,
        "capacity_dropped_event_count": 1,
        "capacity_truncated": True,
    }


@pytest.mark.asyncio
async def test_controlled_mvp_event_capacity_boundary_16_to_17_is_explicit():
    plugin = Recon2DPlugin(ReconConfig.controlled_mvp_v1(), max_state_entries=1024)
    results, _, _ = await replay(
        {"recon.2d": plugin},
        tuple(packet(index, target_port=10000 + index) for index in range(17)),
    )
    state = evidence(results[-1][1])["state_capacity"]
    assert state == {
        "retained_event_count": 16,
        "max_events_per_key": 16,
        "capacity_dropped_event_count": 1,
        "capacity_truncated": True,
    }
    assert evidence(results[-1][1])["quality"]["count_interpretation"] == ("OBSERVED_LOWER_BOUND")


@pytest.mark.asyncio
async def test_event_time_reorder_is_deterministic():
    async def run(order):
        plugin = Recon2DPlugin(config(), max_state_entries=20)
        results, _, _ = await replay({"recon.2d": plugin}, tuple(order), watermark_second=4)
        return tuple(
            (result.result_id, result.evidence.canonical_json, result.state_version)
            for _, result in results
        )

    ordered = (packet(1), packet(2, target_port=22), packet(3, target="192.0.2.3"))
    assert await run(ordered) == await run((ordered[2], ordered[0], ordered[1]))


@pytest.mark.asyncio
async def test_hard_negatives_remain_measurements_without_alert_or_numeric_score():
    plugin = Recon2DPlugin(config(), max_state_entries=20)
    patterns = (
        packet(0),
        packet(1, target_port=80),
        packet(2, target_port=443),
        packet(3, target="192.0.2.20", target_port=443),
    )
    results, _, _ = await replay({"recon.2d": plugin}, patterns)
    assert all(isinstance(result, ReviewFinding) for _, result in results)
    assert not any(isinstance(result, ThreatAlert) for _, result in results)
    final = evidence(results[-1][1])
    assert tuple(final["hard_negative_alternatives"]) == HARD_NEGATIVE_ALTERNATIVES
    assert "score" not in results[-1][1].evidence.canonical_json.lower()
    assert "probability" not in results[-1][1].evidence.canonical_json.lower()


@pytest.mark.asyncio
async def test_sqlite_round_trip_preserves_result_provenance(tmp_path):
    database = tmp_path / "recon.db"
    writer = SqliteWriter(database, SCHEMA)
    writer.connect()
    try:
        plugin = ReconHPlugin(config(), max_state_entries=20)
        results, _, _ = await replay(
            {"recon.h": plugin},
            (packet(0), packet(1, target="192.0.2.20")),
            writer=writer.write_result,
        )
        stored = await writer.get_result(results[-1][1].result_id)
        assert stored is not None
        assert stored.mechanism_id == "RECON-H"
        assert stored.config_hash == config().canonical_hash
        # Runtime records the immutable prior-state version used by evaluation.
        assert stored.state_version == 1
        assert stored.source_observation_ids == results[-1][1].source_observation_ids
        assert stored.claim_ceiling == CLAIM_CEILING
        assert stored.provenance_refs and stored.quality_refs
    finally:
        writer.close()
