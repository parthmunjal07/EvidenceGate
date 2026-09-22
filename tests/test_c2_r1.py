"""M7-05 C2-R1 descriptive recurrence measurement contract."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from evidencegate.domain.enums import (
    AvailabilityBasis, DirectionBasis, EvidenceReadiness, Finality, IdentityBasis,
    ObservationType, QualityState, ResultType, ScientificStatus, SourceKind,
    TimestampSemantics, VisibilityCapability, WireDirection,
)
from evidencegate.domain.events import (
    NetworkObservationEnvelope, ObservationIdentity, RoleAssignment,
    VisibilityProfile,
)
from evidencegate.domain.governance import LaneGovernance
from evidencegate.domain.payloads import FlowObservation
from evidencegate.domain.quality import EvidenceQuality
from evidencegate.persistence.sqlite import SqliteWriter
from evidencegate.plugins.providers.c2 import C2R1Plugin, C2R1State
from evidencegate.plugins.providers.c2_config import (
    C2R1Config, REFERENCE_WATERMARK_LATENESS,
)
from evidencegate.plugins.providers.registry import build_mvp_provider_registry
from evidencegate.results.types import InsufficientEvidence, ReviewFinding
from evidencegate.routing.router import LaneTarget, RelevanceRouter
from evidencegate.runtime.dispatcher import EventTimeReorderPolicy
from evidencegate.runtime.supervisor import RuntimeSupervisor


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
LANE = LaneTarget("c2.r1")
SCHEMA = "evidencegate/persistence/schema.sql"
CLAIM_CEILING = (
    "RECURRENT_COMMUNICATION_MEASUREMENT_ONLY; NOT_C2; NOT_MALWARE; "
    "NOT_COMPROMISE; NOT_BENIGN"
)


def config(**changes) -> C2R1Config:
    values = dict(
        config_id="test-c2-r1",
        minimum_history_events=3,
        max_retained_events_per_pair=4,
        state_ttl=timedelta(seconds=30),
        event_basis=TimestampSemantics.FLOW_START,
        client_role_label="client_id",
        peer_role_label="peer_id",
        service_role_label="peer_port",
    )
    values.update(changes)
    return C2R1Config(**values)


def roles(
    *, client="client-a", peer="peer-a", service="443",
    basis=IdentityBasis.SOURCE_DECLARED_ROLE,
):
    return (
        RoleAssignment(client, "client_id", basis),
        RoleAssignment(peer, "peer_id", basis),
        RoleAssignment(service, "peer_port", basis),
    )


def flow(
    second: int,
    *,
    observation_id: str | None = None,
    role_assignments=None,
    payload_start: datetime | None = None,
    present_fields=None,
    counters=None,
    quality=EvidenceQuality(),
) -> NetworkObservationEnvelope:
    event_time = NOW + timedelta(seconds=second)
    start_time = payload_start or event_time
    payload = FlowObservation(
        flow_id_basis="source-record",
        endpoints=("198.51.100.1", "203.0.113.8"),
        protocol=6,
        start_time=start_time,
        end_time=start_time + timedelta(seconds=1),
        export_time=start_time + timedelta(seconds=2),
        supplied_directional_counters=(
            {"bytes_c2s": 100, "packets_c2s": 2} if counters is None else counters
        ),
        exporter_semantics="fixture-declared",
        sampling=None,
        documented_end_state=None,
    )
    fields = present_fields or frozenset({
        "flow_id_basis", "endpoints", "protocol", "start_time", "end_time",
        "export_time", "supplied_directional_counters", "exporter_semantics",
    })
    return NetworkObservationEnvelope(
        observation_id=observation_id or f"flow-{second}",
        schema_version="1.1",
        observation_type=ObservationType.FLOW,
        event_time=event_time,
        causal_available_time=max(event_time, start_time),
        ingest_time=max(event_time, start_time),
        source_id="fixture-source",
        source_kind=SourceKind.FLOW_EXPORT,
        source_position=str(second),
        observation_contract="flow-v1",
        wire_direction=WireDirection.FORWARD,
        direction_basis=DirectionBasis.CLIENT_SERVER_ROLE,
        finality=Finality.TERMINAL,
        availability_basis=AvailabilityBasis.FLOW_END_ONLY,
        provenance_ref=f"prov:{second}",
        quality_ref=f"quality:{second}",
        present_fields=frozenset(fields),
        typed_payload=payload,
        visibility=VisibilityProfile(
            available=frozenset({
                VisibilityCapability.FLOW_FACTS,
                VisibilityCapability.FORWARD_FACTS,
            }),
            unavailable=frozenset({VisibilityCapability.REVERSE_FACTS}),
        ),
        identity=ObservationIdentity(
            observed_identifiers=payload.endpoints,
            identifier_basis=IdentityBasis.OBSERVED_IDENTIFIER,
            role_assignments=roles() if role_assignments is None else role_assignments,
        ),
        quality=quality,
    )


def governance(lane: str = "c2.r1") -> LaneGovernance:
    return LaneGovernance(
        analytic_lane=lane,
        scientific_status=ScientificStatus.EVIDENCE_CONSTRUCTION,
        scientific_phase="C2-R1 factual recurrence measurement",
        scientific_blockers=(),
        claim_ceiling=CLAIM_CEILING,
        governance_version="c2-r1-0.1.0",
        effective_at=NOW,
        allowed_result_types=(
            ResultType.REVIEW_FINDING,
            ResultType.INSUFFICIENT_EVIDENCE,
            ResultType.PREREQUISITE_MISSING,
            ResultType.QUALITY_DEGRADED,
        ),
        ingest_permitted=True,
    )


async def replay(
    arrival,
    *,
    configuration: C2R1Config | None = None,
    watermark_second: int = 100,
):
    plugin = C2R1Plugin(configuration or config(), max_state_entries=20)
    results, controls = [], []

    async def writer(result, target):
        results.append(result)

    async def controls_writer(event):
        controls.append(event)

    supervisor = RuntimeSupervisor(
        {LANE: plugin}, {LANE: governance()}, writer, shard_count=2,
        control_sink=controls_writer,
        reorder_policies={LANE: EventTimeReorderPolicy(20, 200)},
    )
    supervisor.start_all()
    try:
        plans = []
        for item in arrival:
            plans.append(await supervisor.ingest_observation(item))
        await supervisor.dispatchers[LANE].queue.join()
        await supervisor.advance_watermark(
            LANE, NOW + timedelta(seconds=watermark_second)
        )
        key = plugin.state_key(arrival[-1]) if arrival else None
        entry = (
            supervisor.state_stores[LANE].read(
                plugin.manifest().plugin_id, key,
                NOW + timedelta(seconds=watermark_second),
            )
            if key is not None else None
        )
        return plugin, tuple(results), tuple(controls), entry, tuple(plans)
    finally:
        await supervisor.stop_all()


def test_config_is_immutable_validated_and_has_no_hidden_k_default():
    value = config()
    with pytest.raises((AttributeError, TypeError)):
        value.minimum_history_events = 6
    with pytest.raises(ValueError):
        config(minimum_history_events=0)
    with pytest.raises(ValueError):
        config(minimum_history_events=4, max_retained_events_per_pair=3)
    with pytest.raises(ValueError):
        config(state_ttl=timedelta(0))
    assert value.minimum_history_events == 3
    assert value.minimum_history_events != 6


def test_config_hash_is_canonical_and_tracks_every_executable_change():
    baseline = config()
    assert baseline.canonical_hash == config().canonical_hash
    variants = (
        config(minimum_history_events=2),
        config(state_ttl=timedelta(seconds=31)),
        config(client_role_label="client"),
    )
    assert all(item.canonical_hash != baseline.canonical_hash for item in variants)
    # A human-readable config ID is provenance, not executable mechanism input.
    assert config(config_id="renamed").canonical_hash == baseline.canonical_hash


def test_reference_config_maps_active_kit_without_promoting_a_production_default():
    value = C2R1Config.reference_engine_v1()
    assert value.config_id == "c2-reference-config-v1"
    assert value.minimum_history_events == 3
    assert value.max_retained_events_per_pair == 32
    assert value.state_ttl == timedelta(seconds=3600)
    assert value.event_basis is TimestampSemantics.FLOW_START
    assert REFERENCE_WATERMARK_LATENESS == timedelta(seconds=5)


def test_manifest_identity_scope_and_runtime_capacity_are_explicit():
    plugin = C2R1Plugin(config(), max_state_entries=17)
    manifest = plugin.manifest()
    assert manifest.plugin_id == "provider.c2.r1"
    assert manifest.mechanism_id == "C2-M1"
    assert manifest.config_hash == config().canonical_hash
    assert manifest.state_resource_policy.max_entries == 17
    assert manifest.state_resource_policy.max_ttl == config().state_ttl
    with pytest.raises(TypeError):
        C2R1Plugin(config(), max_state_entries=True)


@pytest.mark.parametrize(
    "assignments",
    [
        roles()[1:],
        (roles()[0], roles()[2]),
        roles() + (RoleAssignment(
            "client-b", "client_id", IdentityBasis.POLICY_DECLARED_ROLE
        ),),
        (),
    ],
)
def test_identity_missing_ambiguous_or_observed_only_fails_closed(assignments):
    plugin = C2R1Plugin(config(), max_state_entries=20)
    item = flow(1, role_assignments=assignments)
    assert not plugin.route(item)
    assert plugin.state_key(item) is None


def test_trusted_source_or_policy_roles_qualify_and_key_is_scoped():
    plugin = C2R1Plugin(config(), max_state_entries=20)
    source = flow(1, role_assignments=roles())
    policy = flow(1, role_assignments=roles(basis=IdentityBasis.POLICY_DECLARED_ROLE))
    assert plugin.route(source) and plugin.route(policy)
    assert plugin.state_key(source) == plugin.state_key(policy)
    changed_service = flow(1, role_assignments=roles(service="8443"))
    assert plugin.state_key(changed_service) != plugin.state_key(source)


def test_flow_start_is_required_and_must_equal_canonical_event_time():
    plugin = C2R1Plugin(config(), max_state_entries=20)
    missing = flow(1, present_fields=frozenset({"protocol"}))
    mismatch = flow(1, payload_start=NOW + timedelta(seconds=2))
    assert not plugin.route(missing) and plugin.state_key(missing) is None
    assert not plugin.route(mismatch) and plugin.state_key(mismatch) is None


@pytest.mark.asyncio
async def test_readiness_state_measurement_support_and_prior_state_version():
    plugin, results, _, entry, _ = await replay(
        (flow(0), flow(60), flow(120)), watermark_second=121
    )
    assert [type(item) for item in results] == [
        InsufficientEvidence, InsufficientEvidence, ReviewFinding,
    ]
    assert [item.status_snapshot.readiness for item in results] == [
        EvidenceReadiness.INSUFFICIENT_HISTORY,
        EvidenceReadiness.INSUFFICIENT_HISTORY,
        EvidenceReadiness.READY,
    ]
    assert [item.state_version for item in results] == [None, 1, 2]
    assert all(item.config_hash == plugin.config.canonical_hash for item in results)
    ready = results[-1]
    evidence = ready.evidence.to_value()
    assert evidence["measurements"] == {
        "event_count": 3,
        "history_span_seconds": 120.0,
        "interval_count": 2,
        "iat_mad_seconds": 0.0,
        "iat_median_seconds": 60.0,
    }
    assert ready.source_observation_ids == ("flow-120", "flow-0", "flow-60")
    assert ready.model_refs == ()
    assert ready.claim_ceiling == CLAIM_CEILING
    assert entry is not None and entry.version == 3


@pytest.mark.asyncio
async def test_history_is_bounded_and_oldest_support_is_dropped():
    bounded = config(minimum_history_events=2, max_retained_events_per_pair=3)
    plugin, results, _, entry, _ = await replay(
        tuple(flow(second) for second in (0, 10, 20, 30)),
        configuration=bounded, watermark_second=31,
    )
    assert entry is not None and isinstance(entry.payload, C2R1State)
    assert [event.observation_id for event in entry.payload.events] == [
        "flow-10", "flow-20", "flow-30",
    ]
    final = results[-1]
    assert final.source_observation_ids == ("flow-30", "flow-10", "flow-20")
    assert final.evidence.to_value()["measurements"]["event_count"] == 3


@pytest.mark.asyncio
async def test_reference_engine_parity_and_reordered_arrival_are_identical():
    ordered = await replay((flow(0), flow(60), flow(120)), watermark_second=121)
    reordered = await replay((flow(120), flow(0), flow(60)), watermark_second=121)
    ordered_results, reordered_results = ordered[1], reordered[1]
    assert tuple(item.evidence.canonical_json for item in ordered_results) == tuple(
        item.evidence.canonical_json for item in reordered_results
    )
    assert tuple(item.result_id for item in ordered_results) == tuple(
        item.result_id for item in reordered_results
    )
    final = ordered_results[-1].evidence.to_value()["measurements"]
    assert final == {
        "event_count": 3, "history_span_seconds": 120.0,
        "interval_count": 2, "iat_median_seconds": 60.0,
        "iat_mad_seconds": 0.0,
    }


@pytest.mark.asyncio
async def test_late_event_never_reaches_r1_state_and_watermark_equality_is_admitted():
    plugin = C2R1Plugin(config(minimum_history_events=2), max_state_entries=20)
    results, controls = [], []

    async def writer(result, target):
        results.append(result)

    async def control_writer(event):
        controls.append(event)

    supervisor = RuntimeSupervisor(
        {LANE: plugin}, {LANE: governance()}, writer, shard_count=1,
        control_sink=control_writer,
        reorder_policies={LANE: EventTimeReorderPolicy(10, 100)},
    )
    supervisor.start_all()
    try:
        await supervisor.advance_watermark(LANE, NOW + timedelta(seconds=5))
        await supervisor.ingest_observation(flow(4))
        await supervisor.ingest_observation(flow(5))
        await supervisor.dispatchers[LANE].queue.join()
        assert supervisor.dispatchers[LANE].pending_reorder_count == 1
        await supervisor.advance_watermark(LANE, NOW + timedelta(seconds=6))
        assert len(results) == 1
        assert results[0].source_observation_ids == ("flow-5",)
        assert any(event.control_type.value == "LATE_EVENT_OBSERVED" for event in controls)
    finally:
        await supervisor.stop_all()


@pytest.mark.asyncio
async def test_expiry_resets_history_without_hidden_count():
    short = config(
        minimum_history_events=2,
        max_retained_events_per_pair=3,
        state_ttl=timedelta(seconds=2),
    )
    plugin = C2R1Plugin(short, max_state_entries=20)
    results = []

    async def writer(result, target):
        results.append(result)

    supervisor = RuntimeSupervisor(
        {LANE: plugin}, {LANE: governance()}, writer, shard_count=1,
        reorder_policies={LANE: EventTimeReorderPolicy(10, 100)},
    )
    supervisor.start_all()
    try:
        for item in (flow(0), flow(1)):
            await supervisor.ingest_observation(item)
        await supervisor.dispatchers[LANE].queue.join()
        await supervisor.advance_watermark(LANE, NOW + timedelta(seconds=4))
        assert len(supervisor.state_stores[LANE]) == 0
        await supervisor.ingest_observation(flow(5))
        await supervisor.dispatchers[LANE].queue.join()
        await supervisor.advance_watermark(LANE, NOW + timedelta(seconds=6))
        assert isinstance(results[-1], InsufficientEvidence)
        assert results[-1].evidence.to_value()["observed_event_count"] == 1
        assert results[-1].state_version is None
    finally:
        await supervisor.stop_all()


@pytest.mark.asyncio
async def test_degraded_quality_is_preserved_and_measurement_remains_descriptive():
    degraded = EvidenceQuality(
        packet_loss=QualityState.DEGRADED,
        sampling=QualityState.DEGRADED,
        parser=QualityState.CLEAR,
        capture_gap=QualityState.DEGRADED,
    )
    _, results, _, _, _ = await replay(
        tuple(flow(second, quality=degraded) for second in (0, 10, 20)),
        watermark_second=21,
    )
    ready = results[-1]
    assert ready.quality_snapshot == degraded
    evidence = ready.evidence.to_value()
    assert evidence["capture_quality"]["sampling"] == "DEGRADED"
    assert set(evidence["hard_negative_alternatives"]) == {
        "monitoring", "updater polling", "telemetry", "health checks", "RMM",
        "API automation",
    }
    serialized = ready.evidence.canonical_json.lower()
    assert "score" not in serialized and "probability" not in serialized


@pytest.mark.asyncio
async def test_config_hash_and_structured_evidence_round_trip_sqlite_v3(tmp_path):
    plugin, results, _, _, _ = await replay(
        (flow(0), flow(10), flow(20)), watermark_second=21
    )
    ready = results[-1]
    writer = SqliteWriter(tmp_path / "c2-r1.db", SCHEMA)
    writer.connect()
    try:
        await writer.write_result(ready)
        stored = await writer.get_result(ready.result_id)
        assert stored == ready
        assert stored.config_hash == plugin.config.canonical_hash
    finally:
        writer.close()


def test_default_registry_activation_is_gated_but_zero_to_many_is_compatible():
    plugins, _ = build_mvp_provider_registry(NOW)
    assert "c2" in plugins and plugins["c2"].manifest().mechanism_id is None
    assert "c2.r1" not in plugins

    r1 = C2R1Plugin(config(), max_state_entries=20)
    candidates = dict(plugins)
    del candidates[LaneTarget("c2")]
    candidates[LANE] = r1
    selected = set(RelevanceRouter(candidates).route(flow(0)))
    assert selected == {"ddos", "recon", "unusual_transfer.m1", "c2.r1"}


@pytest.mark.asyncio
async def test_c2_r1_and_transfer_results_remain_independent():
    plugins, governances = build_mvp_provider_registry(NOW)
    r1 = C2R1Plugin(config(), max_state_entries=20)
    scoped_plugins = {
        LANE: r1,
        LaneTarget("unusual_transfer.m1"): plugins["unusual_transfer.m1"],
    }
    scoped_governance = {
        LANE: governance(),
        LaneTarget("unusual_transfer.m1"): governances["unusual_transfer.m1"],
    }
    results = []

    async def writer(result, target):
        results.append((result, target))

    supervisor = RuntimeSupervisor(
        scoped_plugins, scoped_governance, writer, shard_count=1,
        reorder_policies={LANE: EventTimeReorderPolicy(10, 100)},
    )
    supervisor.start_all()
    try:
        for item in (flow(0), flow(10), flow(20)):
            await supervisor.ingest_observation(item)
        for dispatcher in supervisor.dispatchers.values():
            await dispatcher.queue.join()
        await supervisor.advance_watermark(LANE, NOW + timedelta(seconds=21))
        await supervisor.shards["unusual_transfer.m1"][0].queue.join()
        assert sum(target == LANE for _, target in results) == 3
        assert sum(target == "unusual_transfer.m1" for _, target in results) == 3
        assert {result.mechanism_id for result, _ in results} == {
            "C2-M1", "CAT6-EX-M1",
        }
    finally:
        await supervisor.stop_all()
