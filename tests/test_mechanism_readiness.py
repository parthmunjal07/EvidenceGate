"""Mechanism-owned readiness and bounded state resource policy coverage."""

import asyncio
from dataclasses import replace
from datetime import timedelta

import pytest

from evidencegate.admission.evaluator import EvaluationReadinessDecision
from evidencegate.domain.enums import EvidenceReadiness, ResultType
from evidencegate.plugins.scaffolds.basic_scaffold import BasicScaffoldPlugin
from evidencegate.registry.manifest import StateResourcePolicy
from evidencegate.registry.plugin import PluginProcessOutcome, StateKey, StateTransitionRequest
from evidencegate.results.types import ResultDraft
from evidencegate.runtime.shard import LaneShard
from evidencegate.runtime.state import StateOperation, StateStore
from tests.test_state_transition_runtime import observation


class CountFixture(BasicScaffoldPlugin):
    def __init__(self, *, ready_first=False, ttl=timedelta(seconds=30)):
        self.ready_first, self.ttl = ready_first, ttl

    def manifest(self):
        return replace(super().manifest(), plugin_id="mechanism-readiness-fixture",
            state_resource_policy=StateResourcePolicy(2, timedelta(seconds=60)))

    def state_key(self, item):
        return StateKey(item.typed_payload.src_address)

    async def process(self, item, context, state):
        count = 1 if state is None else state.payload["count"] + 1
        readiness = EvidenceReadiness.READY if self.ready_first or count >= 3 else EvidenceReadiness.INSUFFICIENT_HISTORY
        return PluginProcessOutcome(
            (ResultDraft(ResultType.REVIEW_FINDING, "fixture", (item.observation_id,), ()),),
            StateTransitionRequest(self.state_key(item), None if state is None else state.version,
                StateOperation.UPSERT, {"count": count}, self.ttl),
            EvaluationReadinessDecision(readiness),
        )


async def run(shard, item):
    shard.start(); await shard.put(item); await asyncio.wait_for(shard.queue.join(), 1)


async def collect(target, value):
    target.append(value)


@pytest.mark.asyncio
async def test_stateful_readiness_is_mechanism_owned_and_prior_version_is_preserved():
    plugin, emitted = CountFixture(), []
    shard = LaneShard(0, plugin, StateStore(max_entries=2), lambda x: collect(emitted, x))
    try:
        await run(shard, observation(1)); assert shard.get_readiness("10.0.0.1").readiness is EvidenceReadiness.INSUFFICIENT_HISTORY
        await run(shard, observation(2)); assert shard.get_readiness("10.0.0.1").readiness is EvidenceReadiness.INSUFFICIENT_HISTORY
        await run(shard, observation(3)); assert shard.get_readiness("10.0.0.1").readiness is EvidenceReadiness.READY
    finally:
        await shard.stop()


@pytest.mark.asyncio
async def test_a_different_mechanism_can_be_ready_on_its_first_observation():
    plugin = CountFixture(ready_first=True)
    shard = LaneShard(0, plugin, StateStore(max_entries=2), lambda x: collect([], x))
    try:
        await run(shard, observation(1))
        assert shard.get_readiness("10.0.0.1").readiness is EvidenceReadiness.READY
    finally:
        await shard.stop()


@pytest.mark.asyncio
async def test_ttl_policy_rejects_oversized_transition_without_state_or_results():
    plugin, emitted, controls = CountFixture(ttl=timedelta(seconds=61)), [], []
    shard = LaneShard(0, plugin, StateStore(max_entries=2), lambda x: collect(emitted, x),
                       control_sink=lambda x: collect(controls, x))
    try:
        await run(shard, observation(1))
        assert len(shard.state_store) == 0 and emitted == [] and len(controls) == 1
    finally:
        await shard.stop()


def test_state_resource_policy_is_strictly_typed_and_positive():
    with pytest.raises(ValueError): StateResourcePolicy(0, timedelta(seconds=1))
    with pytest.raises(TypeError): StateResourcePolicy(True, timedelta(seconds=1))
    with pytest.raises(ValueError): StateResourcePolicy(1, timedelta(0))
