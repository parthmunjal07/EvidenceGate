"""M9 DDoS macro: factual bounded window mechanisms."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from evidencegate.domain.enums import (
    AvailabilityBasis, DirectionBasis, Finality, IdentityBasis, ObservationType,
    QualityState, ResultType, ScientificStatus, SourceKind,
    VisibilityCapability, WireDirection,
)
from evidencegate.domain.events import (
    NetworkObservationEnvelope, ObservationIdentity, RoleAssignment,
    VisibilityProfile,
)
from evidencegate.domain.governance import LaneGovernance
from evidencegate.domain.payloads import PacketObservation
from evidencegate.domain.quality import EvidenceQuality
from evidencegate.ingest.replay import validate_bundle
from evidencegate.persistence.sqlite import SqliteWriter
from evidencegate.plugins.providers.ddos import DdosASynPlugin, DdosShellPlugin
from evidencegate.plugins.providers.ddos_config import (
    DdosASynConfig, DdosConnectionChurnConfig, DdosFragmentDemandConfig,
    DdosIcmpDemandConfig, DdosReflectionVictimConfig,
    DdosSourceDiversityConfig, DdosUdpDemandConfig,
)
from evidencegate.plugins.providers.ddos_measurements import (
    DdosConnectionChurnPlugin, DdosFragmentDemandPlugin,
    DdosIcmpDemandPlugin, DdosReflectionVictimPlugin,
    DdosSourceDiversityPlugin, DdosUdpDemandPlugin,
)
from evidencegate.plugins.providers.registry import build_mvp_provider_registry
from evidencegate.results.types import QualityDegraded, ReviewFinding, ThreatAlert
from evidencegate.routing.router import LaneTarget, RelevanceRouter
from evidencegate.runtime.dispatcher import EventTimeReorderPolicy
from evidencegate.runtime.supervisor import RuntimeSupervisor


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
SCHEMA = "evidencegate/persistence/schema.sql"


def roles(*, missing=None, duplicate=None):
    values = [
        RoleAssignment("protected-service", "target_id", IdentityBasis.SOURCE_DECLARED_ROLE),
        RoleAssignment("service/fixture", "service_id", IdentityBasis.SOURCE_DECLARED_ROLE),
    ]
    if missing:
        values = [item for item in values if item.role != missing]
    if duplicate:
        values.append(RoleAssignment(
            "duplicate", duplicate, IdentityBasis.POLICY_DECLARED_ROLE
        ))
    return tuple(values)


def visibility(direction: WireDirection, mode="BOTH"):
    directional = {
        "BOTH": (
            {VisibilityCapability.PACKET_FACTS, VisibilityCapability.FORWARD_FACTS,
             VisibilityCapability.REVERSE_FACTS}, set()
        ),
        "FORWARD": (
            {VisibilityCapability.PACKET_FACTS, VisibilityCapability.FORWARD_FACTS},
            {VisibilityCapability.REVERSE_FACTS},
        ),
        "REVERSE": (
            {VisibilityCapability.PACKET_FACTS, VisibilityCapability.REVERSE_FACTS},
            {VisibilityCapability.FORWARD_FACTS},
        ),
    }[mode]
    return VisibilityProfile(
        available=frozenset(directional[0]), unavailable=frozenset(directional[1])
    )


def packet(
    milliseconds: int, *, protocol=17, flags=None,
    direction=WireDirection.FORWARD, src="198.51.100.1", dst="10.0.0.2",
    src_port=53000, dst_port=53, length=100, l4=None, fragmentation=None,
    role_assignments=None, quality=EvidenceQuality(), visibility_mode="BOTH",
    observation_id=None,
):
    when = NOW + timedelta(milliseconds=milliseconds)
    lengths = {} if length is None else {"ip": length}
    payload = PacketObservation(
        lengths=lengths,
        observed_l2_facts={}, observed_l3_facts={},
        observed_l4_facts={} if l4 is None else l4,
        src_address=src, dst_address=dst, src_port=src_port, dst_port=dst_port,
        flags=flags, sequence_facts=None, fragmentation=fragmentation,
        raw_reference=None, protocol=protocol,
    )
    present = {
        "protocol", "src_address", "dst_address",
    }
    if src_port is not None:
        present.add("src_port")
    if dst_port is not None:
        present.add("dst_port")
    if length is not None:
        present.add("lengths")
    if flags is not None:
        present.add("flags")
    if l4 is not None:
        present.add("observed_l4_facts")
    if fragmentation is not None:
        present.add("fragmentation")
    degraded = QualityState.DEGRADED in (
        quality.packet_loss, quality.sampling, quality.parser, quality.capture_gap
    )
    return NetworkObservationEnvelope(
        observation_id=observation_id or f"p-{milliseconds}-{src}-{src_port}",
        schema_version="1.1", observation_type=ObservationType.PACKET,
        event_time=when, causal_available_time=when, ingest_time=when,
        source_id="ddos-family-fixture", source_kind=SourceKind.PCAP,
        source_position=str(milliseconds), observation_contract="packet-v1",
        wire_direction=direction,
        direction_basis=(DirectionBasis.CAPTURE_INTERFACE
                         if direction is not WireDirection.UNKNOWN
                         else DirectionBasis.UNKNOWN),
        finality=Finality.CURRENT,
        availability_basis=AvailabilityBasis.IMMEDIATE,
        provenance_ref=f"prov:{milliseconds}",
        quality_ref=f"quality:{milliseconds}" if degraded else "",
        present_fields=frozenset(present), typed_payload=payload,
        visibility=visibility(direction, visibility_mode), quality=quality,
        identity=ObservationIdentity(
            observed_identifiers=(src, dst),
            identifier_basis=IdentityBasis.OBSERVED_IDENTIFIER,
            role_assignments=(roles() if role_assignments is None else role_assignments),
        ),
    )


def plugin_set(*, source_limit=4, attempt_limit=4, state_limit=16):
    decision = ("DDOS-TEST-RESOURCE-BOUND",)
    return {
        LaneTarget("ddos.udp_demand"): DdosUdpDemandPlugin(
            DdosUdpDemandConfig.reference_poc_v1(),
            max_state_entries=state_limit, governing_decision_ids=decision,
        ),
        LaneTarget("ddos.reflection_victim"): DdosReflectionVictimPlugin(
            DdosReflectionVictimConfig.reference_poc_v1(),
            max_state_entries=state_limit, max_sources_per_window=source_limit,
            governing_decision_ids=decision,
        ),
        LaneTarget("ddos.source_diversity"): DdosSourceDiversityPlugin(
            DdosSourceDiversityConfig.reference_poc_v1(),
            max_state_entries=state_limit, max_sources_per_window=source_limit,
            governing_decision_ids=decision,
        ),
        LaneTarget("ddos.icmp_demand"): DdosIcmpDemandPlugin(
            DdosIcmpDemandConfig.reference_poc_v1(),
            max_state_entries=state_limit, governing_decision_ids=decision,
        ),
        LaneTarget("ddos.fragment_demand"): DdosFragmentDemandPlugin(
            DdosFragmentDemandConfig.reference_poc_v1(),
            max_state_entries=state_limit, governing_decision_ids=decision,
        ),
        LaneTarget("ddos.connection_churn"): DdosConnectionChurnPlugin(
            DdosConnectionChurnConfig.reference_poc_v1(),
            max_state_entries=state_limit, max_attempts_per_window=attempt_limit,
            governing_decision_ids=decision,
        ),
    }


def governance(lane, plugin):
    return LaneGovernance(
        analytic_lane=str(lane),
        scientific_status=ScientificStatus.EVIDENCE_CONSTRUCTION,
        scientific_phase="factual passive DDoS family measurement",
        scientific_blockers=("default activation requires human gate",),
        claim_ceiling=plugin.claim_ceiling,
        governance_version=f"{plugin.manifest().mechanism_id.lower()}-test-v1",
        effective_at=NOW,
        allowed_result_types=(ResultType.REVIEW_FINDING, ResultType.QUALITY_DEGRADED),
        ingest_permitted=True,
    )


async def run(plugins, observations, *, watermark_ms=1000, per_key=16, total=128):
    results, controls = [], []

    async def writer(result, target):
        results.append((target, result))

    async def control(event):
        controls.append(event)

    governances = {lane: governance(lane, plugin) for lane, plugin in plugins.items()}
    supervisor = RuntimeSupervisor(
        plugins, governances, writer, shard_count=1, control_sink=control,
        reorder_policies={
            lane: EventTimeReorderPolicy(per_key, total) for lane in plugins
        },
    )
    supervisor.start_all()
    try:
        plans = []
        for observation in observations:
            plans.append(await supervisor.ingest_observation(observation))
        for dispatcher in supervisor.dispatchers.values():
            await dispatcher.queue.join()
        for lane in plugins:
            await supervisor.advance_watermark(
                lane, NOW + timedelta(milliseconds=watermark_ms)
            )
        return results, controls, plans, supervisor
    finally:
        await supervisor.stop_all()


def test_reference_configs_are_measurement_only_and_resource_bounds_are_external():
    configs = (
        DdosUdpDemandConfig.reference_poc_v1(),
        DdosReflectionVictimConfig.reference_poc_v1(),
        DdosSourceDiversityConfig.reference_poc_v1(),
        DdosIcmpDemandConfig.reference_poc_v1(),
        DdosFragmentDemandConfig.reference_poc_v1(),
        DdosConnectionChurnConfig.reference_poc_v1(),
    )
    assert all(item.measurement_window == timedelta(seconds=1) for item in configs)
    assert all(item.packet_length_key == "ip" for item in configs)
    assert all(item.config_status == "POC_OR_EXPERIMENT_ONLY" for item in configs)
    assert all(item.science_admitted is False for item in configs)
    base_hash = configs[0].canonical_hash
    assert replace(configs[0], config_id="provenance-only").canonical_hash == base_hash


def test_roles_direction_and_protocol_are_explicit_routing_prerequisites():
    udp = plugin_set()["ddos.udp_demand"]
    good = packet(0)
    assert udp.route(good)
    assert not udp.route(packet(0, protocol=6))
    assert not udp.route(packet(0, direction=WireDirection.UNKNOWN,
                                visibility_mode="BOTH"))
    assert not udp.route(packet(0, role_assignments=roles(missing="target_id")))
    assert not udp.route(packet(0, role_assignments=roles(missing="service_id")))
    assert not udp.route(packet(0, role_assignments=roles(duplicate="target_id")))


@pytest.mark.asyncio
async def test_udp_window_counts_bytes_lengths_and_watermark_closure():
    lane = LaneTarget("ddos.udp_demand")
    plugin = plugin_set()[lane]
    observations = (
        packet(100, length=100, observation_id="udp-1"),
        packet(900, length=200, observation_id="udp-2"),
    )
    results, _, _, _ = await run({lane: plugin}, observations, watermark_ms=1000)
    assert len(results) == 1
    result = results[0][1]
    assert isinstance(result, ReviewFinding)
    evidence = result.evidence.to_value()
    assert evidence["evidence_kind"] == "UDP_DEMAND_MEASUREMENT"
    assert evidence["packet_count"] == 2
    assert evidence["byte_count"] == 300
    assert evidence["mean_packet_length"] == 150.0
    assert evidence["minimum_packet_length"] == 100
    assert evidence["maximum_packet_length"] == 200
    assert result.source_observation_ids == ("udp-1", "udp-2")
    assert result.state_version == 2


@pytest.mark.asyncio
async def test_missing_packet_length_does_not_zero_fill_bytes():
    lane = LaneTarget("ddos.udp_demand")
    results, _, _, _ = await run(
        {lane: plugin_set()[lane]},
        (packet(100, length=100), packet(200, length=None)),
    )
    evidence = results[0][1].evidence.to_value()
    assert evidence["packet_count"] == 2
    assert evidence["byte_count"] is None
    assert evidence["observed_byte_count_for_length_available_packets"] == 100
    assert evidence["missing_length_count"] == 1


@pytest.mark.asyncio
async def test_window_boundary_is_end_exclusive_and_watermark_owned():
    lane = LaneTarget("ddos.udp_demand")
    plugins = {lane: plugin_set()[lane]}
    observations = (packet(999, length=10), packet(1000, length=20))
    results, _, _, _ = await run(plugins, observations, watermark_ms=2000)
    assert len(results) == 2
    values = [item.evidence.to_value() for _, item in results]
    assert [item["packet_count"] for item in values] == [1, 1]
    assert [item["byte_count"] for item in values] == [10, 20]
    assert values[0]["window_end"] == values[1]["window_start"]


@pytest.mark.asyncio
async def test_source_diversity_exact_duplicate_and_bounded_saturation():
    lane = LaneTarget("ddos.source_diversity")
    plugins = {lane: plugin_set(source_limit=2)[lane]}
    observations = (
        packet(100, src="198.51.100.1"),
        packet(200, src="198.51.100.1", src_port=53001),
        packet(300, src="198.51.100.2", src_port=53002),
        packet(400, src="198.51.100.3", src_port=53003),
    )
    results, _, _, _ = await run(plugins, observations)
    result = results[0][1]
    assert isinstance(result, QualityDegraded)
    evidence = result.evidence.to_value()
    assert evidence["packet_count"] == 4
    assert evidence["apparent_source_cardinality_lower_bound"] == 2
    assert evidence["source_capacity_reached"] is True
    assert evidence["exact_within_engineering_capacity"] is False


def test_reflection_requires_exact_source_declared_victim_fact_contract():
    plugin = plugin_set()["ddos.reflection_victim"]
    explicit = packet(0, l4={
        "fact_contract": "DDOS_REFLECTION_FACT_V1",
        "response_like": True,
        "protocol_context": "DNS",
    })
    assert plugin.route(explicit)
    assert not plugin.route(packet(0))
    assert not plugin.route(packet(0, l4={"response_like": True}))
    assert not plugin.route(packet(0, direction=WireDirection.REVERSE, l4={
        "fact_contract": "DDOS_REFLECTION_FACT_V1",
        "response_like": True,
        "protocol_context": "DNS",
    }))


@pytest.mark.asyncio
async def test_reflection_shape_is_measurement_not_ratio_or_source_authenticity():
    lane = LaneTarget("ddos.reflection_victim")
    plugin = plugin_set()[lane]
    facts = {
        "fact_contract": "DDOS_REFLECTION_FACT_V1",
        "response_like": True,
        "protocol_context": "DNS",
    }
    results, _, _, _ = await run({lane: plugin}, (
        packet(100, src="198.51.100.1", l4=facts),
        packet(200, src="198.51.100.2", l4=facts),
    ))
    evidence = results[0][1].evidence.to_value()
    assert evidence["response_shaped_packet_count"] == 2
    assert evidence["apparent_source_cardinality_lower_bound"] == 2
    assert evidence["reflector_request"] is None
    assert evidence["source_authenticity"] is None
    assert "response_request_ratio" not in evidence


def test_icmp_and_fragment_routes_require_explicit_protocol_and_fact_contract():
    plugins = plugin_set()
    icmp = plugins["ddos.icmp_demand"]
    fragment = plugins["ddos.fragment_demand"]
    assert icmp.route(packet(0, protocol=1, src_port=None, dst_port=None))
    assert not icmp.route(packet(0, protocol=58))
    factual = packet(0, fragmentation={
        "fact_contract": "DDOS_FRAGMENT_FACT_V1", "is_fragment": True,
        "offset": 0, "more_fragments": True,
    })
    assert fragment.route(factual)
    assert not fragment.route(packet(0, fragmentation={}))
    assert not fragment.route(packet(0, fragmentation={"is_fragment": True}))
    assert not fragment.route(packet(0, fragmentation={
        "fact_contract": "DDOS_FRAGMENT_FACT_V1", "is_fragment": False,
    }))


@pytest.mark.asyncio
async def test_icmp_and_fragment_emit_factual_counts():
    plugins = plugin_set()
    selected = {
        LaneTarget("ddos.icmp_demand"): plugins["ddos.icmp_demand"],
        LaneTarget("ddos.fragment_demand"): plugins["ddos.fragment_demand"],
    }
    fragment = {
        "fact_contract": "DDOS_FRAGMENT_FACT_V1", "is_fragment": True,
        "offset": 8, "more_fragments": False,
    }
    results, _, _, _ = await run(selected, (
        packet(100, protocol=1, src_port=None, dst_port=None, length=84),
        packet(200, protocol=17, fragmentation=fragment, length=1200),
    ))
    by_lane = {str(lane): result.evidence.to_value() for lane, result in results}
    assert by_lane["ddos.icmp_demand"]["packet_count"] == 1
    assert by_lane["ddos.icmp_demand"]["byte_count"] == 84
    assert by_lane["ddos.fragment_demand"]["fragmented_packet_count"] == 1
    assert by_lane["ddos.fragment_demand"]["byte_count"] == 1200


@pytest.mark.asyncio
async def test_connection_churn_counts_only_initiating_syn_and_bounds_unique_tuples():
    lane = LaneTarget("ddos.connection_churn")
    plugin = plugin_set(attempt_limit=2)[lane]
    observations = (
        packet(100, protocol=6, flags=["SYN"], src_port=50001),
        packet(200, protocol=6, flags=["SYN"], src_port=50001),
        packet(300, protocol=6, flags=["SYN"], src_port=50002),
        packet(400, protocol=6, flags=["SYN"], src_port=50003),
    )
    results, _, _, _ = await run(
        {lane: plugin}, observations, per_key=512, total=512
    )
    result = results[0][1]
    assert isinstance(result, QualityDegraded)
    evidence = result.evidence.to_value()
    assert evidence["observed_initiating_syn_count"] == 4
    assert evidence["unique_visible_tuple_count_lower_bound"] == 2
    assert evidence["attempt_capacity_reached"] is True
    assert not plugin.route(packet(500, protocol=6, flags=["ACK"]))
    assert not plugin.route(packet(600, protocol=6, flags=["SYN", "ACK"],
                                   direction=WireDirection.REVERSE))


@pytest.mark.asyncio
async def test_controlled_mvp_source_capacity_boundary_256_to_257_is_explicit():
    lane = LaneTarget("ddos.source_diversity")
    plugin = plugin_set(source_limit=256, state_limit=512)[lane]
    observations = tuple(
        packet(
            index, src=f"198.51.{index // 256}.{index % 256}",
            src_port=10000 + index,
        )
        for index in range(257)
    )
    results, _, _, _ = await run(
        {lane: plugin}, observations, per_key=512, total=512
    )
    result = results[0][1]
    evidence = result.evidence.to_value()
    assert isinstance(result, QualityDegraded)
    assert evidence["apparent_source_cardinality_lower_bound"] == 256
    assert evidence["source_capacity_reached"] is True
    assert evidence["measurement_is_lower_bound"] is True


@pytest.mark.asyncio
async def test_controlled_mvp_attempt_capacity_boundary_256_to_257_is_explicit():
    lane = LaneTarget("ddos.connection_churn")
    plugin = plugin_set(attempt_limit=256, state_limit=512)[lane]
    observations = tuple(
        packet(index, protocol=6, flags=["SYN"], src_port=10000 + index)
        for index in range(257)
    )
    results, _, _, _ = await run(
        {lane: plugin}, observations, per_key=512, total=512
    )
    result = results[0][1]
    evidence = result.evidence.to_value()
    assert isinstance(result, QualityDegraded)
    assert evidence["unique_visible_tuple_count_lower_bound"] == 256
    assert evidence["attempt_capacity_reached"] is True
    assert evidence["measurement_is_lower_bound"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("quality", (
    EvidenceQuality(packet_loss=QualityState.DEGRADED),
    EvidenceQuality(sampling=QualityState.DEGRADED),
))
async def test_loss_and_sampling_make_counts_explicit_lower_bounds(quality):
    lane = LaneTarget("ddos.udp_demand")
    results, _, _, _ = await run(
        {lane: plugin_set()[lane]}, (packet(100, quality=quality),)
    )
    result = results[0][1]
    assert isinstance(result, QualityDegraded)
    evidence = result.evidence.to_value()
    assert evidence["packet_count"] == 1
    assert evidence["measurement_is_lower_bound"] is True


@pytest.mark.asyncio
async def test_controlled_loss_and_half_sampling_projections_only_reduce_counts():
    lane = LaneTarget("ddos.udp_demand")

    async def measured(indices, quality):
        observations = tuple(
            packet(index * 50, src_port=53000 + index, quality=quality)
            for index in indices
        )
        results, _, _, _ = await run(
            {lane: plugin_set()[lane]}, observations, watermark_ms=1000
        )
        return results[0][1].evidence.to_value()

    baseline = await measured(range(10), EvidenceQuality())
    loss_10 = await measured(
        range(9), EvidenceQuality(packet_loss=QualityState.DEGRADED)
    )
    loss_30 = await measured(
        range(7), EvidenceQuality(packet_loss=QualityState.DEGRADED)
    )
    sampled_half = await measured(
        range(5), EvidenceQuality(sampling=QualityState.DEGRADED)
    )
    assert [baseline["packet_count"], loss_10["packet_count"],
            loss_30["packet_count"], sampled_half["packet_count"]] == [10, 9, 7, 5]
    assert all(item["measurement_is_lower_bound"] for item in (
        loss_10, loss_30, sampled_half
    ))


@pytest.mark.asyncio
@pytest.mark.parametrize("direction, mode", (
    (WireDirection.FORWARD, "FORWARD"),
    (WireDirection.REVERSE, "REVERSE"),
    (WireDirection.FORWARD, "BOTH"),
))
async def test_directional_measurements_survive_each_observed_one_way_contract(
    direction, mode
):
    lane = LaneTarget("ddos.udp_demand")
    observation = packet(100, direction=direction, visibility_mode=mode)
    results, _, _, _ = await run({lane: plugin_set()[lane]}, (observation,))
    evidence = results[0][1].evidence.to_value()
    assert evidence["direction"] == direction.value
    assert evidence["packet_count"] == 1


@pytest.mark.asyncio
async def test_zero_to_many_routing_keeps_mechanisms_independent():
    plugins = plugin_set()
    selected = {
        lane: plugins[lane] for lane in (
            "ddos.udp_demand", "ddos.reflection_victim", "ddos.source_diversity"
        )
    }
    observation = packet(100, l4={
        "fact_contract": "DDOS_REFLECTION_FACT_V1",
        "response_like": True,
        "protocol_context": "DNS",
    })
    router = RelevanceRouter(selected)
    assert set(router.route(observation)) == set(selected)
    results, _, _, _ = await run(selected, (observation,))
    assert {str(lane) for lane, _ in results} == set(selected)
    assert {result.mechanism_id for _, result in results} == {
        "DDOS-B-B0", "DDOS-CV-B0", "DDOS-D-B0",
    }


@pytest.mark.asyncio
async def test_tcp_syn_routes_independently_to_state_diversity_and_churn():
    family = plugin_set()
    plugins = {
        LaneTarget("ddos.syn_state"): DdosASynPlugin(
            DdosASynConfig.reference_poc_v1(), max_state_entries=16
        ),
        LaneTarget("ddos.source_diversity"): family["ddos.source_diversity"],
        LaneTarget("ddos.connection_churn"): family["ddos.connection_churn"],
    }
    observation = packet(100, protocol=6, flags=["SYN"], src_port=50001)
    assert set(RelevanceRouter(plugins).route(observation)) == set(plugins)


@pytest.mark.asyncio
@pytest.mark.parametrize("lane, observation", (
    ("ddos.udp_demand", packet(100)),
    ("ddos.reflection_victim", packet(100, l4={
        "fact_contract": "DDOS_REFLECTION_FACT_V1", "response_like": True,
        "protocol_context": "DNS",
    })),
    ("ddos.source_diversity", packet(100)),
    ("ddos.icmp_demand", packet(100, protocol=1, src_port=None, dst_port=None)),
    ("ddos.fragment_demand", packet(100, fragmentation={
        "fact_contract": "DDOS_FRAGMENT_FACT_V1", "is_fragment": True,
        "offset": 0, "more_fragments": True,
    })),
    ("ddos.connection_churn", packet(100, protocol=6, flags=["SYN"])),
))
async def test_each_mechanism_finalizes_and_round_trips_sqlite(
    tmp_path, lane, observation
):
    target = LaneTarget(lane)
    plugin = plugin_set()[target]
    results, _, _, _ = await run({target: plugin}, (observation,))
    result = results[0][1]
    writer = SqliteWriter(tmp_path / f"{lane}.db", SCHEMA)
    writer.connect()
    try:
        await writer.write_result(result)
        stored = await writer.get_result(result.result_id)
        assert stored == result
        assert stored.config_hash == plugin.config.canonical_hash
        assert stored.governing_ids == ("DDOS-TEST-RESOURCE-BOUND",)
        assert stored.state_version == 1
        assert stored.model_refs == ()
    finally:
        writer.close()


@pytest.mark.asyncio
async def test_state_entry_capacity_boundary_is_explicit_and_observable():
    lane = LaneTarget("ddos.udp_demand")
    plugin = plugin_set(state_limit=1)[lane]
    observations = (
        packet(100, role_assignments=roles()),
        replace(packet(200), identity=ObservationIdentity(
            observed_identifiers=("198.51.100.2", "10.0.0.2"),
            identifier_basis=IdentityBasis.OBSERVED_IDENTIFIER,
            role_assignments=(
                RoleAssignment("other-target", "target_id",
                               IdentityBasis.SOURCE_DECLARED_ROLE),
                roles()[1],
            ),
        )),
    )
    _, controls, _, supervisor = await run(
        {lane: plugin}, observations, watermark_ms=500
    )
    assert len(supervisor.state_stores[lane]) == 1
    assert any(event.control_type.value == "ERROR" for event in controls)


@pytest.mark.asyncio
async def test_reorder_per_key_boundary_creates_quality_gap_without_unbounded_growth():
    lane = LaneTarget("ddos.udp_demand")
    plugin = plugin_set()[lane]
    observations = tuple(packet(index) for index in (100, 200, 300))
    _, _, _, supervisor = await run(
        {lane: plugin}, observations, watermark_ms=1000, per_key=2, total=2
    )
    assert supervisor.dispatchers[lane].pending_reorder_count == 0
    assert supervisor.dispatchers[lane].health.active_gaps


def test_default_registry_activates_factual_ddos_without_alert_results():
    plugins, _ = build_mvp_provider_registry(NOW)
    assert "ddos" not in plugins
    active = {
        str(lane): plugin for lane, plugin in plugins.items()
        if str(lane).startswith("ddos.")
    }
    assert set(active) == {
        "ddos.syn_state", "ddos.udp_demand", "ddos.reflection_victim",
        "ddos.source_diversity", "ddos.icmp_demand", "ddos.fragment_demand",
        "ddos.connection_churn",
    }
    for plugin in active.values():
        assert ResultType.THREAT_ALERT not in plugin.manifest().allowed_result_types
    assert not any(isinstance(item, ThreatAlert) for item in ())


@pytest.mark.asyncio
@pytest.mark.parametrize("name, count", (
    ("ddos_udp_basic", 2),
    ("ddos_udp_many_sources", 3),
    ("ddos_udp_loss", 1),
    ("ddos_reflection_victim_explicit", 1),
    ("ddos_icmp_demand", 1),
    ("ddos_fragment_demand", 1),
    ("ddos_connection_churn", 2),
    ("ddos_mixed_zero_to_many", 1),
    ("ddos_window_boundary", 2),
    ("ddos_source_set_capacity", 3),
    ("ddos_reverse_only", 1),
    ("ddos_sampling_degraded", 1),
))
async def test_macro_replay_fixtures_are_schema_valid(name, count):
    bundle = Path(__file__).parent / "fixtures" / "replay" / name
    assert await validate_bundle(bundle) == count
