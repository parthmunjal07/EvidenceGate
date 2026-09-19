import asyncio
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
from evidencegate.results.types import ResultDraft

class RuntimeSupervisor:
    """
    Wires the pipeline:
    Router -> Queue -> Ingest Admission -> State Key -> Shards -> Plugin -> Validator -> SQLite
    """
    def __init__(
        self,
        plugins: Dict[LaneTarget, AnalyticPlugin],
        governances: Dict[LaneTarget, LaneGovernance],
        result_writer: Callable[[ResultDraft, LaneTarget], Awaitable[None]],
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
            target: StateStore() for target in plugins.keys()
        }
        
        self.shards: Dict[LaneTarget, list[LaneShard]] = {}
        self.dispatchers: Dict[LaneTarget, LaneDispatcher] = {}
        for target, plugin in plugins.items():
            lane_shards = []
            for i in range(shard_count):
                async def bound_writer(res: ResultDraft, t=target):
                    await self.result_writer(res, t)
                
                shard = LaneShard(
                    shard_id=i,
                    plugin=plugin,
                    state_store=self.state_stores[target],
                    result_callback=bound_writer,
                    control_sink=control_sink,
                    lane_id=str(target),
                )
                lane_shards.append(shard)
            self.shards[target] = lane_shards
            
            # Create dispatcher for this lane
            gov = self.governances.get(target)
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
        relevant_targets = self.router.route(observation)
        for target in relevant_targets:
            dispatcher = self.dispatchers.get(target)
            if not dispatcher:
                continue
            
            try:
                dispatcher.put_nowait(observation)
            except asyncio.QueueFull:
                await dispatcher.handle_ingress_saturation(observation)
