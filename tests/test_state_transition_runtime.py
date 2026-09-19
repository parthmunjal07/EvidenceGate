"""Focused tests for declarative plugin state transitions through a shard."""

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from evidencegate.domain.enums import EvidenceReadiness, ResultType
from evidencegate.domain.events import NetworkObservation
from evidencegate.domain.payloads import PacketObservation
from evidencegate.domain.events import NetworkObservationEnvelope
from evidencegate.plugins.scaffolds.basic_scaffold import BasicScaffoldPlugin
from evidencegate.registry.plugin import (
    PluginProcessOutcome,
    PluginStateSnapshot,
    StateKey,
    StateTransitionRequest,
)
from evidencegate.results.types import ResultDraft
from evidencegate.runtime.shard import LaneShard
from evidencegate.runtime.state import StateOperation, StateStore


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
TTL = timedelta(minutes=5)
KEY = StateKey("generic-key")


def observation(number: int) -> NetworkObservationEnvelope:
    payload = PacketObservation(
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
    )
    return NetworkObservationEnvelope(
        observation_id=f"state-contract-{number}",
        schema_version="1.1",
        observation_type=BasicScaffoldPlugin().manifest().accepted_observation_types[0],
        event_time=NOW + timedelta(seconds=number),
        causal_available_time=NOW + timedelta(seconds=number),
        ingest_time=NOW + timedelta(seconds=number),
        source_id="test-source",
        source_kind="PCAP",
        source_position=str(number),
        observation_contract="packet_v1",
        wire_direction="UNKNOWN",
        direction_basis="test",
        finality=True,
        availability_basis="IMMEDIATE",
        provenance_ref="prov:test",
        quality_ref="q:test",
        present_fields=frozenset({"src_address", "dst_address"}),
        typed_payload=payload,
    )


class RecordingStateStore(StateStore):
    def __init__(self) -> None:
        super().__init__()
        self.transition_results = []

    def transition(self, *args, **kwargs):
        result = super().transition(*args, **kwargs)
        self.transition_results.append(result)
        return result


class GenericStatefulPlugin(BasicScaffoldPlugin):
    def __init__(self) -> None:
        self.snapshots: list[PluginStateSnapshot | None] = []
        self.readiness = []
        self.operation = StateOperation.UPSERT
        self.request_key = KEY
        self.expected_version_override: int | None | object = _UNSET

    def manifest(self):
        return replace(super().manifest(), plugin_id="generic_state_fixture")

    def state_key(self, observation: NetworkObservation) -> StateKey:
        return KEY

    async def process(
        self,
        observation: NetworkObservation,
        context: Any,
        state: PluginStateSnapshot | None,
    ) -> PluginProcessOutcome:
        self.snapshots.append(state)
        self.readiness.append(context["readiness"])
        expected_version = state.version if state is not None else None
        if self.expected_version_override is not _UNSET:
            expected_version = self.expected_version_override
        payload = None
        ttl = None
        if self.operation is StateOperation.UPSERT:
            payload = {"count": 1 if state is None else state.payload["count"] + 1}
            ttl = TTL
        transition = StateTransitionRequest(
            key=self.request_key,
            expected_version=expected_version,
            operation=self.operation,
            payload=payload,
            ttl=ttl,
        )
        draft = ResultDraft(
            result_type=ResultType.REVIEW_FINDING,
            entity_reference="generic-test-entity",
            evidence_items=(observation.observation_id,),
            missing_prerequisites=(),
        )
        return PluginProcessOutcome((draft,), transition)


_UNSET = object()


async def run_one(shard: LaneShard, item: NetworkObservationEnvelope) -> None:
    shard.start()
    await shard.put(item)
    await asyncio.wait_for(shard.queue.join(), timeout=1)


def async_collector(target: list):
    async def collect(value):
        target.append(value)

    return collect


@pytest.mark.asyncio
async def test_snapshot_versions_upserts_and_result_order() -> None:
    plugin = GenericStatefulPlugin()
    store = RecordingStateStore()
    callback_entries = []

    async def capture(_draft):
        callback_entries.append(store.read(plugin.manifest().plugin_id, KEY, NOW))

    shard = LaneShard(0, plugin, store, capture)
    try:
        await run_one(shard, observation(1))
        await run_one(shard, observation(2))
    finally:
        await shard.stop()

    assert plugin.snapshots[0] is None
    second = plugin.snapshots[1]
    assert second is not None
    assert second.key == KEY
    assert second.payload == {"count": 1}
    assert second.version == 1
    assert second.expires_at == observation(1).event_time + TTL
    assert [entry.version for entry in callback_entries] == [1, 2]
    assert store.read(plugin.manifest().plugin_id, KEY, NOW).payload == {"count": 2}


@pytest.mark.asyncio
async def test_snapshot_payload_cannot_mutate_stored_state_invisibly() -> None:
    plugin = GenericStatefulPlugin()
    store = StateStore()
    namespace = plugin.manifest().plugin_id
    store.transition(namespace, KEY, None, StateOperation.UPSERT, {"count": 1}, NOW, TTL)
    plugin.operation = StateOperation.NO_CHANGE

    class MutatingPlugin(GenericStatefulPlugin):
        async def process(self, observation, context, state):
            state.payload["count"] = 999
            return await super().process(observation, context, state)

    mutating_plugin = MutatingPlugin()
    mutating_plugin.operation = StateOperation.NO_CHANGE
    emitted = []
    shard = LaneShard(0, mutating_plugin, store, async_collector(emitted))
    try:
        await run_one(shard, observation(1))
    finally:
        await shard.stop()

    assert store.read(namespace, KEY, NOW).payload == {"count": 1}


@pytest.mark.asyncio
async def test_stale_transition_does_not_change_state_or_emit_result() -> None:
    plugin = GenericStatefulPlugin()
    plugin.expected_version_override = None
    store = StateStore()
    namespace = plugin.manifest().plugin_id
    store.transition(namespace, KEY, None, StateOperation.UPSERT, {"count": 1}, NOW, TTL)
    emitted = []
    shard = LaneShard(0, plugin, store, async_collector(emitted))
    try:
        await run_one(shard, observation(1))
    finally:
        await shard.stop()

    entry = store.read(namespace, KEY, NOW)
    assert entry.payload == {"count": 1}
    assert entry.version == 1
    assert emitted == []


@pytest.mark.asyncio
async def test_runtime_owns_namespace_and_preserves_other_plugin_state() -> None:
    plugin = GenericStatefulPlugin()
    store = StateStore()
    store.transition("another-plugin", KEY, None, StateOperation.UPSERT, "other", NOW, TTL)
    emitted = []
    shard = LaneShard(0, plugin, store, async_collector(emitted))
    try:
        await run_one(shard, observation(1))
    finally:
        await shard.stop()

    assert store.read("another-plugin", KEY, NOW).payload == "other"
    assert store.read(plugin.manifest().plugin_id, KEY, NOW).payload == {"count": 1}
    with pytest.raises(TypeError):
        StateTransitionRequest(
            namespace="another-plugin",
            key=KEY,
            expected_version=None,
            operation=StateOperation.NO_CHANGE,
        )


@pytest.mark.asyncio
async def test_transition_cannot_target_unrelated_key() -> None:
    plugin = GenericStatefulPlugin()
    plugin.request_key = StateKey("unrelated-key")
    store = StateStore()
    emitted = []
    shard = LaneShard(0, plugin, store, async_collector(emitted))
    try:
        await run_one(shard, observation(1))
    finally:
        await shard.stop()

    namespace = plugin.manifest().plugin_id
    assert store.read(namespace, KEY, NOW) is None
    assert store.read(namespace, "unrelated-key", NOW) is None
    assert emitted == []


@pytest.mark.asyncio
async def test_stateless_scaffold_emits_without_fabricating_state() -> None:
    plugin = BasicScaffoldPlugin()
    store = StateStore()
    emitted = []
    shard = LaneShard(0, plugin, store, async_collector(emitted))
    try:
        await run_one(shard, observation(1))
    finally:
        await shard.stop()

    assert len(emitted) == 1
    assert len(store) == 0


@pytest.mark.asyncio
async def test_stateless_invocation_cannot_request_state_mutation() -> None:
    class InvalidStatelessPlugin(GenericStatefulPlugin):
        def state_key(self, observation):
            return None

    plugin = InvalidStatelessPlugin()
    store = StateStore()
    emitted = []
    shard = LaneShard(0, plugin, store, async_collector(emitted))
    try:
        await run_one(shard, observation(1))
    finally:
        await shard.stop()

    assert len(store) == 0
    assert emitted == []


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", [StateOperation.RESET, StateOperation.REENTER_WARMUP])
async def test_lifecycle_transitions_reenter_generic_warmup(operation) -> None:
    plugin = GenericStatefulPlugin()
    store = RecordingStateStore()
    emitted = []
    shard = LaneShard(0, plugin, store, async_collector(emitted))
    try:
        await run_one(shard, observation(1))
        await run_one(shard, observation(2))
        assert shard.get_readiness(KEY).readiness is EvidenceReadiness.READY

        plugin.operation = operation
        await run_one(shard, observation(3))

        assert store.transition_results[-1].operation is operation
        assert shard.get_readiness(KEY).readiness is EvidenceReadiness.WARMING_UP
        entry = store.read(plugin.manifest().plugin_id, KEY, observation(3).event_time)
        if operation is StateOperation.RESET:
            assert entry is None
        else:
            assert entry.payload == {"count": 2}
            assert entry.version == 2

        await run_one(shard, observation(4))
        assert plugin.readiness[-1].readiness is EvidenceReadiness.WARMING_UP
    finally:
        await shard.stop()


@pytest.mark.asyncio
async def test_no_change_preserves_state_and_readiness() -> None:
    plugin = GenericStatefulPlugin()
    store = RecordingStateStore()
    emitted = []
    shard = LaneShard(0, plugin, store, async_collector(emitted))
    try:
        await run_one(shard, observation(1))
        await run_one(shard, observation(2))
        before = store.read(plugin.manifest().plugin_id, KEY, observation(2).event_time)

        plugin.operation = StateOperation.NO_CHANGE
        await run_one(shard, observation(3))

        after = store.read(plugin.manifest().plugin_id, KEY, observation(3).event_time)
        assert store.transition_results[-1].operation is StateOperation.NO_CHANGE
        assert after.payload == before.payload
        assert after.version == before.version
        assert after.expires_at == before.expires_at
        assert shard.get_readiness(KEY).readiness is EvidenceReadiness.READY
    finally:
        await shard.stop()


@pytest.mark.asyncio
async def test_delete_removes_state_without_resetting_readiness() -> None:
    plugin = GenericStatefulPlugin()
    store = RecordingStateStore()
    emitted = []
    shard = LaneShard(0, plugin, store, async_collector(emitted))
    try:
        await run_one(shard, observation(1))
        await run_one(shard, observation(2))
        plugin.operation = StateOperation.DELETE
        await run_one(shard, observation(3))

        assert store.transition_results[-1].operation is StateOperation.DELETE
        assert store.read(plugin.manifest().plugin_id, KEY, observation(3).event_time) is None
        assert shard.get_readiness(KEY).readiness is EvidenceReadiness.READY
    finally:
        await shard.stop()
