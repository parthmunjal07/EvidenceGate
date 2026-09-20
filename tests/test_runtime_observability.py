"""Focused runtime evidence tests for M2-RUNTIME-01."""

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from evidencegate.domain.enums import (
    AdmissionReason, AvailabilityBasis,
    ControlType,
    DirectionBasis, Finality, ObservationType,
    OperationalHealth,
    ResultType,
    ScientificStatus, SourceKind, WireDirection,
)
from evidencegate.domain.events import NetworkObservationEnvelope
from evidencegate.domain.governance import LaneGovernance
from evidencegate.domain.payloads import PacketObservation
from evidencegate.metrics.registry import registry
from evidencegate.plugins.scaffolds.basic_scaffold import BasicScaffoldPlugin
from evidencegate.registry.plugin import (
    PluginProcessOutcome,
    StateKey,
    StateTransitionRequest,
)
from evidencegate.results.types import ResultDraft
from evidencegate.runtime.dispatcher import LaneDispatcher
from evidencegate.runtime.shard import LaneShard
from evidencegate.runtime.state import StateOperation, StateStore
from evidencegate.runtime.supervisor import RuntimeSupervisor


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def observation(number: int = 1) -> NetworkObservationEnvelope:
    return NetworkObservationEnvelope(
        observation_id=f"runtime-{number}",
        schema_version="1.1",
        observation_type=ObservationType.PACKET,
        event_time=NOW + timedelta(seconds=number),
        causal_available_time=NOW + timedelta(seconds=number),
        ingest_time=NOW + timedelta(seconds=number),
        source_id="test-source",
        source_kind=SourceKind.PCAP,
        source_position=str(number),
        observation_contract="packet_v1",
        wire_direction=WireDirection.UNKNOWN,
        direction_basis=DirectionBasis.UNKNOWN,
        finality=Finality.TERMINAL,
        availability_basis=AvailabilityBasis.IMMEDIATE,
        provenance_ref="prov:test",
        quality_ref="quality:test",
        present_fields=frozenset({"src_address", "dst_address"}),
        typed_payload=PacketObservation(
            lengths={"ip": 20},
            observed_l2_facts={},
            observed_l3_facts={},
            observed_l4_facts={},
            src_address="10.0.0.1",
            dst_address="10.0.0.2",
            src_port=None,
            dst_port=None,
            flags=[],
            sequence_facts=None,
            fragmentation=None,
            raw_reference=None,
        ),
    )


def governance(*, ingest_permitted: bool = True) -> LaneGovernance:
    return LaneGovernance(
        analytic_lane="lane1",
        scientific_status=ScientificStatus.EVIDENCE_CONSTRUCTION,
        scientific_phase="test",
        scientific_blockers=(),
        claim_ceiling="REVIEW_FINDING_ONLY",
        governance_version="gov-7",
        effective_at=NOW,
        allowed_result_types=(ResultType.REVIEW_FINDING,),
        ingest_permitted=ingest_permitted,
    )


async def collect_into(target, value):
    target.append(value)


@pytest.mark.asyncio
async def test_admission_rejection_is_emitted_without_processing_or_state() -> None:
    class CountingPlugin(BasicScaffoldPlugin):
        calls = 0

        def manifest(self):
            return replace(super().manifest(), required_fields=("required_fact",))

        async def process(self, observation, context, state):
            self.calls += 1
            return await super().process(observation, context, state)

    plugin = CountingPlugin()
    store = StateStore()
    results = []
    controls = []
    shard = LaneShard(0, plugin, store, lambda value: collect_into(results, value))
    dispatcher = LaneDispatcher(
        "lane1",
        plugin,
        governance(),
        [shard],
        1,
        control_sink=lambda value: collect_into(controls, value),
    )
    dispatcher.start()
    try:
        dispatcher.put_nowait(observation())
        await asyncio.wait_for(dispatcher.queue.join(), timeout=1)
    finally:
        await dispatcher.stop()

    assert plugin.calls == 0
    assert results == []
    assert len(store) == 0
    assert shard.queue.empty()
    assert len(controls) == 1
    event = controls[0]
    assert event.control_type is ControlType.ADMISSION_REJECTED
    assert event.typed_payload["observation_id"] == "runtime-1"
    assert event.typed_payload["plugin_id"] == plugin.manifest().plugin_id
    assert event.typed_payload["governance_version"] == "gov-7"
    assert event.typed_payload["reasons"] == (
        AdmissionReason.PREREQUISITE_MISSING,
    )


@pytest.mark.asyncio
async def test_dispatcher_exception_emits_error_and_loop_survives() -> None:
    class FailingShard:
        def put_nowait(self, item):
            raise ValueError("dispatch failed")

    plugin = BasicScaffoldPlugin()
    controls = []
    dispatcher = LaneDispatcher(
        "lane1",
        plugin,
        governance(),
        [FailingShard()],
        1,
        control_sink=lambda value: collect_into(controls, value),
    )
    metric = registry.processing_errors.labels(
        lane="lane1", plugin_id=plugin.manifest().plugin_id
    )
    before = metric._value.get()
    dispatcher.start()
    try:
        dispatcher.put_nowait(observation())
        await asyncio.wait_for(dispatcher.queue.join(), timeout=1)
        assert dispatcher._task is not None and not dispatcher._task.done()
    finally:
        await dispatcher.stop()

    assert dispatcher.health.health is OperationalHealth.FAILED
    assert metric._value.get() == before + 1
    assert len(controls) == 1
    assert controls[0].control_type is ControlType.ERROR
    assert controls[0].typed_payload["component"] == "dispatcher"
    assert controls[0].typed_payload["exception_type"] == "ValueError"


@pytest.mark.asyncio
async def test_shard_plugin_exception_emits_error_and_later_item_runs() -> None:
    class FlakyPlugin(BasicScaffoldPlugin):
        calls = 0

        async def process(self, observation, context, state):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("plugin exploded")
            return await super().process(observation, context, state)

    plugin = FlakyPlugin()
    controls = []
    results = []
    shard = LaneShard(
        2,
        plugin,
        StateStore(),
        lambda value: collect_into(results, value),
        control_sink=lambda value: collect_into(controls, value),
        lane_id="lane1",
    )
    shard.start()
    try:
        await shard.put(observation(1))
        await asyncio.wait_for(shard.queue.join(), timeout=1)
        await shard.put(observation(2))
        await asyncio.wait_for(shard.queue.join(), timeout=1)
        assert shard._task is not None and not shard._task.done()
    finally:
        await shard.stop()

    assert len(controls) == 1
    assert controls[0].control_type is ControlType.ERROR
    assert controls[0].typed_payload["component"] == "shard"
    assert controls[0].typed_payload["shard_id"] == 2
    assert controls[0].typed_payload["exception_type"] == "RuntimeError"
    assert len(results) == 1
    assert results[0].result_type is ResultType.REVIEW_FINDING


@pytest.mark.asyncio
async def test_state_transition_failure_emits_error_without_result_or_mutation() -> None:
    key = StateKey("bounded-key")

    class TransitionPlugin(BasicScaffoldPlugin):
        stale = True

        def manifest(self):
            return replace(super().manifest(), plugin_id="transition-fixture")

        def state_key(self, observation):
            return key

        async def process(self, observation, context, state):
            expected = None if self.stale else state.version
            self.stale = False
            return PluginProcessOutcome(
                result_drafts=(
                    ResultDraft(
                        result_type=ResultType.REVIEW_FINDING,
                        entity_reference="test-entity",
                        evidence_items=(observation.observation_id,),
                        missing_prerequisites=(),
                    ),
                ),
                state_transition=StateTransitionRequest(
                    key=key,
                    expected_version=expected,
                    operation=StateOperation.NO_CHANGE,
                ),
            )

    plugin = TransitionPlugin()
    store = StateStore()
    store.transition(
        plugin.manifest().plugin_id,
        key,
        None,
        StateOperation.UPSERT,
        {"count": 1},
        NOW,
        timedelta(minutes=5),
    )
    controls = []
    results = []
    shard = LaneShard(
        0,
        plugin,
        store,
        lambda value: collect_into(results, value),
        control_sink=lambda value: collect_into(controls, value),
        lane_id="lane1",
    )
    shard.start()
    try:
        await shard.put(observation(1))
        await asyncio.wait_for(shard.queue.join(), timeout=1)
        entry = store.read(plugin.manifest().plugin_id, key, observation(1).event_time)
        assert entry is not None and entry.payload == {"count": 1}
        assert entry.version == 1
        assert results == []

        await shard.put(observation(2))
        await asyncio.wait_for(shard.queue.join(), timeout=1)
        assert shard._task is not None and not shard._task.done()
    finally:
        await shard.stop()

    assert len(controls) == 1
    assert controls[0].typed_payload["exception_type"] == "StateVersionConflict"
    assert len(results) == 1


@pytest.mark.asyncio
async def test_supervisor_lane_ingress_saturation_emits_gap_and_metric() -> None:
    gaps = []
    controls = []

    async def control_sink(event):
        controls.append(event)

    async def writer(result, target):
        raise AssertionError("queue drop must not emit a result")

    supervisor = RuntimeSupervisor(
        {"lane1": BasicScaffoldPlugin()},
        {"lane1": governance()},
        writer,
        shard_count=1,
        control_sink=control_sink,
        gap_sink=lambda value: collect_into(gaps, value),
    )
    dispatcher = supervisor.dispatchers["lane1"]
    assert dispatcher._control_sink is control_sink
    assert supervisor.shards["lane1"][0].control_sink is control_sink
    dispatcher.queue = asyncio.Queue(maxsize=1)
    dispatcher.put_nowait(observation(1))
    metric = registry.queue_full_events.labels(lane="lane1", shard_id="ingress")
    before = metric._value.get()

    await supervisor.ingest_observation(observation(2))

    assert len(gaps) == 1
    assert gaps[0].gap_types == ("QUEUE_SATURATION",)
    assert "Lane ingress" in gaps[0].reason
    assert "before admission" in gaps[0].reason
    assert dispatcher.health.health is OperationalHealth.BACKPRESSURED
    assert metric._value.get() == before + 1


@pytest.mark.asyncio
async def test_dispatcher_to_shard_saturation_emits_gap_and_metric() -> None:
    plugin = BasicScaffoldPlugin()
    shard = LaneShard(0, plugin, StateStore(), lambda value: collect_into([], value), max_size=1)
    shard.put_nowait(observation(1))
    gaps = []
    dispatcher = LaneDispatcher(
        "lane1",
        plugin,
        governance(),
        [shard],
        1,
        gap_sink=lambda value: collect_into(gaps, value),
    )
    metric = registry.queue_full_events.labels(lane="lane1", shard_id="0")
    before = metric._value.get()
    dispatcher.start()
    try:
        dispatcher.put_nowait(observation(2))
        await asyncio.wait_for(dispatcher.queue.join(), timeout=1)
    finally:
        await dispatcher.stop()

    assert len(gaps) == 1
    assert "Shard queue" in gaps[0].reason
    assert "before plugin processing" in gaps[0].reason
    assert dispatcher.health.health is OperationalHealth.BACKPRESSURED
    assert metric._value.get() == before + 1


@pytest.mark.asyncio
async def test_result_callback_failure_is_runtime_error_and_shard_survives() -> None:
    calls = 0
    delivered = []
    controls = []

    async def flaky_result_sink(result):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("delivery failed")
        delivered.append(result)

    shard = LaneShard(
        0,
        BasicScaffoldPlugin(),
        StateStore(),
        flaky_result_sink,
        control_sink=lambda value: collect_into(controls, value),
        lane_id="lane1",
    )
    shard.start()
    try:
        await shard.put(observation(1))
        await asyncio.wait_for(shard.queue.join(), timeout=1)
        await shard.put(observation(2))
        await asyncio.wait_for(shard.queue.join(), timeout=1)
    finally:
        await shard.stop()

    assert len(controls) == 1
    assert controls[0].typed_payload["exception_type"] == "OSError"
    assert len(delivered) == 1


@pytest.mark.asyncio
async def test_failing_diagnostic_sinks_are_bounded_and_do_not_kill_loop() -> None:
    control_calls = 0
    gap_calls = 0

    async def bad_control_sink(event):
        nonlocal control_calls
        control_calls += 1
        raise RuntimeError("control sink unavailable")

    async def bad_gap_sink(gap):
        nonlocal gap_calls
        gap_calls += 1
        raise RuntimeError("gap sink unavailable")

    dispatcher = LaneDispatcher(
        "lane1",
        BasicScaffoldPlugin(),
        governance(ingest_permitted=False),
        [],
        1,
        control_sink=bad_control_sink,
        gap_sink=bad_gap_sink,
    )
    dispatcher.start()
    try:
        dispatcher.put_nowait(observation(1))
        await asyncio.wait_for(dispatcher.queue.join(), timeout=1)
        assert dispatcher._task is not None and not dispatcher._task.done()
        gap = await dispatcher.handle_ingress_saturation(observation(2))
        assert gap.gap_types == ("QUEUE_SATURATION",)
        assert dispatcher._task is not None and not dispatcher._task.done()
    finally:
        await dispatcher.stop()

    # Admission rejection plus the required gap-action status are each attempted
    # once; neither sink failure recurses.
    assert control_calls == 2
    assert gap_calls == 1
