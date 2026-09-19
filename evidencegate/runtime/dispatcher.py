"""Lane ingress, admission, and deterministic shard dispatch."""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Awaitable, Callable, List

from evidencegate.admission.evaluator import AdmissionEvaluator, IngestAdmissionDecision
from evidencegate.domain.enums import ControlType, GapAction, OperationalHealth
from evidencegate.domain.events import NetworkObservation, RuntimeControlEvent
from evidencegate.domain.governance import LaneGovernance
from evidencegate.domain.quality import QualityGap
from evidencegate.metrics.registry import registry
from evidencegate.registry.plugin import AnalyticPlugin
from evidencegate.routing.router import LaneTarget
from evidencegate.runtime.shard import LaneShard, compute_shard


logger = logging.getLogger(__name__)
ControlSink = Callable[[RuntimeControlEvent], Awaitable[None]]
GapSink = Callable[[QualityGap], Awaitable[None]]


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
    ):
        self.target = target
        self.plugin = plugin
        self.governance = governance
        self.shards = shards
        self.shard_count = shard_count
        self.queue: asyncio.Queue[NetworkObservation] = asyncio.Queue(maxsize=max_size)
        self._task: asyncio.Task | None = None
        self.health = LaneHealthRecord(lane_id=str(target))
        self._gap_sink = gap_sink
        self._control_sink = control_sink

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

    def put_nowait(self, observation: NetworkObservation) -> None:
        self.queue.put_nowait(observation)

    async def _consume(self) -> None:
        while True:
            observation = await self.queue.get()
            try:
                manifest = self.plugin.manifest()
                decision = AdmissionEvaluator.evaluate(
                    observation, manifest, self.governance
                )
                if not decision.admitted:
                    await self._emit_admission_rejection(observation, decision)
                    continue

                state_key = self.plugin.state_key(observation)
                shard_idx = compute_shard(
                    manifest.plugin_id, state_key, self.shard_count
                )
                try:
                    self.shards[shard_idx].put_nowait(observation)
                except asyncio.QueueFull:
                    await self._handle_queue_saturation(observation, shard_idx)

            except Exception as exc:
                plugin_id = self._plugin_id()
                logger.exception(
                    "Unexpected error in dispatcher for lane %s", self.target
                )
                self.health.health = OperationalHealth.FAILED
                registry.processing_errors.labels(
                    lane=str(self.target), plugin_id=plugin_id
                ).inc()
                await self._emit_control(self._error_event(observation, plugin_id, exc))
            finally:
                self.queue.task_done()

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
        return await self._record_queue_saturation(
            observation,
            shard_label="ingress",
            reason="Lane ingress queue full — routed observation dropped before admission.",
        )

    async def _handle_queue_saturation(
        self, observation: NetworkObservation, shard_id: int = 0
    ) -> QualityGap:
        """Record admitted evidence dropped before plugin processing."""
        return await self._record_queue_saturation(
            observation,
            shard_label=str(shard_id),
            reason=(
                "Shard queue full — admitted observation dropped before plugin "
                "processing."
            ),
        )

    async def _record_queue_saturation(
        self,
        observation: NetworkObservation,
        shard_label: str,
        reason: str,
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
        self._invoke_gap_action(self.plugin.manifest().gap_action, gap)
        return gap

    def _invoke_gap_action(self, action: GapAction, gap: QualityGap) -> None:
        """Preserve existing bounded health behavior; lifecycle is deferred."""
        if action == GapAction.CONTINUE_WITH_QUALITY_FLAG:
            pass
        elif action in (GapAction.RESET_AFFECTED_STATE, GapAction.REENTER_WARMUP):
            self.health.health = OperationalHealth.BACKPRESSURED
        elif action == GapAction.ABSTAIN_UNTIL_RECOVERED:
            self.health.health = OperationalHealth.STALLED
        elif action == GapAction.DISABLE_LANE:
            self.health.health = OperationalHealth.DISABLED
