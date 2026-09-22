"""Bounded per-key event-time reordering at the dispatcher boundary."""

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from evidencegate.admission.evaluator import EvaluationReadinessDecision
from evidencegate.domain.enums import (
    AvailabilityBasis, ControlType, DirectionBasis, EvidenceReadiness, Finality,
    GapAction, ObservationType, ResultType, ScientificStatus, SourceKind,
    WireDirection,
)
from evidencegate.domain.events import NetworkObservationEnvelope
from evidencegate.domain.governance import LaneGovernance
from evidencegate.domain.payloads import PacketObservation
from evidencegate.plugins.providers.registry import build_mvp_provider_registry, build_mvp_runtime_registration
from evidencegate.plugins.scaffolds.basic_scaffold import BasicScaffoldPlugin
from evidencegate.registry.manifest import StateResourcePolicy
from evidencegate.registry.plugin import (
    PluginProcessOutcome, StateKey, StateTransitionRequest,
)
from evidencegate.results.types import ResultDraft
from evidencegate.routing.router import LaneTarget
from evidencegate.runtime.dispatcher import (
    DispatcherStoppedError, EventTimeReorderPolicy, LaneDispatcher, WatermarkError,
    source_position_order,
)
from evidencegate.runtime.shard import LaneShard
from evidencegate.runtime.state import StateOperation, StateStore
from evidencegate.runtime.supervisor import RuntimeSupervisor


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
LANE = LaneTarget("stateful")


def observation(
    second: int,
    *,
    key: str = "a",
    position: str | None = None,
    observation_id: str | None = None,
) -> NetworkObservationEnvelope:
    return NetworkObservationEnvelope(
        observation_id=observation_id or f"event-{key}-{second}",
        schema_version="1.1",
        observation_type=ObservationType.PACKET,
        event_time=NOW + timedelta(seconds=second),
        causal_available_time=NOW + timedelta(seconds=second),
        ingest_time=NOW + timedelta(seconds=second),
        source_id=key,
        source_kind=SourceKind.PCAP,
        source_position=position if position is not None else str(second),
        observation_contract="packet_v1",
        wire_direction=WireDirection.UNKNOWN,
        direction_basis=DirectionBasis.UNKNOWN,
        finality=Finality.TERMINAL,
        availability_basis=AvailabilityBasis.IMMEDIATE,
        provenance_ref="prov",
        quality_ref="quality",
        present_fields=frozenset({"src_address", "dst_address"}),
        typed_payload=PacketObservation(
            lengths={"ip": 20}, observed_l2_facts={}, observed_l3_facts={},
            observed_l4_facts={}, src_address="10.0.0.1",
            dst_address="10.0.0.2", src_port=None, dst_port=None, flags=[],
            sequence_facts=None, fragmentation=None, raw_reference=None,
        ),
    )


def governance(lane: str = "stateful") -> LaneGovernance:
    return LaneGovernance(
        lane, ScientificStatus.EVIDENCE_CONSTRUCTION, "test", (),
        "REVIEW_FINDING_ONLY", "gov", NOW, (ResultType.REVIEW_FINDING,), True,
    )


class RecordingStatefulPlugin(BasicScaffoldPlugin):
    def __init__(self, *, ttl: timedelta = timedelta(minutes=10)) -> None:
        self.ttl = ttl
        self.processed: list[tuple[str, int, str, str]] = []
        self.timeline: list[str] = []

    def manifest(self):
        return replace(
            super().manifest(), plugin_id="reorder-fixture",
            mechanism_id="fixture.reorder", gap_action=GapAction.CONTINUE_WITH_QUALITY_FLAG,
            state_resource_policy=StateResourcePolicy(20, timedelta(hours=1)),
        )

    def state_key(self, item):
        return StateKey(item.source_id)

    async def process(self, item, context, state):
        second = int((item.event_time - NOW).total_seconds())
        self.processed.append((item.source_id, second, item.source_position, item.observation_id))
        self.timeline.append(f"process:{item.observation_id}")
        count = 1 if state is None else state.payload["count"] + 1
        return PluginProcessOutcome(
            (ResultDraft(
                ResultType.REVIEW_FINDING, item.source_id,
                (item.observation_id,), (),
                evidence={"count": count, "observation_id": item.observation_id},
            ),),
            StateTransitionRequest(
                self.state_key(item), None if state is None else state.version,
                StateOperation.UPSERT, {"count": count}, self.ttl,
            ),
            EvaluationReadinessDecision(EvidenceReadiness.READY),
        )

    async def on_expire(self, key, context, state):
        self.timeline.append(f"expire:{key}")
        return PluginProcessOutcome()

    async def on_watermark(self, watermark, context):
        self.timeline.append("watermark")
        return PluginProcessOutcome()


async def collect(target, item):
    target.append(item)


async def dispatcher_fixture(
    *, maximum=20, total=200, ttl=timedelta(minutes=10), shards=2
):
    plugin = RecordingStatefulPlugin(ttl=ttl)
    store = StateStore(expire_on_access=False)
    results, controls, gaps = [], [], []
    lane_shards = [
        LaneShard(i, plugin, store, lambda item: collect(results, item),
                  control_sink=lambda item: collect(controls, item), lane_id=str(LANE))
        for i in range(shards)
    ]
    dispatcher = LaneDispatcher(
        LANE, plugin, governance(), lane_shards, shards,
        control_sink=lambda item: collect(controls, item),
        gap_sink=lambda item: collect(gaps, item),
        reorder_policy=EventTimeReorderPolicy(maximum, total),
    )
    for shard in lane_shards:
        shard.start()
    dispatcher.start()
    return plugin, store, lane_shards, dispatcher, results, controls, gaps


async def admit(dispatcher, *items):
    for item in items:
        dispatcher.put_nowait(item)
    await asyncio.wait_for(dispatcher.queue.join(), 1)


async def close(dispatcher, shards):
    await dispatcher.stop()
    for shard in shards:
        await shard.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("arrival", [(3, 1, 2), (2, 3, 1)])
async def test_replay_arrival_order_is_reordered_by_event_time(arrival):
    plugin, store, shards, dispatcher, *_ = await dispatcher_fixture()
    try:
        await admit(dispatcher, *(observation(second) for second in arrival))
        assert plugin.processed == [] and dispatcher.pending_reorder_count == 3
        await dispatcher.advance_watermark(NOW + timedelta(seconds=4))
        assert [item[1] for item in plugin.processed] == [1, 2, 3]
        entry = store.read("reorder-fixture", StateKey("a"), NOW + timedelta(seconds=4))
        assert entry is not None and (entry.payload, entry.version) == ({"count": 3}, 3)
    finally:
        await close(dispatcher, shards)


@pytest.mark.asyncio
async def test_same_timestamp_uses_position_then_observation_id():
    plugin, _, shards, dispatcher, *_ = await dispatcher_fixture()
    try:
        await admit(dispatcher,
            observation(1, position="3", observation_id="position-3"),
            observation(1, position="1", observation_id="position-1"),
            observation(1, position="2", observation_id="position-2"),
            observation(2, position="7", observation_id="z"),
            observation(2, position="7", observation_id="a"),
        )
        await dispatcher.advance_watermark(NOW + timedelta(seconds=3))
        assert [item[2] for item in plugin.processed[:3]] == ["1", "2", "3"]
        assert [item[3] for item in plugin.processed[3:]] == ["a", "z"]
        assert source_position_order("10") < source_position_order("non-numeric")
        assert source_position_order("2") < source_position_order("10")
    finally:
        await close(dispatcher, shards)


@pytest.mark.asyncio
async def test_multiple_keys_have_independent_order_and_buffers():
    plugin, _, shards, dispatcher, *_ = await dispatcher_fixture()
    try:
        await admit(dispatcher,
            observation(3, key="a"), observation(2, key="b"),
            observation(1, key="a"), observation(1, key="b"),
            observation(2, key="a"),
        )
        await dispatcher.advance_watermark(NOW + timedelta(seconds=4))
        assert [x[1] for x in plugin.processed if x[0] == "a"] == [1, 2, 3]
        assert [x[1] for x in plugin.processed if x[0] == "b"] == [1, 2]
    finally:
        await close(dispatcher, shards)


@pytest.mark.asyncio
async def test_late_equality_and_monotonic_watermark_contract():
    plugin, _, shards, dispatcher, _, controls, _ = await dispatcher_fixture()
    try:
        watermark = NOW + timedelta(seconds=5)
        assert await dispatcher.advance_watermark(watermark)
        assert not await dispatcher.advance_watermark(watermark)
        with pytest.raises(WatermarkError):
            await dispatcher.advance_watermark(NOW + timedelta(seconds=4))
        await admit(dispatcher, observation(4), observation(5))
        assert plugin.processed == [] and dispatcher.pending_reorder_count == 1
        assert any(event.control_type is ControlType.LATE_EVENT_OBSERVED for event in controls)
        await dispatcher.advance_watermark(NOW + timedelta(seconds=6))
        assert [item[1] for item in plugin.processed] == [5]
    finally:
        await close(dispatcher, shards)


@pytest.mark.asyncio
async def test_flush_completes_before_expiry_then_watermark_callback():
    plugin, store, shards, dispatcher, *_ = await dispatcher_fixture(ttl=timedelta(seconds=1))
    try:
        await admit(dispatcher, observation(9))
        await dispatcher.advance_watermark(NOW + timedelta(seconds=10))
        assert plugin.timeline == ["process:event-a-9", "expire:a", "watermark"]
        assert len(store) == 0
    finally:
        await close(dispatcher, shards)


@pytest.mark.asyncio
async def test_per_key_bound_surfaces_quality_loss_without_evicting_buffered_facts():
    plugin, _, shards, dispatcher, _, controls, gaps = await dispatcher_fixture(maximum=2)
    try:
        await admit(dispatcher,
            observation(3), observation(1), observation(2), observation(1, key="b"),
        )
        assert dispatcher.pending_reorder_count == 3
        assert len(gaps) == 1
        assert gaps[0].gap_types == ("REORDER_BUFFER_SATURATION",)
        assert "state key a" in gaps[0].reason
        assert any(event.control_type is ControlType.GAP_ACTION_STATUS for event in controls)
        await dispatcher.advance_watermark(NOW + timedelta(seconds=4))
        assert [x[1] for x in plugin.processed if x[0] == "a"] == [1, 3]
        assert [x[1] for x in plugin.processed if x[0] == "b"] == [1]
    finally:
        await close(dispatcher, shards)


@pytest.mark.asyncio
async def test_total_bound_saturates_across_keys_without_evicting_existing_facts():
    plugin, _, shards, dispatcher, _, controls, gaps = await dispatcher_fixture(
        maximum=4, total=4
    )
    try:
        await admit(
            dispatcher,
            observation(1, key="a"), observation(1, key="b"),
            observation(1, key="c"), observation(1, key="d"),
            observation(1, key="e"),
        )
        assert dispatcher.pending_reorder_count == 4
        assert dispatcher.peak_pending_reorder_total == 4
        assert dispatcher.peak_pending_reorder_per_key == 1
        assert len(dispatcher._reorder_buffers) == 4
        assert [gap.gap_types for gap in gaps] == [
            ("REORDER_BUFFER_TOTAL_SATURATION",)
        ]
        assert "configured_total_limit=4" in gaps[0].reason
        assert "current_pending_total=4" in gaps[0].reason
        assert any(event.control_type is ControlType.GAP_ACTION_STATUS for event in controls)
        await dispatcher.advance_watermark(NOW + timedelta(seconds=2))
        assert dispatcher.pending_reorder_count == 0
        assert {item[0] for item in plugin.processed} == {"a", "b", "c", "d"}
    finally:
        await close(dispatcher, shards)


@pytest.mark.asyncio
async def test_per_key_saturation_has_precedence_when_both_limits_are_full():
    _, _, shards, dispatcher, _, _, gaps = await dispatcher_fixture(
        maximum=2, total=2
    )
    try:
        await admit(
            dispatcher,
            observation(1, key="a"), observation(2, key="a"),
            observation(3, key="a"),
        )
        assert dispatcher.pending_reorder_count == 2
        assert [gap.gap_types for gap in gaps] == [
            ("REORDER_BUFFER_SATURATION",)
        ]
    finally:
        await close(dispatcher, shards)


@pytest.mark.asyncio
async def test_watermark_releases_total_budget_for_new_observations():
    plugin, _, shards, dispatcher, _, _, gaps = await dispatcher_fixture(
        maximum=2, total=2
    )
    try:
        await admit(dispatcher, observation(1, key="a"), observation(1, key="b"))
        assert dispatcher.pending_reorder_count == 2
        await dispatcher.advance_watermark(NOW + timedelta(seconds=2))
        assert dispatcher.pending_reorder_count == 0
        await admit(dispatcher, observation(2, key="c"), observation(2, key="d"))
        assert dispatcher.pending_reorder_count == 2
        assert gaps == []
        await dispatcher.advance_watermark(NOW + timedelta(seconds=3))
        assert dispatcher.pending_reorder_count == 0
        assert {item[0] for item in plugin.processed} == {"a", "b", "c", "d"}
    finally:
        await close(dispatcher, shards)


def test_reorder_policy_is_strictly_positive_and_typed():
    with pytest.raises(TypeError):
        EventTimeReorderPolicy(1)
    with pytest.raises(ValueError):
        EventTimeReorderPolicy(0, 1)
    with pytest.raises(TypeError):
        EventTimeReorderPolicy(True, 1)
    with pytest.raises(ValueError):
        EventTimeReorderPolicy(1, 0)
    with pytest.raises(TypeError):
        EventTimeReorderPolicy(1, True)
    with pytest.raises(ValueError, match="cannot be less"):
        EventTimeReorderPolicy(2, 1)


@pytest.mark.asyncio
async def test_supervisor_requires_stateful_policy_but_not_for_current_registry():
    plugin = RecordingStatefulPlugin()

    async def writer(result, target):
        pass

    with pytest.raises(ValueError, match="requires an explicit event-time reorder policy"):
        RuntimeSupervisor({LANE: plugin}, {LANE: governance()}, writer)
    supervisor = RuntimeSupervisor(
        {LANE: plugin}, {LANE: governance()}, writer,
        reorder_policies={LANE: EventTimeReorderPolicy(5, 50)},
    )
    assert supervisor.dispatchers[LANE].pending_reorder_count == 0

    registration = build_mvp_runtime_registration(NOW)
    current = RuntimeSupervisor(
        registration.plugins, registration.governances, writer,
        reorder_policies=registration.reorder_policies,
    )
    assert set(current.dispatchers) == set(registration.plugins)


@pytest.mark.asyncio
async def test_different_arrivals_produce_identical_state_and_finalized_results():
    async def replay(arrival):
        plugin = RecordingStatefulPlugin()
        results = []

        async def writer(result, target):
            results.append(result)

        supervisor = RuntimeSupervisor(
            {LANE: plugin}, {LANE: governance()}, writer, shard_count=2,
            reorder_policies={LANE: EventTimeReorderPolicy(10, 100)},
        )
        supervisor.start_all()
        try:
            for second in arrival:
                await supervisor.ingest_observation(observation(second))
            await asyncio.wait_for(supervisor.dispatchers[LANE].queue.join(), 1)
            await supervisor.advance_watermark(LANE, NOW + timedelta(seconds=4))
            entry = supervisor.state_stores[LANE].read(
                "reorder-fixture", StateKey("a"), NOW + timedelta(seconds=4)
            )
            return (
                tuple(plugin.processed), entry.payload, entry.version,
                tuple(result.result_id for result in results),
                tuple(result.evidence.canonical_json for result in results),
                tuple(result.state_version for result in results),
                tuple(result.status_snapshot.readiness for result in results),
            )
        finally:
            await supervisor.stop_all()

    first = await replay((3, 1, 2))
    second = await replay((2, 3, 1))
    assert first == second
    assert first[-2] == (None, 1, 2)


@pytest.mark.asyncio
async def test_stateless_lane_bypasses_reordering_and_needs_no_watermark():
    plugin = BasicScaffoldPlugin()
    shard_results = []
    shard = LaneShard(0, plugin, StateStore(), lambda item: collect(shard_results, item))
    dispatcher = LaneDispatcher("stateless", plugin, governance("stateless"), [shard], 1)
    shard.start()
    dispatcher.start()
    try:
        await admit(dispatcher, observation(1))
        await asyncio.wait_for(shard.queue.join(), 1)
        assert len(shard_results) == 1 and dispatcher.pending_reorder_count == 0
    finally:
        await close(dispatcher, [shard])


@pytest.mark.asyncio
async def test_stop_does_not_flush_pending_stateful_observations():
    plugin, _, shards, dispatcher, *_ = await dispatcher_fixture()
    await admit(dispatcher, observation(1))
    assert dispatcher.pending_reorder_count == 1
    await close(dispatcher, shards)
    assert plugin.processed == [] and dispatcher.pending_reorder_count == 1


@pytest.mark.asyncio
async def test_buffered_event_processes_without_publication_after_lane_disable():
    plugin, store, shards, dispatcher, results, _, _ = await dispatcher_fixture()
    try:
        await admit(dispatcher, observation(1))
        gap = await dispatcher.handle_ingress_saturation(observation(2))
        await dispatcher._invoke_gap_action(GapAction.DISABLE_LANE, gap, StateKey("a"), 0)
        await dispatcher.advance_watermark(NOW + timedelta(seconds=3))
        entry = store.read("reorder-fixture", StateKey("a"), NOW + timedelta(seconds=3))
        assert plugin.processed and entry is not None
        assert results == []
    finally:
        await close(dispatcher, shards)


@pytest.mark.asyncio
async def test_watermark_cannot_overtake_observation_already_in_ingress_queue():
    plugin, store, shards, dispatcher, _, controls, _ = await dispatcher_fixture()
    try:
        dispatcher.put_nowait(observation(9))
        assert await dispatcher.advance_watermark(NOW + timedelta(seconds=10))
        entry = store.read("reorder-fixture", StateKey("a"), NOW + timedelta(seconds=10))
        assert entry is not None and entry.payload == {"count": 1}
        assert [item[1] for item in plugin.processed] == [9]
        assert not any(event.control_type is ControlType.LATE_EVENT_OBSERVED for event in controls)
    finally:
        await close(dispatcher, shards)


@pytest.mark.asyncio
async def test_observation_queued_after_marker_sees_committed_watermark():
    plugin, store, shards, dispatcher, _, controls, _ = await dispatcher_fixture()
    entered, release = asyncio.Event(), asyncio.Event()

    async def blocked_watermark(watermark, context):
        entered.set()
        await release.wait()
        return PluginProcessOutcome()

    plugin.on_watermark = blocked_watermark
    try:
        dispatcher.put_nowait(observation(9))
        boundary = asyncio.create_task(
            dispatcher.advance_watermark(NOW + timedelta(seconds=10))
        )
        await asyncio.wait_for(entered.wait(), 1)
        dispatcher.put_nowait(observation(8))
        release.set()
        assert await boundary
        await asyncio.wait_for(dispatcher.queue.join(), 1)
        entry = store.read("reorder-fixture", StateKey("a"), NOW + timedelta(seconds=10))
        assert entry is not None and entry.payload == {"count": 1}
        assert [item[1] for item in plugin.processed] == [9]
        late = [event for event in controls if event.control_type is ControlType.LATE_EVENT_OBSERVED]
        assert len(late) == 1 and late[0].typed_payload["observation_id"] == "event-a-8"
    finally:
        release.set()
        await close(dispatcher, shards)


@pytest.mark.asyncio
async def test_equal_event_ahead_of_marker_waits_for_later_watermark():
    plugin, _, shards, dispatcher, *_ = await dispatcher_fixture()
    try:
        dispatcher.put_nowait(observation(10))
        assert await dispatcher.advance_watermark(NOW + timedelta(seconds=10))
        assert plugin.processed == [] and dispatcher.pending_reorder_count == 1
        assert await dispatcher.advance_watermark(NOW + timedelta(seconds=11))
        assert [item[1] for item in plugin.processed] == [10]
    finally:
        await close(dispatcher, shards)


@pytest.mark.asyncio
async def test_watermark_joins_pre_marker_stateless_shard_work():
    timeline = []
    process_entered, process_release = asyncio.Event(), asyncio.Event()

    class BlockingStatelessPlugin(BasicScaffoldPlugin):
        async def process(self, item, context, state):
            process_entered.set()
            await process_release.wait()
            timeline.append("process")
            return PluginProcessOutcome()

        async def on_watermark(self, watermark, context):
            timeline.append("watermark")
            return PluginProcessOutcome()

    plugin = BlockingStatelessPlugin()
    shard = LaneShard(0, plugin, StateStore(), lambda item: collect([], item))
    dispatcher = LaneDispatcher("stateless", plugin, governance("stateless"), [shard], 1)
    shard.start()
    dispatcher.start()
    try:
        dispatcher.put_nowait(observation(1))
        boundary = asyncio.create_task(
            dispatcher.advance_watermark(NOW + timedelta(seconds=2))
        )
        await asyncio.wait_for(process_entered.wait(), 1)
        assert not boundary.done()
        process_release.set()
        assert await boundary
        assert timeline == ["process", "watermark"]
    finally:
        process_release.set()
        await close(dispatcher, [shard])


@pytest.mark.asyncio
async def test_concurrent_watermarks_and_duplicates_are_queue_ordered():
    plugin, _, shards, dispatcher, _, controls, _ = await dispatcher_fixture()
    try:
        first = asyncio.create_task(
            dispatcher.advance_watermark(NOW + timedelta(seconds=10))
        )
        second = asyncio.create_task(
            dispatcher.advance_watermark(NOW + timedelta(seconds=20))
        )
        assert await asyncio.gather(first, second) == [True, True]
        assert dispatcher.watermark == NOW + timedelta(seconds=20)
        assert [item for item in plugin.timeline if item == "watermark"] == [
            "watermark", "watermark"
        ]

        duplicate_one = asyncio.create_task(
            dispatcher.advance_watermark(NOW + timedelta(seconds=30))
        )
        duplicate_two = asyncio.create_task(
            dispatcher.advance_watermark(NOW + timedelta(seconds=30))
        )
        assert await asyncio.gather(duplicate_one, duplicate_two) == [True, False]
        advanced = [event for event in controls if event.control_type is ControlType.WATERMARK_ADVANCED]
        assert len(advanced) == 3
    finally:
        await close(dispatcher, shards)


@pytest.mark.asyncio
async def test_backward_watermark_reaches_caller_and_dispatcher_stays_usable():
    _, _, shards, dispatcher, *_ = await dispatcher_fixture()
    try:
        forward = asyncio.create_task(
            dispatcher.advance_watermark(NOW + timedelta(seconds=20))
        )
        backward = asyncio.create_task(
            dispatcher.advance_watermark(NOW + timedelta(seconds=10))
        )
        assert await forward is True
        with pytest.raises(WatermarkError):
            await backward
        assert dispatcher._task is not None and not dispatcher._task.done()
        assert await dispatcher.advance_watermark(NOW + timedelta(seconds=30))
    finally:
        await close(dispatcher, shards)


@pytest.mark.asyncio
async def test_stop_fails_active_and_queued_watermark_requests():
    plugin, _, shards, dispatcher, *_ = await dispatcher_fixture()
    entered, release = asyncio.Event(), asyncio.Event()

    async def blocked_watermark(watermark, context):
        entered.set()
        await release.wait()
        return PluginProcessOutcome()

    plugin.on_watermark = blocked_watermark
    first = asyncio.create_task(
        dispatcher.advance_watermark(NOW + timedelta(seconds=10))
    )
    await asyncio.wait_for(entered.wait(), 1)
    second = asyncio.create_task(
        dispatcher.advance_watermark(NOW + timedelta(seconds=20))
    )

    async def marker_is_queued():
        while dispatcher.queue.qsize() == 0:
            await asyncio.sleep(0)

    await asyncio.wait_for(marker_is_queued(), 1)
    await dispatcher.stop()
    outcomes = await asyncio.gather(first, second, return_exceptions=True)
    assert all(isinstance(item, DispatcherStoppedError) for item in outcomes)
    assert dispatcher.queue.empty()
    release.set()
    for shard in shards:
        await shard.stop()


@pytest.mark.asyncio
async def test_watermark_marker_backpressures_instead_of_dropping_on_full_ingress():
    plugin = RecordingStatefulPlugin()
    store = StateStore(expire_on_access=False)
    shard = LaneShard(0, plugin, store, lambda item: collect([], item))
    dispatcher = LaneDispatcher(
        LANE, plugin, governance(), [shard], 1, max_size=1,
        reorder_policy=EventTimeReorderPolicy(10, 100),
    )
    entered, release = asyncio.Event(), asyncio.Event()
    original_buffer = dispatcher._buffer_stateful

    async def blocking_first_buffer(item, state_key, shard_idx):
        if item.observation_id == "event-a-1":
            entered.set()
            await release.wait()
        await original_buffer(item, state_key, shard_idx)

    dispatcher._buffer_stateful = blocking_first_buffer
    shard.start()
    dispatcher.start()
    try:
        dispatcher.put_nowait(observation(1))
        await asyncio.wait_for(entered.wait(), 1)
        dispatcher.put_nowait(observation(2))
        boundary = asyncio.create_task(
            dispatcher.advance_watermark(NOW + timedelta(seconds=3))
        )

        async def marker_is_backpressured():
            while not dispatcher._watermark_put_tasks:
                await asyncio.sleep(0)
            while all(task.done() for task in dispatcher._watermark_put_tasks):
                await asyncio.sleep(0)

        await asyncio.wait_for(marker_is_backpressured(), 1)
        assert not boundary.done() and dispatcher.watermark is None
        release.set()
        assert await boundary
        assert [item[1] for item in plugin.processed] == [1, 2]
    finally:
        release.set()
        await close(dispatcher, [shard])
