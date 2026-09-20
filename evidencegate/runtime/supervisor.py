import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Awaitable, Callable
from evidencegate.registry.plugin import AnalyticPlugin
from evidencegate.registry.manifest import PluginManifest
from evidencegate.domain.events import NetworkObservation, RuntimeControlEvent
from evidencegate.domain.governance import LaneGovernance
from evidencegate.domain.quality import QualityGap
from evidencegate.routing.router import RelevanceRouter, LaneTarget
from evidencegate.admission.evaluator import AdmissionEvaluator
from evidencegate.runtime.state import StateStore
from evidencegate.runtime.shard import LaneShard, compute_shard
from evidencegate.runtime.dispatcher import LaneDispatcher
from evidencegate.results.types import Result_T
from evidencegate.results.finalizer import ResultEmissionContext, ResultFinalizer
from evidencegate.domain.enums import ControlType
from evidencegate.metrics.registry import registry

logger = logging.getLogger(__name__)

class RuntimeSupervisor:
    """
    Wires the pipeline:
    Router -> Queue -> Ingest Admission -> State Key -> Shards -> Plugin -> Validator -> SQLite
    """
    def __init__(
        self,
        plugins: Dict[LaneTarget, AnalyticPlugin],
        governances: Dict[LaneTarget, LaneGovernance],
        result_writer: Callable[[Result_T, LaneTarget], Awaitable[None]],
        shard_count: int = 4,
        control_sink: Callable[[RuntimeControlEvent], Awaitable[None]] | None = None,
        gap_sink: Callable[[QualityGap], Awaitable[None]] | None = None,
    ):
        self.plugins = plugins
        self.governances = governances
        self.result_writer = result_writer
        self.shard_count = shard_count
        self.control_sink = control_sink
        self.gap_sink = gap_sink
        
        self.router = RelevanceRouter(plugins)
        self.state_stores: Dict[LaneTarget, StateStore] = {
            # Explicit lane watermarks, not observation timestamps, own expiry.
            target: StateStore(expire_on_access=False) for target in plugins.keys()
        }
        
        self.shards: Dict[LaneTarget, list[LaneShard]] = {}
        self.dispatchers: Dict[LaneTarget, LaneDispatcher] = {}
        for target, plugin in plugins.items():
            gov = self.governances.get(target)
            manifest = plugin.manifest()
            lane_shards = []
            for i in range(shard_count):
                async def bound_writer(res: Result_T, t=target):
                    await self.result_writer(res, t)

                def finalize(
                    draft, context: ResultEmissionContext,
                    m=manifest, g=gov,
                ) -> Result_T:
                    if g is None:
                        raise RuntimeError(f"lane {target} has no governance snapshot")
                    return ResultFinalizer.finalize(draft, m, g, context)
                
                shard = LaneShard(
                    shard_id=i,
                    plugin=plugin,
                    state_store=self.state_stores[target],
                    result_callback=bound_writer,
                    control_sink=control_sink,
                    lane_id=str(target),
                    result_finalizer=finalize,
                )
                lane_shards.append(shard)
            self.shards[target] = lane_shards
            
            # Create dispatcher for this lane
            if gov:
                self.dispatchers[target] = LaneDispatcher(
                    target=target,
                    plugin=plugin,
                    governance=gov,
                    shards=lane_shards,
                    shard_count=shard_count,
                    control_sink=control_sink,
                    gap_sink=gap_sink,
                )

    def start_all(self):
        for shard_list in self.shards.values():
            for shard in shard_list:
                shard.start()
        for dispatcher in self.dispatchers.values():
            dispatcher.start()
                
    async def stop_all(self):
        for dispatcher in self.dispatchers.values():
            await dispatcher.stop()
        for shard_list in self.shards.values():
            for shard in shard_list:
                await shard.stop()

    async def ingest_observation(self, observation: NetworkObservation):
        plan = self.router.plan(observation)
        await self._emit_router_predicate_errors(observation, plan)
        for target in plan.selected_targets:
            registry.routed_rate.labels(
                lane=str(target), observation_type=observation.observation_type.value
            ).inc()
            dispatcher = self.dispatchers.get(target)
            if not dispatcher:
                continue
            
            try:
                dispatcher.put_nowait(observation)
            except asyncio.QueueFull:
                await dispatcher.handle_ingress_saturation(observation)
        return plan

    async def _emit_router_predicate_errors(self, observation, plan) -> None:
        if self.control_sink is None:
            return
        for decision in plan.decisions:
            if decision.predicate_exception_type is None:
                continue
            event = RuntimeControlEvent(
                control_event_id=str(uuid.uuid4()), schema_version="1.0",
                control_type=ControlType.ERROR, ingest_time=datetime.now(timezone.utc),
                event_time=observation.event_time, source_id=observation.source_id,
                lane_id=str(decision.target), provenance_ref=observation.provenance_ref,
                quality_ref=observation.quality_ref,
                typed_payload={
                    "component": "router", "lane": str(decision.target),
                    "plugin_id": self.router.plugin_id_for(decision.target),
                    "observation_id": observation.observation_id,
                    "exception_type": decision.predicate_exception_type,
                    "error": decision.predicate_error,
                },
            )
            try:
                await self.control_sink(event)
            except Exception:
                # Diagnostic delivery must not interfere with unrelated routing.
                logger.exception(
                    "Router control sink failed for event %s; event will not be retried",
                    event.control_event_id,
                )

    async def advance_watermark(self, target: LaneTarget, watermark) -> bool:
        """Advance one lane's explicit event-time boundary."""
        dispatcher = self.dispatchers.get(target)
        if dispatcher is None:
            raise KeyError(f"unknown lane: {target}")
        return await dispatcher.advance_watermark(watermark)
