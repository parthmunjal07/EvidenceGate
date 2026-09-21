"""Explicit event-time lifecycle coverage for the generic runtime."""

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from evidencegate.domain.enums import (
    AvailabilityBasis, ControlType, DirectionBasis, EvidenceReadiness, Finality,
    GapAction, ObservationType, ResultType, ScientificStatus, SourceKind,
    WireDirection,
)
from evidencegate.domain.events import NetworkObservationEnvelope
from evidencegate.domain.governance import LaneGovernance
from evidencegate.domain.payloads import PacketObservation
from evidencegate.plugins.scaffolds.basic_scaffold import BasicScaffoldPlugin
from evidencegate.registry.plugin import PluginProcessOutcome, StateKey, StateTransitionRequest
from evidencegate.registry.manifest import StateResourcePolicy
from evidencegate.admission.evaluator import EvaluationReadinessDecision
from evidencegate.results.types import ResultDraft
from evidencegate.runtime.dispatcher import (
    EventTimeReorderPolicy, LaneDispatcher, WatermarkError,
)
from evidencegate.runtime.shard import LaneShard
from evidencegate.runtime.state import StateOperation, StateStore


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
TTL = timedelta(seconds=10)


def observation(number: int, key: str = "a") -> NetworkObservationEnvelope:
    return NetworkObservationEnvelope(
        observation_id=f"event-{key}-{number}", schema_version="1.1",
        observation_type=ObservationType.PACKET, event_time=NOW + timedelta(seconds=number),
        causal_available_time=NOW + timedelta(seconds=number), ingest_time=NOW + timedelta(seconds=number),
        source_id="replay", source_kind=SourceKind.PCAP, source_position=str(number),
        observation_contract="packet_v1", wire_direction=WireDirection.UNKNOWN,
        direction_basis=DirectionBasis.UNKNOWN, finality=Finality.TERMINAL,
        availability_basis=AvailabilityBasis.IMMEDIATE, provenance_ref="prov", quality_ref="quality",
        present_fields=frozenset({"src_address", "dst_address"}),
        typed_payload=PacketObservation(lengths={"ip": 20}, observed_l2_facts={}, observed_l3_facts={},
            observed_l4_facts={}, src_address="10.0.0.1", dst_address="10.0.0.2", src_port=None,
            dst_port=None, flags=[], sequence_facts=None, fragmentation=None, raw_reference=None),
    )


def governance() -> LaneGovernance:
    return LaneGovernance("lane", ScientificStatus.EVIDENCE_CONSTRUCTION, "test", (),
        "REVIEW_FINDING_ONLY", "gov", NOW, (ResultType.REVIEW_FINDING,), True)


class LifecyclePlugin(BasicScaffoldPlugin):
    def __init__(self):
        self.process_calls, self.expired, self.watermarks, self.order = 0, [], [], []
        self.fail_key = None
        self.illegal_callback = None

    def manifest(self):
        return replace(super().manifest(), plugin_id="lifecycle-fixture", gap_action=GapAction.CONTINUE_WITH_QUALITY_FLAG,
                       state_resource_policy=StateResourcePolicy(10, timedelta(minutes=10)))

    def state_key(self, item):
        return StateKey(item.observation_id.split("-")[1])

    async def process(self, item, context, state):
        self.process_calls += 1
        count = 1 if state is None else state.payload["count"] + 1
        return PluginProcessOutcome((), StateTransitionRequest(self.state_key(item), None if state is None else state.version,
            StateOperation.UPSERT, {"count": count}, TTL),
            EvaluationReadinessDecision(EvidenceReadiness.READY))

    async def on_expire(self, key, context, state):
        self.order.append(("expire", str(key)))
        self.expired.append(state)
        if str(key) == self.fail_key:
            raise RuntimeError("expiry fixture failure")
        transition = StateTransitionRequest(key, None, StateOperation.DELETE) if self.illegal_callback == "on_expire" else None
        return PluginProcessOutcome((ResultDraft(ResultType.REVIEW_FINDING, "expiry", (str(key),), ()),), transition)

    async def on_watermark(self, watermark, context):
        self.order.append(("watermark", watermark))
        self.watermarks.append(context)
        transition = StateTransitionRequest(StateKey("bad"), None, StateOperation.DELETE) if self.illegal_callback == "on_watermark" else None
        return PluginProcessOutcome((ResultDraft(ResultType.REVIEW_FINDING, "watermark", (watermark.isoformat(),), ()),), transition)


async def fixture(shards=2):
    plugin, controls, results = LifecyclePlugin(), [], []
    store = StateStore(expire_on_access=False)
    lane_shards = [LaneShard(i, plugin, store, lambda draft: collect(results, draft), control_sink=lambda event: collect(controls, event), lane_id="lane") for i in range(shards)]
    dispatcher = LaneDispatcher("lane", plugin, governance(), lane_shards, shards,
        control_sink=lambda event: collect(controls, event),
        reorder_policy=EventTimeReorderPolicy(10))
    for shard in lane_shards:
        shard.start()
    dispatcher.start()
    return plugin, store, lane_shards, dispatcher, controls, results


async def collect(target, value):
    target.append(value)


async def ingest(dispatcher, shards, item):
    dispatcher.put_nowait(item)
    await asyncio.wait_for(dispatcher.queue.join(), 1)
    for shard in shards:
        await asyncio.wait_for(shard.queue.join(), 1)


async def close(dispatcher, shards):
    await dispatcher.stop()
    for shard in shards:
        await shard.stop()


@pytest.mark.asyncio
async def test_watermark_expiry_order_readiness_and_monotonicity():
    plugin, store, shards, dispatcher, controls, _ = await fixture()
    try:
        await ingest(dispatcher, shards, observation(1, "a"))
        expiry = NOW + timedelta(seconds=11)
        assert await dispatcher.advance_watermark(expiry - timedelta(microseconds=1))
        assert len(store) == 1
        assert await dispatcher.advance_watermark(expiry)
        assert len(store) == 0 and len(plugin.expired) == 1
        assert plugin.expired[0].payload == {"count": 1}
        assert plugin.order[-2] == ("expire", "a") and plugin.order[-1][0] == "watermark"
        assert shards[0].get_readiness("a").readiness is EvidenceReadiness.WARMING_UP or shards[1].get_readiness("a").readiness is EvidenceReadiness.WARMING_UP
        assert controls[-1].control_type is ControlType.WATERMARK_ADVANCED
        watermark_calls = len(plugin.watermarks)
        assert not await dispatcher.advance_watermark(expiry)
        assert len(plugin.expired) == 1 and len(plugin.watermarks) == watermark_calls
        with pytest.raises(WatermarkError):
            await dispatcher.advance_watermark(NOW)
        assert dispatcher.watermark == expiry
        await ingest(dispatcher, shards, observation(12, "a"))
        await dispatcher.advance_watermark(NOW + timedelta(seconds=13))
        owning_shard = next(shard for shard in shards if "a" in shard._key_states)
        assert owning_shard.get_readiness("a").readiness is EvidenceReadiness.READY
    finally:
        await close(dispatcher, shards)


@pytest.mark.asyncio
async def test_late_event_is_observable_and_event_at_watermark_is_admitted():
    plugin, store, shards, dispatcher, controls, _ = await fixture()
    try:
        watermark = NOW + timedelta(seconds=5)
        await dispatcher.advance_watermark(watermark)
        await ingest(dispatcher, shards, observation(4, "a"))
        assert plugin.process_calls == 0 and len(store) == 0
        assert controls[-1].control_type is ControlType.LATE_EVENT_OBSERVED
        await ingest(dispatcher, shards, observation(5, "a"))
        assert plugin.process_calls == 0 and dispatcher.pending_reorder_count == 1
        await dispatcher.advance_watermark(watermark + timedelta(microseconds=1))
        assert plugin.process_calls == 1
    finally:
        await close(dispatcher, shards)


@pytest.mark.asyncio
async def test_expiry_failure_and_illegal_transition_do_not_undo_expiry():
    plugin, store, shards, dispatcher, controls, _ = await fixture()
    try:
        await ingest(dispatcher, shards, observation(1, "a")); await ingest(dispatcher, shards, observation(1, "b"))
        plugin.fail_key = "a"
        await dispatcher.advance_watermark(NOW + timedelta(seconds=20))
        assert len(store) == 0 and {str(item.key) for item in plugin.expired} == {"a", "b"}
        assert any(event.control_type is ControlType.ERROR and event.typed_payload["callback"] == "on_expire" for event in controls)
        plugin.fail_key = None; plugin.illegal_callback = "on_watermark"
        await dispatcher.advance_watermark(NOW + timedelta(seconds=21))
        assert any(event.control_type is ControlType.ERROR and event.typed_payload["callback"] == "on_watermark" for event in controls)
    finally:
        await close(dispatcher, shards)


@pytest.mark.asyncio
async def test_gap_and_disabled_lane_do_not_change_expiry_truth_or_publish_results():
    plugin, store, shards, dispatcher, controls, results = await fixture()
    try:
        await ingest(dispatcher, shards, observation(1))
        gap = await dispatcher.handle_ingress_saturation(observation(2))
        await dispatcher.advance_watermark(NOW + timedelta(seconds=20))
        assert gap in dispatcher.health.active_gaps and shards[0]._quality_degraded is True
        assert await dispatcher.resolve_gap(gap.gap_id)
        await ingest(dispatcher, shards, observation(21))
        await dispatcher._invoke_gap_action(GapAction.DISABLE_LANE, gap, None, None)
        before = len(results)
        await dispatcher.advance_watermark(NOW + timedelta(seconds=40))
        assert len(store) == 0 and dispatcher.health.health.value == "DISABLED" and len(results) == before
    finally:
        await close(dispatcher, shards)


@pytest.mark.asyncio
async def test_identical_event_time_replays_have_identical_lifecycle_semantics():
    async def replay():
        plugin, store, shards, dispatcher, controls, _ = await fixture()
        try:
            await ingest(dispatcher, shards, observation(1, "a"))
            await ingest(dispatcher, shards, observation(2, "a"))
            await dispatcher.advance_watermark(NOW + timedelta(seconds=5))
            await ingest(dispatcher, shards, observation(4, "a"))
            await dispatcher.advance_watermark(NOW + timedelta(seconds=20))
            return (
                len(store), tuple(plugin.order), dispatcher.watermark,
                tuple(event.control_type for event in controls), plugin.process_calls,
            )
        finally:
            await close(dispatcher, shards)

    assert await replay() == await replay()
