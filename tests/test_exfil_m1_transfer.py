"""CAT6-EX-M1 only measures declared directional FLOW counters."""
import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from evidencegate.domain.enums import (
    AvailabilityBasis, CapabilityState, DirectionBasis, Finality, ObservationType, ResultType,
    SourceKind, VisibilityCapability, WireDirection,
    TimestampSemantics,
)
from evidencegate.domain.events import NetworkObservationEnvelope, VisibilityProfile
from evidencegate.domain.payloads import FlowObservation, PacketObservation
from evidencegate.ingest.canonicalizer import FlowCanonicalizer
from evidencegate.ingest.source import RawSourceRecord, SourceManifest
from evidencegate.persistence.sqlite import SqliteWriter
from evidencegate.plugins.providers.registry import build_mvp_provider_registry
from evidencegate.registry.plugin import PluginProcessOutcome
from evidencegate.routing.router import RelevanceRouter
from evidencegate.runtime.supervisor import RuntimeSupervisor

NOW = datetime(2026, 3, 2, tzinfo=timezone.utc)
LANE = "unusual_transfer.m1"
PRESENT = frozenset({"flow_id_basis", "endpoints", "protocol", "start_time", "end_time", "supplied_directional_counters", "exporter_semantics"})


def flow(counters={"bytes_c2s": 10}, *, duration=10, visibility=None, sampling=None):
    payload = FlowObservation("exporter-session-key", ("tuple-first", "tuple-second"), 6, NOW,
        NOW + timedelta(seconds=duration), NOW + timedelta(seconds=duration), counters,
        "exporter declares *_c2s as client-to-server", sampling, None)
    present = PRESENT | ({"sampling"} if sampling is not None else set())
    return NetworkObservationEnvelope("flow-m1", "1.1", ObservationType.FLOW, NOW, NOW, NOW,
        "flow-export", SourceKind.FLOW_EXPORT, "1", "flow-v1", WireDirection.FORWARD,
        DirectionBasis.FLOW_EXPORTER, Finality.TERMINAL, AvailabilityBasis.FLOW_END_ONLY,
        "prov:flow-m1", "", frozenset(present), payload,
        visibility or VisibilityProfile(available=frozenset({VisibilityCapability.FLOW_FACTS, VisibilityCapability.FORWARD_FACTS})))


def registry(): return build_mvp_provider_registry(NOW)


def canonical_client_only_flow(counters):
    source = SourceManifest(
        source_id="flow-export", source_kind=SourceKind.FLOW_EXPORT,
        capture_start=None, capture_end=None,
        timestamp_semantics=TimestampSemantics.SOURCE_EVENT_TIME,
        input_observation_contract="flow-v1", direction_basis=DirectionBasis.FLOW_EXPORTER,
        wire_direction=WireDirection.FORWARD,
    )
    return FlowCanonicalizer().canonicalize(
        RawSourceRecord(flow(counters).typed_payload, NOW, "canonical-m1", Finality.TERMINAL),
        source, "quality:flow-m1", NOW,
    ).observations[0]


def test_manifest_and_flow_only_routing():
    plugins, _ = registry(); plugin = plugins[LANE]; manifest = plugin.manifest(); router = RelevanceRouter(plugins)
    assert manifest.mechanism_id == "CAT6-EX-M1" and manifest.accepted_observation_types == (ObservationType.FLOW,)
    assert LANE in router.route(flow())
    packet = NetworkObservationEnvelope("packet", "1.1", ObservationType.PACKET, NOW, NOW, NOW, "p", SourceKind.PCAP, "1", "p", WireDirection.FORWARD, DirectionBasis.CAPTURE_INTERFACE, Finality.CURRENT, AvailabilityBasis.IMMEDIATE, "p", "", frozenset(), PacketObservation({}, {}, {}, {}, None, None, None, None, None, None, None, None), VisibilityProfile(available=frozenset({VisibilityCapability.PACKET_FACTS})))
    assert LANE not in router.route(packet)
    assert LANE not in router.route(flow({"bytes_s2c": 9}))
    assert LANE not in router.route(flow({"unknown_exporter_count": 9}))
    server_only = replace(flow({"bytes_c2s": 9}), wire_direction=WireDirection.REVERSE,
        visibility=VisibilityProfile(
            available=frozenset({VisibilityCapability.FLOW_FACTS, VisibilityCapability.REVERSE_FACTS}),
            unavailable=frozenset({VisibilityCapability.FORWARD_FACTS}),
        ))
    assert LANE not in router.route(server_only)


@pytest.mark.asyncio
async def test_measurement_evidence_rates_sampling_state_and_persistence(tmp_path):
    plugins, gov = registry(); plugin = plugins[LANE]; results = []
    async def collect(result, lane): results.append((result, lane))
    supervisor = RuntimeSupervisor(plugins, gov, collect, shard_count=1); supervisor.start_all()
    try:
        observation = canonical_client_only_flow({"bytes_c2s": 10, "packets_c2s": 2, "bytes_s2c": 4})
        plan = await supervisor.ingest_observation(observation)
        assert set(plan.selected_targets) == {"ddos", "c2", "recon", LANE}
        await asyncio.gather(*(supervisor.dispatchers[lane].queue.join() for lane in plan.selected_targets))
        result, lane = next(item for item in results if item[1] == LANE)
        evidence = result.evidence.to_value()
        assert lane == LANE and result.result_type is ResultType.REVIEW_FINDING and result.state_version is None and result.model_refs == ()
        assert evidence["recognized_directional_counters"] == {"bytes_c2s": 10, "packets_c2s": 2}
        assert evidence["direction_scope"] == "CLIENT_TO_SERVER_ONLY"
        assert evidence["bytes_c2s_per_second"] == 1 and "bytes_s2c_per_second" not in evidence
        assert evidence["endpoints_source_order"] == ["tuple-first", "tuple-second"]
        assert "NO_EXFILTRATION_CONFIRMED" in result.claim_ceiling and "NO_THEFT" in result.claim_ceiling
        assert result.visibility_snapshot.state(VisibilityCapability.REVERSE_FACTS) is CapabilityState.UNAVAILABLE
        assert plugin.state_key(observation) is None and await plugin.on_watermark(NOW, None) == PluginProcessOutcome()
        writer = SqliteWriter(tmp_path / "m1.db", "evidencegate/persistence/schema.sql"); writer.connect()
        await writer.write_result(result); assert await writer.get_result(result.result_id) == result; writer.close()
    finally:
        await supervisor.stop_all()


@pytest.mark.asyncio
async def test_both_visibility_retains_both_counter_directions_and_reverse_rate():
    plugins, _ = registry(); plugin = plugins[LANE]
    both = flow(
        {"bytes_c2s": 10, "packets_c2s": 2, "bytes_s2c": 4, "packets_s2c": 1},
        visibility=VisibilityProfile(available=frozenset({
            VisibilityCapability.FLOW_FACTS, VisibilityCapability.FORWARD_FACTS,
            VisibilityCapability.REVERSE_FACTS,
        })),
    )
    draft = (await plugin.process(both, None, None)).result_drafts[0]
    assert draft.evidence["recognized_directional_counters"] == {
        "bytes_c2s": 10, "packets_c2s": 2, "bytes_s2c": 4, "packets_s2c": 1,
    }
    assert draft.evidence["direction_scope"] == "BIDIRECTIONAL_COUNTERS"
    assert draft.evidence["bytes_s2c_per_second"] == 0.4


@pytest.mark.asyncio
async def test_unknown_and_degraded_reverse_visibility_gate_reverse_counters():
    plugins, _ = registry(); plugin = plugins[LANE]
    unknown = flow(
        {"bytes_c2s": 10, "bytes_s2c": 4},
        visibility=VisibilityProfile(available=frozenset({
            VisibilityCapability.FLOW_FACTS, VisibilityCapability.FORWARD_FACTS,
        })),
    )
    degraded = flow(
        {"bytes_c2s": 10, "bytes_s2c": 4},
        visibility=VisibilityProfile(
            available=frozenset({VisibilityCapability.FLOW_FACTS, VisibilityCapability.FORWARD_FACTS}),
            degraded=frozenset({VisibilityCapability.REVERSE_FACTS}),
        ),
    )
    unknown_draft = (await plugin.process(unknown, None, None)).result_drafts[0]
    degraded_draft = (await plugin.process(degraded, None, None)).result_drafts[0]
    assert unknown_draft.evidence["recognized_directional_counters"] == {"bytes_c2s": 10}
    assert "bytes_s2c_per_second" not in unknown_draft.evidence
    assert degraded_draft.evidence["recognized_directional_counters"] == {"bytes_c2s": 10, "bytes_s2c": 4}
    assert degraded.visibility.state(VisibilityCapability.REVERSE_FACTS) is CapabilityState.DEGRADED


@pytest.mark.asyncio
async def test_client_only_and_both_visibility_produce_distinct_result_ids():
    plugins, gov = registry(); results = []
    async def collect(result, lane):
        if lane == LANE:
            results.append(result)
    supervisor = RuntimeSupervisor(plugins, gov, collect, shard_count=1); supervisor.start_all()
    try:
        client_only = canonical_client_only_flow({"bytes_c2s": 10, "bytes_s2c": 4})
        both = replace(client_only, wire_direction=WireDirection.UNKNOWN,
            direction_basis=DirectionBasis.UNKNOWN, visibility=VisibilityProfile(available=frozenset({
                VisibilityCapability.FLOW_FACTS, VisibilityCapability.FORWARD_FACTS,
                VisibilityCapability.REVERSE_FACTS,
            })))
        degraded = replace(both, visibility=VisibilityProfile(
            available=frozenset({VisibilityCapability.FLOW_FACTS, VisibilityCapability.FORWARD_FACTS}),
            degraded=frozenset({VisibilityCapability.REVERSE_FACTS}),
        ))
        for observation in (client_only, both, degraded):
            await supervisor.ingest_observation(observation)
            await supervisor.dispatchers[LANE].queue.join()
        assert len(results) == 3 and results[0].result_id != results[1].result_id
        assert results[1].visibility_snapshot.state(VisibilityCapability.REVERSE_FACTS) is CapabilityState.AVAILABLE
        assert results[2].visibility_snapshot.state(VisibilityCapability.REVERSE_FACTS) is CapabilityState.DEGRADED
    finally:
        await supervisor.stop_all()


@pytest.mark.asyncio
async def test_small_large_client_only_zero_duration_and_determinism():
    plugins, gov = registry(); plugin = plugins[LANE]
    small = flow({"packets_c2s": 1}, duration=0)
    large = flow({"bytes_c2s": 10_000_000_000}, duration=1)
    assert plugin.route(small) and plugin.route(large)
    small_draft = (await plugin.process(small, None, None)).result_drafts[0]
    large_draft = (await plugin.process(large, None, None)).result_drafts[0]
    assert small_draft.result_type is large_draft.result_type is ResultType.REVIEW_FINDING
    assert small_draft.evidence["duration_seconds"] == 0 and not any("per_second" in key for key in small_draft.evidence)
    assert large_draft.evidence["recognized_directional_counters"] == {"bytes_c2s": 10_000_000_000}
    results = []
    async def collect(result, lane): results.append(result)
    supervisor = RuntimeSupervisor(plugins, gov, collect, shard_count=1); supervisor.start_all()
    try:
        await supervisor.ingest_observation(large); await supervisor.dispatchers[LANE].queue.join(); first = results.pop()
        await supervisor.ingest_observation(large); await supervisor.dispatchers[LANE].queue.join(); assert results.pop().result_id == first.result_id
        changed = replace(large, typed_payload=replace(large.typed_payload, supplied_directional_counters={"bytes_c2s": 2}))
        await supervisor.ingest_observation(changed); await supervisor.dispatchers[LANE].queue.join(); assert results.pop().result_id != first.result_id
    finally:
        await supervisor.stop_all()
