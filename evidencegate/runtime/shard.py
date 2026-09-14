import asyncio
import hashlib
from typing import Callable, Awaitable
from evidencegate.registry.plugin import AnalyticPlugin, StateKey
from evidencegate.domain.events import NetworkObservation
from evidencegate.runtime.state import StateStore
from evidencegate.results.types import ResultDraft

class LaneShard:
    """
    FIFO Shard for deterministic per-key processing.
    """
    def __init__(
        self, 
        shard_id: int, 
        plugin: AnalyticPlugin, 
        state_store: StateStore,
        result_callback: Callable[[ResultDraft], Awaitable[None]],
        max_size: int = 1000
    ):
        self.shard_id = shard_id
        self.plugin = plugin
        self.state_store = state_store
        self.result_callback = result_callback
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
            
    async def put(self, observation: NetworkObservation):
        await self.queue.put(observation)
        
    def put_nowait(self, observation: NetworkObservation):
        self.queue.put_nowait(observation)

    async def _consume(self):
        while True:
            observation = await self.queue.get()
            try:
                state_key = self.plugin.state_key(observation)
                state = None
                if state_key:
                    state = self.state_store.get(state_key)
                
                # Evaluation Readiness logic (Warmup, etc.) is handled inside process, or wrapped here
                # We assume state mutation happens inside process for now.
                context = {} # Future: context injection
                results = await self.plugin.process(observation, context, state)
                
                for res in results:
                    await self.result_callback(res)
                    
            except Exception as e:
                # In a real implementation we would emit a control event or error result
                pass
            finally:
                self.queue.task_done()

def compute_shard(plugin_id: str, state_key: StateKey | None, shard_count: int) -> int:
    if state_key is None:
        return 0
    raw = f"{plugin_id}||{state_key}".encode("utf-8")
    hash_val = int(hashlib.sha256(raw).hexdigest(), 16)
    return hash_val % shard_count
