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
import logging
import uuid
from datetime import datetime, timezone
from typing import Callable, Awaitable

from evidencegate.registry.plugin import (
    AnalyticPlugin,
    PluginProcessOutcome,
    PluginStateSnapshot,
    StateKey,
    StateTransitionRequest,
)
from evidencegate.domain.events import NetworkObservation, RuntimeControlEvent
from evidencegate.domain.enums import ControlType, EvidenceReadiness, GapAction
from evidencegate.metrics.registry import registry
from evidencegate.runtime.state import StateEntry, StateOperation, StateStore
from evidencegate.runtime.provenance import parser_refs_from_observation
from evidencegate.results.types import ResultDraft, Result_T
from evidencegate.results.finalizer import ResultEmissionContext
from evidencegate.admission.evaluator import EvaluationReadinessDecision


logger = logging.getLogger(__name__)
ControlSink = Callable[[RuntimeControlEvent], Awaitable[None]]


class ShardKeyState:
    """
    Per-state-key metadata tracked by the shard for readiness lifecycle.
    No threat science here — only counts to determine warm-up progression.
    """
    __slots__ = ("readiness", "abstaining_gap_ids")

    def __init__(self) -> None:
        self.readiness = EvaluationReadinessDecision(EvidenceReadiness.WARMING_UP)
        self.abstaining_gap_ids: set[str] = set()

    def reenter_warmup(self) -> None:
        self.readiness = EvaluationReadinessDecision(EvidenceReadiness.WARMING_UP)

    @property
    def abstaining(self) -> bool:
        return bool(self.abstaining_gap_ids)


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
        result_callback: Callable[[Result_T | ResultDraft], Awaitable[None]],
        max_size: int = 1000,
        control_sink: ControlSink | None = None,
        lane_id: str | None = None,
        result_finalizer: Callable[[ResultDraft, ResultEmissionContext], Result_T] | None = None,
    ):
        self.shard_id = shard_id
        self.plugin = plugin
        self.state_store = state_store
        self.result_callback = result_callback
        self.control_sink = control_sink
        self.lane_id = lane_id
        self.result_finalizer = result_finalizer
        self.queue: asyncio.Queue[NetworkObservation] = asyncio.Queue(maxsize=max_size)
        self._task: asyncio.Task | None = None
        # Readiness tracking per state_key (no threat science)
        self._key_states: dict[str, ShardKeyState] = {}
        self._quality_degraded = False

    def set_quality_degraded(self, value: bool) -> None:
        """Set immutable-at-use lane quality context supplied to plugins."""
        self._quality_degraded = value

    def apply_gap_action(
        self,
        action: GapAction,
        gap_id: str,
        state_key: StateKey | None,
        event_time: datetime,
    ) -> tuple[str, str]:
        """Apply a bounded generic lifecycle action for one known state key."""
        if action is GapAction.CONTINUE_WITH_QUALITY_FLAG:
            return "APPLIED", "quality flag recorded at lane scope"
        if state_key is None:
            return "BLOCKED_NO_STATE_KEY", "no safe affected state key"

        key_str = str(state_key)
        key_state = self._key_states.setdefault(key_str, ShardKeyState())
        if action is GapAction.ABSTAIN_UNTIL_RECOVERED:
            key_state.abstaining_gap_ids.add(gap_id)
            return "APPLIED", "result publication suppressed for affected key"
        if action not in (GapAction.RESET_AFFECTED_STATE, GapAction.REENTER_WARMUP):
            return "NOT_APPLICABLE", "action is owned by lane dispatcher"

        namespace = self.plugin.manifest().plugin_id
        entry = self.state_store.read(namespace, state_key, event_time)
        if entry is None:
            return "NOT_APPLICABLE", "affected state is already missing"
        operation = (
            StateOperation.RESET
            if action is GapAction.RESET_AFFECTED_STATE
            else StateOperation.REENTER_WARMUP
        )
        self.state_store.transition(
            namespace=namespace,
            key=state_key,
            expected_version=entry.version,
            operation=operation,
            payload=None,
            event_time=event_time,
            ttl=None,
        )
        key_state.reenter_warmup()
        return "APPLIED", "versioned affected-state lifecycle transition applied"

    def resolve_gap(self, gap_id: str, state_key: StateKey | None) -> None:
        if state_key is not None:
            key_state = self._key_states.get(str(state_key))
            if key_state is not None:
                key_state.abstaining_gap_ids.discard(gap_id)

    async def handle_expiry(
        self, entry: StateEntry, watermark: datetime, publish_results: bool
    ) -> None:
        """Run post-expiry plugin work; state is already authoritatively absent."""
        key_str = str(entry.key)
        self._key_states.setdefault(key_str, ShardKeyState()).reenter_warmup()
        context = {
            "state_key": entry.key,
            "watermark": watermark,
            "shard_id": self.shard_id,
            "quality_degraded": self._quality_degraded,
        }
        try:
            outcome = await self.plugin.on_expire(
                entry.key, context, PluginStateSnapshot.from_entry(entry)
            )
            await self._deliver_lifecycle_outcome(
                outcome, watermark, "on_expire", entry.key, publish_results,
                state_version=entry.version,
            )
        except Exception as exc:
            await self._emit_lifecycle_error("on_expire", watermark, exc)

    async def handle_watermark(
        self, watermark: datetime, expired_state_count: int, publish_results: bool
    ) -> None:
        context = {
            "watermark": watermark,
            "expired_state_count": expired_state_count,
            "lane_id": self.lane_id,
            "quality_degraded": self._quality_degraded,
        }
        try:
            outcome = await self.plugin.on_watermark(watermark, context)
            await self._deliver_lifecycle_outcome(
                outcome, watermark, "on_watermark", None, publish_results,
                state_version=None,
            )
        except Exception as exc:
            await self._emit_lifecycle_error("on_watermark", watermark, exc)

    async def _deliver_lifecycle_outcome(
        self,
        outcome: PluginProcessOutcome,
        watermark: datetime,
        callback: str,
        state_key: StateKey | None,
        publish_results: bool,
        state_version: int | None = None,
    ) -> None:
        if not isinstance(outcome, PluginProcessOutcome):
            raise TypeError(f"plugin {callback} must return PluginProcessOutcome")
        if outcome.state_transition is not None:
            raise ValueError(f"plugin {callback} cannot request state mutation")
        abstaining = state_key is not None and self._key_states.get(
            str(state_key), ShardKeyState()
        ).abstaining
        if publish_results and not abstaining:
            for draft in outcome.result_drafts:
                trigger = (
                    f"state:{self._plugin_id()}:{state_key}"
                    if state_key is not None
                    else f"watermark:{watermark.isoformat()}"
                )
                await self._deliver_draft(
                    draft,
                    ResultEmissionContext(
                        lane_id=self.lane_id or "unassigned",
                        causal_result_time=watermark,
                        quality_refs=(),
                        provenance_refs=(),
                        readiness=EvidenceReadiness.READY,
                        quality_degraded=self._quality_degraded,
                        trigger_reference=trigger,
                        state_version=state_version,
                    ),
                )

    async def _emit_lifecycle_error(
        self, callback: str, watermark: datetime, exc: Exception
    ) -> None:
        registry.processing_errors.labels(
            lane=self.lane_id or "unassigned", plugin_id=self._plugin_id()
        ).inc()
        await self._emit_control(RuntimeControlEvent(
            control_event_id=str(uuid.uuid4()), schema_version="1.0",
            control_type=ControlType.ERROR, ingest_time=datetime.now(timezone.utc),
            event_time=watermark, lane_id=self.lane_id,
            typed_payload={"component": "lifecycle", "callback": callback,
                "plugin_id": self._plugin_id(), "shard_id": self.shard_id,
                "exception_type": type(exc).__name__, "error": str(exc)[:500]},
        ))

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
        return ks.readiness

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
                    if key_str not in self._key_states:
                        self._key_states[key_str] = ShardKeyState()

                # ── Evaluation Readiness ─────────────────────────────────────
                # Computed AFTER state update so it reflects the new count.
                readiness_decision = (
                    self._key_states[key_str].readiness if key_str is not None
                    else EvaluationReadinessDecision(EvidenceReadiness.READY)
                )

                context = {
                    "readiness": readiness_decision,
                    "shard_id": self.shard_id,
                    "quality_degraded": self._quality_degraded,
                }

                outcome = await self.plugin.process(observation, context, state)
                if not isinstance(outcome, PluginProcessOutcome):
                    raise TypeError("plugin process must return PluginProcessOutcome")

                # A stateful mechanism, rather than the runtime, owns its
                # readiness. Validate before publication; factual transition
                # remains eligible to commit below.
                readiness_error = None
                if state_key is not None:
                    if not isinstance(outcome.evaluation_readiness, EvaluationReadinessDecision):
                        readiness_error = ValueError(
                            "stateful plugin process outcome must declare evaluation_readiness"
                        )
                    else:
                        readiness_decision = outcome.evaluation_readiness
                elif outcome.evaluation_readiness is not None:
                    if not isinstance(outcome.evaluation_readiness, EvaluationReadinessDecision):
                        raise TypeError("evaluation_readiness must be EvaluationReadinessDecision")
                    readiness_decision = outcome.evaluation_readiness

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
                    if transition.operation is StateOperation.UPSERT:
                        policy = self.plugin.manifest().state_resource_policy
                        if policy is None:
                            raise ValueError("stateful UPSERT requires manifest.state_resource_policy")
                        if transition.ttl is not None and transition.ttl > policy.max_ttl:
                            raise ValueError("state transition TTL exceeds manifest state resource policy")

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

                if readiness_error is not None:
                    raise readiness_error

                # Readiness is committed only once the requested transition
                # succeeds. RESET/REENTER deliberately retain their neutral
                # runtime warm-up lifecycle decision.
                if state_key is not None and (
                    transition is None
                    or transition.operation not in (
                        StateOperation.RESET,
                        StateOperation.REENTER_WARMUP,
                    )
                ):
                    self._key_states[key_str].readiness = readiness_decision

                abstaining = key_str is not None and self._key_states[key_str].abstaining
                if not abstaining:
                    for draft in outcome.result_drafts:
                        await self._deliver_draft(
                            draft,
                            ResultEmissionContext(
                                lane_id=self.lane_id or "unassigned",
                                causal_result_time=observation.causal_available_time,
                                quality_refs=(observation.quality_ref,),
                                provenance_refs=(observation.provenance_ref,),
                                readiness=readiness_decision.readiness,
                                quality_degraded=self._quality_degraded,
                                trigger_reference=observation.observation_id,
                                source_observation_ids=(observation.observation_id,),
                                source_ids=(observation.source_id,),
                                quality_snapshot=observation.quality,
                                visibility_snapshot=observation.visibility,
                                state_version=state.version if state is not None else None,
                                parser_refs=parser_refs_from_observation(observation),
                            ),
                        )

            except Exception as exc:
                plugin_id = self._plugin_id()
                registry.processing_errors.labels(
                    lane=self.lane_id or "unassigned",
                    plugin_id=plugin_id,
                ).inc()
                logger.exception(
                    "Shard processing failed (lane=%s plugin=%s shard=%s observation=%s)",
                    self.lane_id,
                    plugin_id,
                    self.shard_id,
                    observation.observation_id,
                )
                event = RuntimeControlEvent(
                    control_event_id=str(uuid.uuid4()),
                    schema_version="1.0",
                    control_type=ControlType.ERROR,
                    ingest_time=datetime.now(timezone.utc),
                    event_time=observation.event_time,
                    source_id=observation.source_id,
                    lane_id=self.lane_id,
                    provenance_ref=observation.provenance_ref,
                    quality_ref=observation.quality_ref,
                    typed_payload={
                        "component": "shard",
                        "plugin_id": plugin_id,
                        "shard_id": self.shard_id,
                        "observation_id": observation.observation_id,
                        "exception_type": type(exc).__name__,
                        "error": str(exc)[:500],
                    },
                )
                await self._emit_control(event)
            finally:
                self.queue.task_done()

    def _plugin_id(self) -> str:
        try:
            return self.plugin.manifest().plugin_id
        except Exception:
            return type(self.plugin).__name__

    async def _deliver_draft(
        self, draft: ResultDraft, context: ResultEmissionContext
    ) -> None:
        """Finalize before delivery when this shard is runtime-wired.

        The ``None`` compatibility mode is retained for isolated M1–M4 shard
        unit tests; production supervisor wiring always supplies a finalizer.
        """
        if self.result_finalizer is None:
            await self.result_callback(draft)
            return
        await self.result_callback(self.result_finalizer(draft, context))

    async def _emit_control(self, event: RuntimeControlEvent) -> None:
        if self.control_sink is None:
            logger.error("Runtime control event has no sink: %s", event.typed_payload)
            return
        try:
            await self.control_sink(event)
        except Exception:
            logger.exception(
                "Control sink failed for shard event %s; event will not be retried",
                event.control_event_id,
            )


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
