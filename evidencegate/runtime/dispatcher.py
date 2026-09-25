"""Lane ingress, admission, and deterministic shard dispatch."""

import asyncio
import heapq
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Awaitable, Callable, List

from evidencegate.admission.evaluator import AdmissionEvaluator, IngestAdmissionDecision
from evidencegate.runtime.trace import emit_trace
from evidencegate.domain.enums import ControlType, GapAction, OperationalHealth
from evidencegate.domain.events import NetworkObservation, RuntimeControlEvent
from evidencegate.domain.governance import LaneGovernance
from evidencegate.domain.quality import QualityGap
from evidencegate.metrics.registry import registry
from evidencegate.registry.plugin import AnalyticPlugin, StateKey
from evidencegate.routing.router import LaneTarget
from evidencegate.runtime.shard import LaneShard, compute_shard


logger = logging.getLogger(__name__)
ControlSink = Callable[[RuntimeControlEvent], Awaitable[None]]
GapSink = Callable[[QualityGap], Awaitable[None]]


class WatermarkError(ValueError):
    """An invalid lane watermark request."""


class DispatcherStoppedError(RuntimeError):
    """A dispatcher stopped before a requested boundary could complete."""


@dataclass(frozen=True, slots=True)
class _WatermarkRequest:
    """Private queue marker that serializes one lane watermark with ingress."""

    watermark: datetime
    completion: asyncio.Future[bool]


@dataclass(frozen=True, slots=True)
class EventTimeReorderPolicy:
    """Independent per-key and lane-wide engineering reorder memory bounds."""

    max_buffered_events_per_key: int
    max_buffered_events_total: int

    def __post_init__(self) -> None:
        for name in (
            "max_buffered_events_per_key", "max_buffered_events_total",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be a non-bool integer")
            if value <= 0:
                raise ValueError(f"{name} must be greater than zero")
        if self.max_buffered_events_total < self.max_buffered_events_per_key:
            raise ValueError(
                "max_buffered_events_total cannot be less than "
                "max_buffered_events_per_key"
            )


def source_position_order(source_position: str) -> tuple[int, int | str]:
    """Return a protocol-neutral order: ASCII decimal numerically, else lexical.

    Numeric positions sort before non-numeric positions when the two forms are
    mixed. No protocol-specific meaning is inferred from the string.
    """
    if re.fullmatch(r"[0-9]+", source_position):
        return (0, int(source_position))
    return (1, source_position)


class LaneHealthRecord:
    """Mutable lane health record and in-memory saturation evidence."""

    __slots__ = ("lane_id", "health", "active_gaps", "total_gaps_created")

    def __init__(self, lane_id: str) -> None:
        self.lane_id = lane_id
        self.health: OperationalHealth = OperationalHealth.HEALTHY
        self.active_gaps: list[QualityGap] = []
        self.total_gaps_created: int = 0

    def record_gap(self, gap: QualityGap) -> None:
        self.active_gaps.append(gap)
        self.total_gaps_created += 1
        self.health = OperationalHealth.BACKPRESSURED

    def close_gap(self, gap_id: str) -> None:
        self.active_gaps = [g for g in self.active_gaps if g.gap_id != gap_id]
        if not self.active_gaps:
            self.health = OperationalHealth.HEALTHY


class LaneDispatcher:
    """Read a bounded lane queue, apply admission, and dispatch to a shard."""

    def __init__(
        self,
        target: LaneTarget,
        plugin: AnalyticPlugin,
        governance: LaneGovernance,
        shards: List[LaneShard],
        shard_count: int,
        max_size: int = 2000,
        gap_sink: GapSink | None = None,
        control_sink: ControlSink | None = None,
        reorder_policy: EventTimeReorderPolicy | None = None,
        trace_sink: Callable[..., None] | None = None,
    ):
        self.target = target
        self.plugin = plugin
        self.governance = governance
        self.shards = shards
        self.shard_count = shard_count
        self.queue: asyncio.Queue[NetworkObservation | _WatermarkRequest] = (
            asyncio.Queue(maxsize=max_size)
        )
        self._task: asyncio.Task | None = None
        self._stopping = False
        self._watermark_put_tasks: set[asyncio.Task[None]] = set()
        self.health = LaneHealthRecord(lane_id=str(target))
        self._gap_sink = gap_sink
        self._control_sink = control_sink
        self._trace_sink = trace_sink
        self._gap_context: dict[str, tuple[GapAction, StateKey | None, int | None]] = {}
        self._disabled = False
        self._watermark: datetime | None = None
        self._reorder_policy = reorder_policy
        self._reorder_buffers: dict[
            StateKey,
            list[tuple[datetime, tuple[int, int | str], str, int, NetworkObservation]],
        ] = {}
        self._reorder_sequence = 0
        self._pending_reorder_total = 0
        self._peak_pending_reorder_total = 0
        self._peak_pending_reorder_per_key = 0

    @property
    def watermark(self) -> datetime | None:
        return self._watermark

    @property
    def pending_reorder_count(self) -> int:
        """Number of admitted stateful observations awaiting a watermark."""
        return self._pending_reorder_total

    @property
    def max_pending_reorder_per_key(self) -> int:
        """Largest current per-key reorder occupancy, without exposing keys."""
        return max((len(buffer) for buffer in self._reorder_buffers.values()), default=0)

    @property
    def peak_pending_reorder_total(self) -> int:
        """High-water mark for total reorder occupancy since the last reset."""
        return self._peak_pending_reorder_total

    @property
    def peak_pending_reorder_per_key(self) -> int:
        """Privacy-safe per-key occupancy high-water mark since reset."""
        return self._peak_pending_reorder_per_key

    def reset_reorder_peaks(self) -> None:
        """Reset high-water marks to current occupancy for a measurement run."""
        self._peak_pending_reorder_total = self.pending_reorder_count
        self._peak_pending_reorder_per_key = self.max_pending_reorder_per_key

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._consume())

    async def stop(self) -> None:
        self._stopping = True
        put_tasks = tuple(self._watermark_put_tasks)
        for task in put_tasks:
            task.cancel()
        if put_tasks:
            await asyncio.gather(*put_tasks, return_exceptions=True)

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        error = DispatcherStoppedError(
            "dispatcher stopped before watermark boundary completed"
        )
        while True:
            try:
                item = self.queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            try:
                if isinstance(item, _WatermarkRequest) and not item.completion.done():
                    item.completion.set_exception(error)
            finally:
                self.queue.task_done()

    def put_nowait(self, observation: NetworkObservation) -> None:
        if self._stopping:
            raise DispatcherStoppedError("dispatcher is stopped")
        self.queue.put_nowait(observation)

    async def _consume(self) -> None:
        while True:
            item = await self.queue.get()
            try:
                if isinstance(item, _WatermarkRequest):
                    try:
                        advanced = await self._advance_watermark_serialized(
                            item.watermark
                        )
                    except asyncio.CancelledError:
                        if not item.completion.done():
                            item.completion.set_exception(DispatcherStoppedError(
                                "dispatcher stopped during watermark boundary"
                            ))
                        raise
                    except Exception as exc:
                        if not item.completion.done():
                            item.completion.set_exception(exc)
                    else:
                        if not item.completion.done():
                            item.completion.set_result(advanced)
                    continue

                observation = item
                if self._disabled:
                    await self._emit_disabled_skip(observation)
                    continue
                if self._watermark is not None and observation.event_time < self._watermark:
                    await self._emit_late_event(observation)
                    continue
                manifest = self.plugin.manifest()
                decision = AdmissionEvaluator.evaluate(
                    observation, manifest, self.governance
                )
                if not decision.admitted:
                    emit_trace(
                        self._trace_sink,
                        "ADMISSION_REJECTED",
                        observation_id=observation.observation_id,
                        observation_type=observation.observation_type.value,
                        lane_id=str(self.target),
                        mechanism=self.plugin.manifest().mechanism_id,
                        reason=", ".join(reason.value for reason in decision.reasons),
                    )
                    await self._emit_admission_rejection(observation, decision)
                    continue

                state_key = self.plugin.state_key(observation)
                shard_idx = compute_shard(
                    manifest.plugin_id, state_key, self.shard_count
                )
                if state_key is None:
                    await self._dispatch_to_shard(observation, shard_idx, state_key)
                else:
                    await self._buffer_stateful(observation, state_key, shard_idx)

            except Exception as exc:
                plugin_id = self._plugin_id()
                logger.exception(
                    "Unexpected error in dispatcher for lane %s", self.target
                )
                self.health.health = OperationalHealth.FAILED
                registry.processing_errors.labels(
                    lane=str(self.target), plugin_id=plugin_id
                ).inc()
                await self._emit_control(self._error_event(item, plugin_id, exc))
            finally:
                self.queue.task_done()

    async def _dispatch_to_shard(
        self,
        observation: NetworkObservation,
        shard_idx: int,
        state_key: StateKey | None,
    ) -> bool:
        try:
            self.shards[shard_idx].put_nowait(observation)
            return True
        except asyncio.QueueFull:
            await self._handle_queue_saturation(observation, shard_idx, state_key)
            return False

    async def _buffer_stateful(
        self, observation: NetworkObservation, state_key: StateKey, shard_idx: int
    ) -> None:
        policy = self._reorder_policy
        if policy is None:
            raise RuntimeError(
                "stateful lane requires an explicit EventTimeReorderPolicy"
            )
        buffer = self._reorder_buffers.get(state_key)
        # Deterministic precedence: a fact that violates both limits is
        # classified as per-key saturation.
        if buffer is not None and len(buffer) >= policy.max_buffered_events_per_key:
            await self._handle_reorder_saturation(observation, state_key, shard_idx)
            return
        if self._pending_reorder_total >= policy.max_buffered_events_total:
            await self._handle_total_reorder_saturation(
                observation, state_key, shard_idx
            )
            return
        if buffer is None:
            buffer = self._reorder_buffers.setdefault(state_key, [])
        self._reorder_sequence += 1
        heapq.heappush(
            buffer,
            (
                observation.event_time,
                source_position_order(observation.source_position),
                observation.observation_id,
                self._reorder_sequence,
                observation,
            ),
        )
        self._pending_reorder_total += 1
        self._peak_pending_reorder_per_key = max(
            self._peak_pending_reorder_per_key, len(buffer)
        )
        self._peak_pending_reorder_total = max(
            self._peak_pending_reorder_total, self.pending_reorder_count
        )

    def _plugin_id(self) -> str:
        try:
            return self.plugin.manifest().plugin_id
        except Exception:
            return type(self.plugin).__name__

    def _error_event(
        self, observation: NetworkObservation, plugin_id: str, exc: Exception
    ) -> RuntimeControlEvent:
        return RuntimeControlEvent(
            control_event_id=str(uuid.uuid4()),
            schema_version="1.0",
            control_type=ControlType.ERROR,
            ingest_time=datetime.now(timezone.utc),
            event_time=observation.event_time,
            source_id=observation.source_id,
            lane_id=str(self.target),
            provenance_ref=observation.provenance_ref,
            quality_ref=observation.quality_ref,
            typed_payload={
                "component": "dispatcher",
                "plugin_id": plugin_id,
                "observation_id": observation.observation_id,
                "exception_type": type(exc).__name__,
                "error": str(exc)[:500],
            },
        )

    async def _emit_admission_rejection(
        self,
        observation: NetworkObservation,
        decision: IngestAdmissionDecision,
    ) -> None:
        event = RuntimeControlEvent(
            control_event_id=str(uuid.uuid4()),
            schema_version="1.0",
            control_type=ControlType.ADMISSION_REJECTED,
            ingest_time=datetime.now(timezone.utc),
            event_time=observation.event_time,
            source_id=observation.source_id,
            lane_id=str(self.target),
            provenance_ref=observation.provenance_ref,
            quality_ref=decision.quality_ref,
            typed_payload={
                "component": "dispatcher",
                "observation_id": observation.observation_id,
                "plugin_id": self._plugin_id(),
                "lane_id": str(self.target),
                "reasons": decision.reasons,
                "governance_version": decision.governance_version,
                "quality_ref": decision.quality_ref,
            },
        )
        await self._emit_control(event)

    async def _emit_disabled_skip(self, observation: NetworkObservation) -> None:
        await self._emit_control(RuntimeControlEvent(
            control_event_id=str(uuid.uuid4()), schema_version="1.0",
            control_type=ControlType.GAP_ACTION_STATUS,
            ingest_time=datetime.now(timezone.utc), event_time=observation.event_time,
            source_id=observation.source_id, lane_id=str(self.target),
            provenance_ref=observation.provenance_ref, quality_ref=observation.quality_ref,
            typed_payload={"component": "dispatcher", "plugin_id": self._plugin_id(),
                "observation_id": observation.observation_id,
                "action": GapAction.DISABLE_LANE.value, "status": "SKIPPED_DISABLED",
                "reason": "lane is operationally disabled"},
        ))

    async def _emit_late_event(self, observation: NetworkObservation) -> None:
        await self._emit_control(RuntimeControlEvent(
            control_event_id=str(uuid.uuid4()), schema_version="1.0",
            control_type=ControlType.LATE_EVENT_OBSERVED,
            ingest_time=datetime.now(timezone.utc), event_time=observation.event_time,
            source_id=observation.source_id, lane_id=str(self.target),
            provenance_ref=observation.provenance_ref, quality_ref=observation.quality_ref,
            typed_payload={"component": "dispatcher", "lane_id": str(self.target),
                "plugin_id": self._plugin_id(), "observation_id": observation.observation_id,
                "event_time": observation.event_time.isoformat(),
                "current_watermark": self._watermark.isoformat() if self._watermark else None,
                "source_id": observation.source_id,
                "reason": "event_time is earlier than the lane watermark"},
        ))

    async def advance_watermark(self, watermark: datetime) -> bool:
        """Enqueue and await a lane watermark serialized with observation ingress."""
        if not isinstance(watermark, datetime):
            raise TypeError("watermark must be a datetime")
        if watermark.tzinfo is None or watermark.utcoffset() is None:
            raise WatermarkError("watermark must be timezone-aware")
        if self._stopping or self._task is None or self._task.done():
            raise DispatcherStoppedError("dispatcher is not running")
        if asyncio.current_task() is self._task:
            raise RuntimeError("dispatcher consumer cannot await its own watermark")

        loop = asyncio.get_running_loop()
        completion: asyncio.Future[bool] = loop.create_future()
        request = _WatermarkRequest(watermark, completion)
        put_task = asyncio.create_task(self.queue.put(request))
        self._watermark_put_tasks.add(put_task)
        try:
            await put_task
        finally:
            self._watermark_put_tasks.discard(put_task)
        return await completion

    async def _advance_watermark_serialized(self, watermark: datetime) -> bool:
        """Execute one watermark marker inside the sole dispatcher consumer."""
        previous = self._watermark
        if previous is not None:
            if watermark < previous:
                raise WatermarkError("watermark must not move backward")
            if watermark == previous:
                return False

        for state_key in sorted(self._reorder_buffers, key=str):
            buffer = self._reorder_buffers[state_key]
            shard_idx = compute_shard(
                self._plugin_id(), state_key, self.shard_count
            )
            while buffer and buffer[0][0] < watermark:
                observation = heapq.heappop(buffer)[-1]
                self._pending_reorder_total -= 1
                await self._dispatch_to_shard(observation, shard_idx, state_key)
            if not buffer:
                del self._reorder_buffers[state_key]

        # Every shard item ahead of this marker must finish before lifecycle work.
        # Later observations remain behind the marker in this same lane queue.
        for shard in self.shards:
            await shard.queue.join()

        # All shards share this store, so expiry is owned and invoked once here.
        expired = self.shards[0].state_store.expire(watermark)
        plugin_id = self._plugin_id()
        for entry in expired:
            shard_id = compute_shard(plugin_id, entry.key, self.shard_count)
            await self.shards[shard_id].handle_expiry(
                entry, watermark, publish_results=not self._disabled
            )
        await self.shards[0].handle_watermark(
            watermark, len(expired), publish_results=not self._disabled
        )

        # Commit only after all pre-boundary work and lifecycle callbacks finish.
        self._watermark = watermark
        await self._emit_control(RuntimeControlEvent(
            control_event_id=str(uuid.uuid4()), schema_version="1.0",
            control_type=ControlType.WATERMARK_ADVANCED,
            ingest_time=datetime.now(timezone.utc), event_time=watermark,
            lane_id=str(self.target),
            typed_payload={"component": "lifecycle", "lane_id": str(self.target),
                "plugin_id": plugin_id,
                "previous_watermark": previous.isoformat() if previous else None,
                "new_watermark": watermark.isoformat(),
                "expired_state_count": len(expired)},
        ))
        return True

    async def _emit_control(self, event: RuntimeControlEvent) -> None:
        if self._control_sink is None:
            logger.warning("Runtime control event has no sink: %s", event.typed_payload)
            return
        try:
            await self._control_sink(event)
        except Exception:
            logger.exception(
                "Control sink failed for dispatcher event %s; event will not be retried",
                event.control_event_id,
            )

    async def _emit_gap(self, gap: QualityGap) -> None:
        if self._gap_sink is None:
            logger.error("Quality gap has no sink: %s", gap)
            return
        try:
            await self._gap_sink(gap)
        except Exception:
            logger.exception(
                "Gap sink failed for gap %s; gap will not be retried", gap.gap_id
            )

    async def handle_ingress_saturation(
        self, observation: NetworkObservation
    ) -> QualityGap:
        """Record evidence dropped before lane admission."""
        try:
            state_key = self.plugin.state_key(observation)
            shard_id = compute_shard(self._plugin_id(), state_key, self.shard_count)
        except Exception:
            logger.exception("Unable to identify affected key for lane ingress gap")
            state_key, shard_id = None, None
        return await self._record_queue_saturation(
            observation,
            shard_label="ingress",
            reason="Lane ingress queue full — routed observation dropped before admission.",
            state_key=state_key, shard_id=shard_id,
        )

    async def _handle_queue_saturation(
        self, observation: NetworkObservation, shard_id: int = 0, state_key: StateKey | None = None
    ) -> QualityGap:
        """Record admitted evidence dropped before plugin processing."""
        return await self._record_queue_saturation(
            observation,
            shard_label=str(shard_id),
            reason=(
                "Shard queue full — admitted observation dropped before plugin "
                "processing."
            ),
            state_key=state_key, shard_id=shard_id,
        )

    async def _handle_reorder_saturation(
        self,
        observation: NetworkObservation,
        state_key: StateKey,
        shard_id: int,
    ) -> QualityGap:
        """Record admitted evidence that cannot fit its bounded reorder buffer."""
        gap = QualityGap(
            gap_id=str(uuid.uuid4()),
            scope=str(self.target),
            first_known_event_time=observation.event_time,
            last_known_event_time=observation.event_time,
            detection_time=observation.ingest_time,
            count=1,
            gap_types=("REORDER_BUFFER_SATURATION",),
            reason=(
                "Per-key event-time reorder buffer full; admitted observation "
                f"could not be retained safely for state key {state_key!s}."
            ),
        )
        self.health.record_gap(gap)
        registry.queue_full_events.labels(
            lane=str(self.target), shard_id="reorder"
        ).inc()
        await self._emit_gap(gap)
        await self._invoke_gap_action(
            self.plugin.manifest().gap_action, gap, state_key, shard_id
        )
        return gap

    async def _handle_total_reorder_saturation(
        self,
        observation: NetworkObservation,
        state_key: StateKey,
        shard_id: int,
    ) -> QualityGap:
        """Record an incoming fact rejected by the lane-wide reorder budget."""
        policy = self._reorder_policy
        if policy is None:  # Defensive; stateful buffering already requires it.
            raise RuntimeError("total reorder saturation requires a reorder policy")
        gap = QualityGap(
            gap_id=str(uuid.uuid4()),
            scope=str(self.target),
            first_known_event_time=observation.event_time,
            last_known_event_time=observation.event_time,
            detection_time=observation.ingest_time,
            count=1,
            gap_types=("REORDER_BUFFER_TOTAL_SATURATION",),
            reason=(
                "Lane-wide event-time reorder buffer full; incoming admitted "
                "observation was not retained. "
                f"configured_total_limit={policy.max_buffered_events_total}; "
                f"current_pending_total={self._pending_reorder_total}; "
                "affected_state_key_known=true."
            ),
        )
        self.health.record_gap(gap)
        registry.queue_full_events.labels(
            lane=str(self.target), shard_id="reorder-total"
        ).inc()
        await self._emit_gap(gap)
        await self._invoke_gap_action(
            self.plugin.manifest().gap_action, gap, state_key, shard_id
        )
        return gap

    async def _record_queue_saturation(
        self,
        observation: NetworkObservation,
        shard_label: str,
        reason: str,
        state_key: StateKey | None,
        shard_id: int | None,
    ) -> QualityGap:
        gap = QualityGap(
            gap_id=str(uuid.uuid4()),
            scope=str(self.target),
            first_known_event_time=observation.event_time,
            last_known_event_time=observation.event_time,
            detection_time=observation.ingest_time,
            count=1,
            gap_types=("QUEUE_SATURATION",),
            reason=reason,
        )
        self.health.record_gap(gap)
        registry.queue_full_events.labels(
            lane=str(self.target), shard_id=shard_label
        ).inc()
        await self._emit_gap(gap)
        await self._invoke_gap_action(self.plugin.manifest().gap_action, gap, state_key, shard_id)
        return gap

    async def _invoke_gap_action(
        self, action: GapAction, gap: QualityGap, state_key: StateKey | None, shard_id: int | None
    ) -> None:
        self._gap_context[gap.gap_id] = (action, state_key, shard_id)
        self._set_quality_degraded(True)
        status, reason = "APPLIED", "lane quality degradation remains visible"
        try:
            if action is GapAction.DISABLE_LANE:
                self._disabled = True
                self.health.health = OperationalHealth.DISABLED
                for shard in self.shards:
                    shard.set_publication_enabled(False)
            elif action is not GapAction.CONTINUE_WITH_QUALITY_FLAG:
                if state_key is None or shard_id is None:
                    status, reason = "BLOCKED_NO_STATE_KEY", "no safe affected state key"
                else:
                    status, reason = self.shards[shard_id].apply_gap_action(
                        action, gap.gap_id, state_key, gap.detection_time
                    )
        except Exception as exc:
            logger.exception("Gap action failed for %s", gap.gap_id)
            status, reason = "FAILED", str(exc)[:500]
        await self._emit_control(RuntimeControlEvent(
            control_event_id=str(uuid.uuid4()), schema_version="1.0",
            control_type=ControlType.GAP_ACTION_STATUS,
            ingest_time=datetime.now(timezone.utc), event_time=gap.detection_time,
            source_id=None, lane_id=str(self.target), provenance_ref=None, quality_ref=None,
            typed_payload={"component": "dispatcher", "gap_id": gap.gap_id,
                "lane_id": str(self.target), "plugin_id": self._plugin_id(),
                "action": action.value, "status": status, "state_key_known": state_key is not None,
                "shard_id": shard_id, "reason": reason},
        ))

    def _set_quality_degraded(self, value: bool) -> None:
        for shard in self.shards:
            shard.set_quality_degraded(value)

    async def resolve_gap(self, gap_id: str) -> bool:
        context = self._gap_context.pop(gap_id, None)
        if context is None:
            return False
        _, state_key, shard_id = context
        if state_key is not None and shard_id is not None:
            self.shards[shard_id].resolve_gap(gap_id, state_key)
        self.health.close_gap(gap_id)
        self._set_quality_degraded(bool(self.health.active_gaps))
        if self._disabled:
            self.health.health = OperationalHealth.DISABLED
        return True

    def enable_lane(self) -> None:
        self._disabled = False
        for shard in self.shards:
            shard.set_publication_enabled(True)
        self.health.health = (
            OperationalHealth.BACKPRESSURED if self.health.active_gaps else OperationalHealth.HEALTHY
        )
