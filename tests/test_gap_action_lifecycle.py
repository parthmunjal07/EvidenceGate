"""Generic runtime lifecycle tests for declared GapAction behavior."""

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
from evidencegate.runtime.dispatcher import LaneDispatcher
from evidencegate.runtime.shard import LaneShard
from evidencegate.runtime.state import StateOperation, StateStore
from evidencegate.runtime.state import StateVersionConflict


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def obs(number: int, key: str = "a") -> NetworkObservationEnvelope:
    return NetworkObservationEnvelope(
        observation_id=f"gap-{key}-{number}", schema_version="1.1",
        observation_type=ObservationType.PACKET, event_time=NOW + timedelta(seconds=number),
        causal_available_time=NOW + timedelta(seconds=number), ingest_time=NOW + timedelta(seconds=number),
        source_id="test", source_kind=SourceKind.PCAP, source_position=str(number),
        observation_contract="packet_v1", wire_direction=WireDirection.UNKNOWN,
        direction_basis=DirectionBasis.UNKNOWN, finality=Finality.TERMINAL,
        availability_basis=AvailabilityBasis.IMMEDIATE, provenance_ref="prov", quality_ref="quality",
        present_fields=frozenset({"src_address", "dst_address"}),
        typed_payload=PacketObservation(lengths={"ip": 20}, observed_l2_facts={}, observed_l3_facts={},
            observed_l4_facts={}, src_address="10.0.0.1", dst_address="10.0.0.2", src_port=None,
            dst_port=None, flags=[], sequence_facts=None, fragmentation=None, raw_reference=None),
    )


def gov() -> LaneGovernance:
    return LaneGovernance("lane", ScientificStatus.EVIDENCE_CONSTRUCTION, "test", (),
        "REVIEW_FINDING_ONLY", "gov", NOW, (ResultType.REVIEW_FINDING,), True)


class StatefulPlugin(BasicScaffoldPlugin):
    def __init__(self, action=GapAction.CONTINUE_WITH_QUALITY_FLAG):
        self.action, self.contexts, self.calls = action, [], 0

    def manifest(self):
        return replace(super().manifest(), plugin_id="gap-fixture", gap_action=self.action,
                       state_resource_policy=StateResourcePolicy(10, timedelta(minutes=10)))

    def state_key(self, observation):
        return StateKey(observation.observation_id.split("-")[1])

    async def process(self, observation, context, state):
        self.calls += 1
        self.contexts.append(context)
        count = 1 if state is None else state.payload["count"] + 1
        return PluginProcessOutcome((ResultDraft(ResultType.REVIEW_FINDING, "generic", (observation.observation_id,), ()),),
            StateTransitionRequest(self.state_key(observation), None if state is None else state.version,
                StateOperation.UPSERT, {"count": count}, timedelta(minutes=5)),
            EvaluationReadinessDecision(EvidenceReadiness.READY))


async def emit(target, item):
    target.append(item)


async def run_shard(shard, item):
    shard.start()
    await shard.put(item)
    await asyncio.wait_for(shard.queue.join(), 1)


def dispatcher(plugin, shard, controls):
    return LaneDispatcher("lane", plugin, gov(), [shard], 1,
        control_sink=lambda event: emit(controls, event))


@pytest.mark.asyncio
async def test_continue_flag_is_visible_and_multiple_gaps_require_all_resolution():
    plugin, results, controls = StatefulPlugin(), [], []
    shard = LaneShard(0, plugin, StateStore(), lambda result: emit(results, result))
    d = dispatcher(plugin, shard, controls)
    await run_shard(shard, obs(1))
    await run_shard(shard, obs(2))
    assert plugin.contexts[-1]["readiness"].readiness is EvidenceReadiness.READY
    first = await d.handle_ingress_saturation(obs(3))
    second = await d.handle_ingress_saturation(obs(4))
    await run_shard(shard, obs(5))
    assert plugin.contexts[-1]["quality_degraded"] is True
    assert plugin.contexts[-1]["readiness"].readiness is EvidenceReadiness.READY
    assert len(results) == 3
    assert await d.resolve_gap(first.gap_id)
    await run_shard(shard, obs(6))
    assert plugin.contexts[-1]["quality_degraded"] is True
    assert await d.resolve_gap(second.gap_id)
    await run_shard(shard, obs(7))
    assert plugin.contexts[-1]["quality_degraded"] is False
    assert len(d.health.active_gaps) == 0
    await shard.stop()


@pytest.mark.asyncio
async def test_reset_only_changes_affected_key_and_emits_applied_status():
    plugin, results, controls = StatefulPlugin(GapAction.RESET_AFFECTED_STATE), [], []
    store, shard = StateStore(), LaneShard(0, plugin, StateStore(), lambda result: emit(results, result))
    # Use the shard's authoritative store and mature independent keys.
    store = shard.state_store
    await run_shard(shard, obs(1, "a")); await run_shard(shard, obs(2, "a")); await run_shard(shard, obs(1, "b"))
    d = dispatcher(plugin, shard, controls)
    gap = await d._handle_queue_saturation(obs(3, "a"), 0, StateKey("a"))
    assert store.read("gap-fixture", "a", obs(3, "a").event_time) is None
    assert store.read("gap-fixture", "b", obs(3, "a").event_time).payload == {"count": 1}
    assert shard.get_readiness("a").readiness is EvidenceReadiness.WARMING_UP
    assert controls[-1].control_type is ControlType.GAP_ACTION_STATUS
    assert controls[-1].typed_payload["status"] == "APPLIED"
    await shard.stop()


@pytest.mark.asyncio
async def test_reenter_warmup_preserves_entry_and_unknown_key_blocks_safely():
    plugin, results, controls = StatefulPlugin(GapAction.REENTER_WARMUP), [], []
    shard = LaneShard(0, plugin, StateStore(), lambda result: emit(results, result))
    await run_shard(shard, obs(1)); await run_shard(shard, obs(2))
    before = shard.state_store.read("gap-fixture", "a", obs(2).event_time)
    d = dispatcher(plugin, shard, controls)
    await d._handle_queue_saturation(obs(3), 0, StateKey("a"))
    after = shard.state_store.read("gap-fixture", "a", obs(3).event_time)
    assert (after.payload, after.version, after.expires_at) == (before.payload, before.version, before.expires_at)
    assert shard.get_readiness("a").readiness is EvidenceReadiness.WARMING_UP
    unknown = await d._handle_queue_saturation(obs(4), 0, None)
    assert unknown.gap_id in {gap.gap_id for gap in d.health.active_gaps}
    assert controls[-1].typed_payload["status"] == "BLOCKED_NO_STATE_KEY"
    assert shard.state_store.read("gap-fixture", "a", obs(4).event_time).payload == before.payload
    await shard.stop()


@pytest.mark.asyncio
async def test_abstain_commits_facts_but_suppresses_results_until_explicit_resolution():
    plugin, results, controls = StatefulPlugin(GapAction.ABSTAIN_UNTIL_RECOVERED), [], []
    shard = LaneShard(0, plugin, StateStore(), lambda result: emit(results, result))
    d = dispatcher(plugin, shard, controls)
    gap = await d._handle_queue_saturation(obs(1), 0, StateKey("a"))
    await run_shard(shard, obs(2))
    entry = shard.state_store.read("gap-fixture", "a", obs(2).event_time)
    assert plugin.calls == 1 and entry.payload == {"count": 1} and results == []
    assert plugin.contexts[-1]["readiness"].readiness is EvidenceReadiness.WARMING_UP
    await d.resolve_gap(gap.gap_id)
    await run_shard(shard, obs(3))
    assert len(results) == 1
    await shard.stop()


@pytest.mark.asyncio
async def test_disable_skips_visibly_without_mutating_governance_then_reenables():
    plugin, results, controls = StatefulPlugin(GapAction.DISABLE_LANE), [], []
    shard = LaneShard(0, plugin, StateStore(), lambda result: emit(results, result))
    d = dispatcher(plugin, shard, controls)
    original = (d.governance.scientific_status, d.governance.ingest_permitted, d.governance.allowed_result_types)
    await d.handle_ingress_saturation(obs(1))
    shard.start()
    d.start()
    try:
        d.put_nowait(obs(2)); await asyncio.wait_for(d.queue.join(), 1)
        assert plugin.calls == 0 and len(shard.state_store) == 0 and results == []
        assert controls[-1].typed_payload["status"] == "SKIPPED_DISABLED"
        assert (d.governance.scientific_status, d.governance.ingest_permitted, d.governance.allowed_result_types) == original
        d.enable_lane()
        d.put_nowait(obs(3)); await asyncio.wait_for(d.queue.join(), 1)
        await asyncio.wait_for(shard.queue.join(), 1)
        assert plugin.calls == 1
    finally:
        await d.stop(); await shard.stop()


@pytest.mark.asyncio
async def test_lifecycle_state_conflict_is_typed_failure_without_broad_mutation():
    class ConflictingStore(StateStore):
        def transition(self, *args, **kwargs):
            if kwargs.get("operation") is StateOperation.RESET:
                raise StateVersionConflict("gap-fixture", StateKey("a"), 1, 2)
            return super().transition(*args, **kwargs)

    plugin, controls = StatefulPlugin(GapAction.RESET_AFFECTED_STATE), []
    store = ConflictingStore()
    store.transition("gap-fixture", StateKey("a"), None, StateOperation.UPSERT, {"count": 1}, NOW, timedelta(minutes=5))
    store.transition("gap-fixture", StateKey("b"), None, StateOperation.UPSERT, {"count": 1}, NOW, timedelta(minutes=5))
    shard = LaneShard(0, plugin, store, lambda result: emit([], result))
    d = dispatcher(plugin, shard, controls)
    await d._handle_queue_saturation(obs(2), 0, StateKey("a"))
    assert controls[-1].typed_payload["status"] == "FAILED"
    assert store.read("gap-fixture", "a", obs(2).event_time).payload == {"count": 1}
    assert store.read("gap-fixture", "b", obs(2).event_time).payload == {"count": 1}
