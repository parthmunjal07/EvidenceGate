"""
runtime/shard.py — FIFO lane shard with real EvaluationReadiness lifecycle.

Contract §7 + IC-16:
  - State update always happens (admissible observations are never blocked by readiness).
  - EvaluationReadinessDecision is computed AFTER state update.
  - Hardcoded "READY" is replaced by a genuine minimal readiness lifecycle.
  - No threat-specific thresholds, windows, or science.

Lifecycle (per state_key):
  1st observation  → state updated → readiness = WARMING_UP
  2nd+ observation → state updated → readiness = READY
  State eviction   → readiness = STATE_EVICTED
"""
import asyncio
import hashlib
from typing import Callable, Awaitable

from evidencegate.registry.plugin import (
    AnalyticPlugin,
    PluginProcessOutcome,
    PluginStateSnapshot,
    StateKey,
    StateTransitionRequest,
)
from evidencegate.domain.events import NetworkObservation
from evidencegate.domain.enums import EvidenceReadiness
from evidencegate.runtime.state import StateOperation, StateStore
from evidencegate.results.types import ResultDraft
from evidencegate.admission.evaluator import (
    EvaluationReadinessEvaluator,
    EvaluationReadinessDecision,
)


class ShardKeyState:
    """
    Per-state-key metadata tracked by the shard for readiness lifecycle.
    No threat science here — only counts to determine warm-up progression.
    """
    __slots__ = ("observation_count", "evicted")

    def __init__(self) -> None:
        self.observation_count: int = 0
        self.evicted: bool = False

    def record_observation(self) -> None:
        self.observation_count += 1

    def mark_evicted(self) -> None:
        self.evicted = True

    def reenter_warmup(self) -> None:
        self.observation_count = 0
        self.evicted = False


class LaneShard:
    """
    FIFO Shard for deterministic per-key processing.
    Each shard has a bounded mailbox; overflow creates a quality gap (IC-06).
    Per-key processing is serial (contract §7).
    """

    def __init__(
        self,
        shard_id: int,
        plugin: AnalyticPlugin,
        state_store: StateStore,
        result_callback: Callable[[ResultDraft], Awaitable[None]],
        max_size: int = 1000,
    ):
        self.shard_id = shard_id
        self.plugin = plugin
        self.state_store = state_store
        self.result_callback = result_callback
        self.queue: asyncio.Queue[NetworkObservation] = asyncio.Queue(maxsize=max_size)
        self._task: asyncio.Task | None = None
        # Readiness tracking per state_key (no threat science)
        self._key_states: dict[str, ShardKeyState] = {}

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._consume())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def put(self, observation: NetworkObservation) -> None:
        await self.queue.put(observation)

    def put_nowait(self, observation: NetworkObservation) -> None:
        self.queue.put_nowait(observation)

    def get_readiness(self, state_key: str | None) -> EvaluationReadinessDecision:
        """Return current readiness for a key without mutating state."""
        if state_key is None:
            return EvaluationReadinessDecision(readiness=EvidenceReadiness.READY)
        ks = self._key_states.get(state_key)
        if ks is None:
            return EvaluationReadinessDecision(readiness=EvidenceReadiness.WARMING_UP)
        return EvaluationReadinessEvaluator.evaluate(
            observation_count=ks.observation_count,
            state_evicted=ks.evicted,
        )

    async def _consume(self) -> None:
        while True:
            observation = await self.queue.get()
            try:
                state_key = self.plugin.state_key(observation)
                key_str = str(state_key) if state_key is not None else None

                # ── Factual state update ─────────────────────────────────────
                # This ALWAYS runs for admissible observations.
                # Readiness state must never block this update (IC-16).
                state = None
                if key_str is not None:
                    entry = self.state_store.read(
                        namespace=self.plugin.manifest().plugin_id,
                        key=key_str,
                        at_time=observation.event_time,
                    )
                    state = (
                        PluginStateSnapshot.from_entry(entry)
                        if entry is not None
                        else None
                    )
                    # Update key tracking BEFORE readiness evaluation
                    if key_str not in self._key_states:
                        self._key_states[key_str] = ShardKeyState()
                    self._key_states[key_str].record_observation()

                # ── Evaluation Readiness ─────────────────────────────────────
                # Computed AFTER state update so it reflects the new count.
                readiness_decision = EvaluationReadinessEvaluator.evaluate(
                    observation_count=(
                        self._key_states[key_str].observation_count
                        if key_str is not None
                        else 1  # stateless observations are always ready
                    ),
                    state_evicted=(
                        self._key_states[key_str].evicted
                        if key_str is not None
                        else False
                    ),
                )

                context = {
                    "readiness": readiness_decision,
                    "shard_id": self.shard_id,
                }

                outcome = await self.plugin.process(observation, context, state)
                if not isinstance(outcome, PluginProcessOutcome):
                    raise TypeError("plugin process must return PluginProcessOutcome")

                transition = outcome.state_transition
                if transition is not None:
                    if not isinstance(transition, StateTransitionRequest):
                        raise TypeError(
                            "plugin state transition must be StateTransitionRequest"
                        )
                    if state_key is None:
                        raise ValueError(
                            "a stateless plugin invocation cannot request state mutation"
                        )
                    if transition.key != state_key:
                        raise ValueError(
                            "state transition key must match plugin.state_key(observation)"
                        )

                    transition_result = self.state_store.transition(
                        namespace=self.plugin.manifest().plugin_id,
                        key=transition.key,
                        expected_version=transition.expected_version,
                        operation=transition.operation,
                        payload=transition.payload,
                        event_time=observation.event_time,
                        ttl=transition.ttl,
                    )
                    if transition_result.operation in (
                        StateOperation.RESET,
                        StateOperation.REENTER_WARMUP,
                    ):
                        self._key_states[key_str].reenter_warmup()

                for res in outcome.result_drafts:
                    await self.result_callback(res)

            except Exception:
                # In a full implementation: emit a typed control event / error result.
                # For the MVP scaffold: swallow so the shard keeps running.
                pass
            finally:
                self.queue.task_done()


def compute_shard(plugin_id: str, state_key: StateKey | None, shard_count: int) -> int:
    """
    Deterministic shard assignment using SHA-256.
    Uses str(plugin_id || "||" || str(state_key)) so the same inputs always
    produce the same shard index within a run (IC-05).
    Must NOT use Python's built-in hash() which is randomised per process.
    """
    if state_key is None:
        return 0
    raw = f"{plugin_id}||{state_key}".encode("utf-8")
    hash_val = int(hashlib.sha256(raw).hexdigest(), 16)
    return hash_val % shard_count
