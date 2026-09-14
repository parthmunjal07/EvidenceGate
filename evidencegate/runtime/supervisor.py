import asyncio
from typing import Dict, Awaitable, Callable
from evidencegate.registry.plugin import AnalyticPlugin
from evidencegate.registry.manifest import PluginManifest
from evidencegate.domain.events import NetworkObservation
from evidencegate.domain.governance import LaneGovernance
from evidencegate.routing.router import RelevanceRouter, LaneTarget
from evidencegate.admission.evaluator import AdmissionEvaluator
from evidencegate.runtime.state import StateStore
from evidencegate.runtime.shard import LaneShard, compute_shard
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
        shard_count: int = 4
    ):
        self.plugins = plugins
        self.governances = governances
        self.result_writer = result_writer
        self.shard_count = shard_count
        
        self.router = RelevanceRouter(plugins)
        self.state_stores: Dict[LaneTarget, StateStore] = {
            target: StateStore() for target in plugins.keys()
        }
        
        self.shards: Dict[LaneTarget, list[LaneShard]] = {}
        for target, plugin in plugins.items():
            lane_shards = []
            for i in range(shard_count):
                async def bound_writer(res: ResultDraft, t=target):
                    await self.result_writer(res, t)
                
                shard = LaneShard(
                    shard_id=i,
                    plugin=plugin,
                    state_store=self.state_stores[target],
                    result_callback=bound_writer
                )
                lane_shards.append(shard)
            self.shards[target] = lane_shards

    def start_all(self):
        for shard_list in self.shards.values():
            for shard in shard_list:
                shard.start()
                
    async def stop_all(self):
        for shard_list in self.shards.values():
            for shard in shard_list:
                await shard.stop()

    async def ingest_observation(self, observation: NetworkObservation):
        relevant_targets = self.router.route(observation)
        for target in relevant_targets:
            plugin = self.plugins[target]
            manifest = plugin.manifest()
            governance = self.governances.get(target)
            if not governance:
                continue # Skip if no governance config exists for this lane
                
            decision = AdmissionEvaluator.evaluate(observation, manifest, governance)
            if not decision.admitted:
                # Based on user visibility config, we might yield a Reason result here.
                # In MVP, if rejected, it stops here for this lane unless emitting a diagnostic.
                continue
            
            state_key = plugin.state_key(observation)
            shard_idx = compute_shard(manifest.plugin_id, state_key, self.shard_count)
            
            # Put to the bounded queue for backpressured FIFO consumption
            target_shard = self.shards[target][shard_idx]
            await target_shard.put(observation)
