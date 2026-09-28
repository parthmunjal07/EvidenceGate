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
        return replace(
            super().manifest(),
            plugin_id="mechanism-readiness-fixture",
            state_resource_policy=StateResourcePolicy(2, timedelta(seconds=60)),
        )

    def state_key(self, item):
        return StateKey(item.typed_payload.src_address)

    async def process(self, item, context, state):
        count = 1 if state is None else state.payload["count"] + 1
        readiness = (
            EvidenceReadiness.READY
            if self.ready_first or count >= 3
            else EvidenceReadiness.INSUFFICIENT_HISTORY
        )
        return PluginProcessOutcome(
            (ResultDraft(ResultType.REVIEW_FINDING, "fixture", (item.observation_id,), ()),),
            StateTransitionRequest(
                self.state_key(item),
                None if state is None else state.version,
                StateOperation.UPSERT,
                {"count": count},
                self.ttl,
            ),
            EvaluationReadinessDecision(readiness),
        )


class MissingReadinessFixture(CountFixture):
    async def process(self, item, context, state):
        outcome = await super().process(item, context, state)
        return PluginProcessOutcome(outcome.result_drafts, outcome.state_transition)


async def run(shard, item):
    shard.start()
    await shard.put(item)
    await asyncio.wait_for(shard.queue.join(), 1)


async def collect(target, value):
    target.append(value)


@pytest.mark.asyncio
async def test_stateful_readiness_is_mechanism_owned_and_prior_version_is_preserved():
    plugin, emitted = CountFixture(), []
    shard = LaneShard(0, plugin, StateStore(max_entries=2), lambda x: collect(emitted, x))
    try:
        await run(shard, observation(1))
        assert shard.get_readiness("10.0.0.1").readiness is EvidenceReadiness.INSUFFICIENT_HISTORY
        await run(shard, observation(2))
        assert shard.get_readiness("10.0.0.1").readiness is EvidenceReadiness.INSUFFICIENT_HISTORY
        await run(shard, observation(3))
        assert shard.get_readiness("10.0.0.1").readiness is EvidenceReadiness.READY
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
    plugin, emitted, controls = CountFixture(), [], []
    shard = LaneShard(
        0,
        plugin,
        StateStore(max_entries=2),
        lambda x: collect(emitted, x),
        control_sink=lambda x: collect(controls, x),
    )
    try:
        await run(shard, observation(1))
        assert shard.get_readiness("10.0.0.1").readiness is EvidenceReadiness.INSUFFICIENT_HISTORY
        plugin.ready_first, plugin.ttl = True, timedelta(seconds=61)
        await run(shard, observation(2))
        assert len(shard.state_store) == 1 and emitted != [] and len(controls) == 1
        assert shard.get_readiness("10.0.0.1").readiness is EvidenceReadiness.INSUFFICIENT_HISTORY
    finally:
        await shard.stop()


@pytest.mark.asyncio
async def test_stale_transition_preserves_committed_readiness():
    plugin, emitted = CountFixture(), []
    shard = LaneShard(0, plugin, StateStore(max_entries=2), lambda x: collect(emitted, x))
    try:
        await run(shard, observation(1))
        assert shard.get_readiness("10.0.0.1").readiness is EvidenceReadiness.INSUFFICIENT_HISTORY
        original = plugin.process

        async def stale(item, context, state):
            outcome = await original(item, context, state)
            return PluginProcessOutcome(
                outcome.result_drafts,
                StateTransitionRequest(
                    outcome.state_transition.key,
                    None,
                    StateOperation.UPSERT,
                    outcome.state_transition.payload,
                    outcome.state_transition.ttl,
                ),
                EvaluationReadinessDecision(EvidenceReadiness.READY),
            )

        plugin.process = stale
        await run(shard, observation(2))
        assert shard.get_readiness("10.0.0.1").readiness is EvidenceReadiness.INSUFFICIENT_HISTORY
    finally:
        await shard.stop()


@pytest.mark.asyncio
async def test_missing_readiness_commits_facts_but_not_readiness_or_results():
    plugin, emitted, controls = MissingReadinessFixture(), [], []
    shard = LaneShard(
        0,
        plugin,
        StateStore(max_entries=2),
        lambda x: collect(emitted, x),
        control_sink=lambda x: collect(controls, x),
    )
    try:
        await run(shard, observation(1))
        assert len(shard.state_store) == 1 and emitted == [] and len(controls) == 1
        assert shard.get_readiness("10.0.0.1").readiness is EvidenceReadiness.WARMING_UP
    finally:
        await shard.stop()


@pytest.mark.asyncio
async def test_capacity_failure_does_not_commit_ready_for_new_key():
    plugin, controls = CountFixture(ready_first=True), []
    shard = LaneShard(
        0,
        plugin,
        StateStore(max_entries=2),
        lambda x: collect([], x),
        control_sink=lambda x: collect(controls, x),
    )

    def keyed(number, address):
        item = observation(number)
        return replace(item, typed_payload=replace(item.typed_payload, src_address=address))

    try:
        await run(shard, keyed(1, "10.0.0.1"))
        await run(shard, keyed(2, "10.0.0.2"))
        await run(shard, keyed(3, "10.0.0.3"))
        assert shard.get_readiness("10.0.0.1").readiness is EvidenceReadiness.READY
        assert shard.get_readiness("10.0.0.2").readiness is EvidenceReadiness.READY
        assert shard.get_readiness("10.0.0.3").readiness is EvidenceReadiness.WARMING_UP
        assert len(shard.state_store) == 2 and len(controls) == 1
    finally:
        await shard.stop()


@pytest.mark.asyncio
async def test_finalized_result_uses_committed_readiness():
    plugin, emitted = CountFixture(ready_first=True), []
    shard = LaneShard(
        0,
        plugin,
        StateStore(max_entries=2),
        lambda x: collect(emitted, x),
        result_finalizer=lambda draft, context: context,
    )
    try:
        await run(shard, observation(1))
        assert emitted[0].readiness is EvidenceReadiness.READY
        assert shard.get_readiness("10.0.0.1").readiness is EvidenceReadiness.READY
    finally:
        await shard.stop()


@pytest.mark.asyncio
async def test_stateful_no_transition_commits_explicit_readiness():
    class NoTransitionFixture(CountFixture):
        async def process(self, item, context, state):
            return PluginProcessOutcome(
                (), None, EvaluationReadinessDecision(EvidenceReadiness.READY)
            )

    plugin = NoTransitionFixture()
    shard = LaneShard(0, plugin, StateStore(max_entries=2), lambda x: collect([], x))
    try:
        await run(shard, observation(1))
        assert shard.get_readiness("10.0.0.1").readiness is EvidenceReadiness.READY
        assert len(shard.state_store) == 0
    finally:
        await shard.stop()


def test_state_resource_policy_is_strictly_typed_and_positive():
    with pytest.raises(ValueError):
        StateResourcePolicy(0, timedelta(seconds=1))
    with pytest.raises(TypeError):
        StateResourcePolicy(True, timedelta(seconds=1))
    with pytest.raises(ValueError):
        StateResourcePolicy(1, timedelta(0))
