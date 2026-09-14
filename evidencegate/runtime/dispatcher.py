import asyncio
from typing import Dict, List
from evidencegate.registry.plugin import AnalyticPlugin
from evidencegate.domain.events import NetworkObservation
from evidencegate.domain.governance import LaneGovernance
from evidencegate.admission.evaluator import AdmissionEvaluator
from evidencegate.runtime.shard import LaneShard, compute_shard
from evidencegate.routing.router import LaneTarget

class LaneDispatcher:
    """
    Reads from bounded lane ingress queue -> ingest admission -> state key calc -> shard dispatch
    """
    def __init__(
        self,
        target: LaneTarget,
        plugin: AnalyticPlugin,
        governance: LaneGovernance,
        shards: List[LaneShard],
        shard_count: int,
        max_size: int = 2000
    ):
        self.target = target
        self.plugin = plugin
        self.governance = governance
        self.shards = shards
        self.shard_count = shard_count
        self.queue: asyncio.Queue[NetworkObservation] = asyncio.Queue(maxsize=max_size)
        self._task: asyncio.Task | None = None
        
    def start(self):
        if self._task is None:
            self._task = asyncio.create_task(self._consume())
            
    async def stop(self):
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
                
    def put_nowait(self, observation: NetworkObservation):
        self.queue.put_nowait(observation)
        
    async def _consume(self):
        while True:
            observation = await self.queue.get()
            try:
                manifest = self.plugin.manifest()
                
                decision = AdmissionEvaluator.evaluate(observation, manifest, self.governance)
                if not decision.admitted:
                    # In MVP, rejected observations stop here (unless configured to emit a diagnostic result)
                    continue
                
                state_key = self.plugin.state_key(observation)
                shard_idx = compute_shard(manifest.plugin_id, state_key, self.shard_count)
                
                target_shard = self.shards[shard_idx]
                try:
                    target_shard.put_nowait(observation)
                except asyncio.QueueFull:
                    # Queue saturation -> health gap
                    from evidencegate.domain.quality import QualityGap
                    import uuid
                    gap = QualityGap(
                        gap_id=str(uuid.uuid4()),
                        scope=self.target,
                        first_known_event_time=observation.event_time,
                        last_known_event_time=observation.event_time,
                        detection_time=observation.ingest_time,
                        count=1,
                        gap_types=("QUEUE_SATURATION",),
                        reason="Shard queue full"
                    )
                    pass
            except Exception as e:
                pass
            finally:
                self.queue.task_done()
