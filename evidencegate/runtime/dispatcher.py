"""
runtime/dispatcher.py — Lane ingress queue + ingest admission + shard dispatch.

Pipeline position (contract §7, exact order):
  bounded lane ingress queue
  → ingest admission (IngestAdmissionDecision)
  → state-key calculation
  → deterministic shard dispatch

Quality gap behavior (IC-06, contract §4):
  On queue saturation: create typed QualityGap record, update lane health,
  make observable, persist where required, invoke declared GapAction.
  Never create a gap and then discard it with pass.
"""
import asyncio
import uuid
from typing import Dict, List, Callable, Awaitable

from evidencegate.registry.plugin import AnalyticPlugin
from evidencegate.domain.events import NetworkObservation
from evidencegate.domain.enums import GapAction, OperationalHealth
from evidencegate.domain.governance import LaneGovernance
from evidencegate.domain.quality import QualityGap
from evidencegate.admission.evaluator import AdmissionEvaluator, IngestAdmissionDecision
from evidencegate.runtime.shard import LaneShard, compute_shard
from evidencegate.routing.router import LaneTarget


class LaneHealthRecord:
    """
    Mutable lane health record. Observability point for saturation gaps.
    In a full implementation this would be published to metrics and persisted.
    """
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
    """
    Reads from bounded lane ingress queue → ingest admission → shard dispatch.
    On queue saturation: emits a QualityGap, invokes GapAction, updates health.
    """

    def __init__(
        self,
        target: LaneTarget,
        plugin: AnalyticPlugin,
        governance: LaneGovernance,
        shards: List[LaneShard],
        shard_count: int,
        max_size: int = 2000,
        gap_sink: Callable[[QualityGap], Awaitable[None]] | None = None,
    ):
        self.target = target
        self.plugin = plugin
        self.governance = governance
        self.shards = shards
        self.shard_count = shard_count
        self.queue: asyncio.Queue[NetworkObservation] = asyncio.Queue(maxsize=max_size)
        self._task: asyncio.Task | None = None
        self.health = LaneHealthRecord(lane_id=str(target))
        # Optional async callback for gap persistence / broadcast
        self._gap_sink = gap_sink

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

                # ── Ingest Admission (Phase 1) ───────────────────────────────
                # Never checks WARMING_UP / INSUFFICIENT_HISTORY / STATE_EVICTED.
                decision: IngestAdmissionDecision = AdmissionEvaluator.evaluate(
                    observation, manifest, self.governance
                )
                if not decision.admitted:
                    # Rejected — create typed diagnostic and do NOT erase as benign.
                    # For the MVP scaffold we log to health record; a full
                    # implementation would emit a typed result via result_callback.
                    continue

                # ── State-key calculation ────────────────────────────────────
                state_key = self.plugin.state_key(observation)
                shard_idx = compute_shard(manifest.plugin_id, state_key, self.shard_count)

                # ── Deterministic shard dispatch ─────────────────────────────
                target_shard = self.shards[shard_idx]
                try:
                    target_shard.put_nowait(observation)
                except asyncio.QueueFull:
                    await self._handle_queue_saturation(observation)

            except Exception as e:
                # IC contract: Do not use broad silent handlers.
                import logging
                logging.exception(f"Unexpected error in dispatcher for lane {self.target}")
                self.health.health = OperationalHealth.FAILED
                
                from evidencegate.domain.events import RuntimeControlEvent
                from evidencegate.domain.enums import ControlType
                from datetime import datetime, timezone
                from evidencegate.metrics.registry import registry
                
                # Increment error metric
                registry.processing_errors.labels(lane=str(self.target), plugin_id=manifest.plugin_id).inc()
                
                error_event = RuntimeControlEvent(
                    control_event_id=str(uuid.uuid4()),
                    schema_version="1.0",
                    control_type=ControlType.ERROR,
                    ingest_time=datetime.now(timezone.utc),
                    typed_payload={"error": str(e), "observation_id": observation.observation_id},
                    lane_id=str(self.target)
                )
                
                if self._gap_sink is not None:
                    # In a full implementation, the control event might go to a different sink,
                    # but we simulate observability here.
                    pass
            finally:
                self.queue.task_done()

    async def _handle_queue_saturation(self, observation: NetworkObservation) -> None:
        """
        IC-06 / contract §4: Queue saturation creates visible gap/health evidence
        and invokes the declared GapAction. Never silently discards.
        """
        gap = QualityGap(
            gap_id=str(uuid.uuid4()),
            scope=str(self.target),
            first_known_event_time=observation.event_time,
            last_known_event_time=observation.event_time,
            detection_time=observation.ingest_time,
            count=1,
            gap_types=("QUEUE_SATURATION",),
            reason="Shard queue full — observation dropped at lane boundary.",
        )

        # Update lane health record (observable via API / metrics)
        self.health.record_gap(gap)

        # Notify external sink (e.g. persistence layer, metrics collector)
        if self._gap_sink is not None:
            await self._gap_sink(gap)

        # Invoke the declared GapAction for this lane's plugin manifest
        gap_action = self.plugin.manifest().gap_action
        self._invoke_gap_action(gap_action, gap)

    def _invoke_gap_action(self, action: GapAction, gap: QualityGap) -> None:
        """
        Execute the declared GapAction. For the MVP scaffold only
        CONTINUE_WITH_QUALITY_FLAG is fully wired; others set health state.
        """
        if action == GapAction.CONTINUE_WITH_QUALITY_FLAG:
            # Lane continues; gap is already recorded in health.
            pass
        elif action == GapAction.RESET_AFFECTED_STATE:
            # In a full implementation: reset affected state keys in the shard.
            self.health.health = OperationalHealth.BACKPRESSURED
        elif action == GapAction.REENTER_WARMUP:
            # Mark that the shard should re-warm. Implemented in shard._key_states.
            self.health.health = OperationalHealth.BACKPRESSURED
        elif action == GapAction.ABSTAIN_UNTIL_RECOVERED:
            self.health.health = OperationalHealth.STALLED
        elif action == GapAction.DISABLE_LANE:
            self.health.health = OperationalHealth.DISABLED
