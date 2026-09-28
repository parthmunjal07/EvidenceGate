import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Awaitable, Callable, Mapping
from evidencegate.registry.plugin import AnalyticPlugin
from evidencegate.domain.events import NetworkObservation, RuntimeControlEvent
from evidencegate.domain.governance import LaneGovernance
from evidencegate.domain.quality import QualityGap
from evidencegate.routing.router import RelevanceRouter, LaneTarget
from evidencegate.runtime.state import StateStore
from evidencegate.runtime.shard import LaneShard
from evidencegate.runtime.trace import emit_trace
from evidencegate.runtime.dispatcher import EventTimeReorderPolicy, LaneDispatcher
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
        reorder_policies: Mapping[LaneTarget, EventTimeReorderPolicy] | None = None,
        trace_sink: Callable[..., None] | None = None,
    ):
        self.plugins = plugins
        self.governances = governances
        self.result_writer = result_writer
        self.shard_count = shard_count
        self.control_sink = control_sink
        self.gap_sink = gap_sink
        self.reorder_policies = dict(reorder_policies or {})
        self.trace_sink = trace_sink

        for target, plugin in plugins.items():
            if (
                plugin.manifest().state_resource_policy is not None
                and target not in self.reorder_policies
            ):
                raise ValueError(
                    f"stateful lane {target} requires an explicit event-time reorder policy"
                )

        self.router = RelevanceRouter(plugins)
        self.state_stores: Dict[LaneTarget, StateStore] = {
            # Explicit lane watermarks, not observation timestamps, own expiry.
            # The manifest limit is an engineering bound, never a scientific window.
            target: StateStore(
                max_entries=(
                    plugin.manifest().state_resource_policy.max_entries
                    if plugin.manifest().state_resource_policy is not None
                    else StateStore.DEFAULT_MAX_ENTRIES
                ),
                expire_on_access=False,
            )
            for target, plugin in plugins.items()
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
                    draft,
                    context: ResultEmissionContext,
                    m=manifest,
                    g=gov,
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
                    trace_sink=trace_sink,
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
                    reorder_policy=self.reorder_policies.get(target),
                    trace_sink=trace_sink,
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
        if self.trace_sink is not None:
            from evidencegate.api.observation_presentation import project_observation

            try:
                canonical_presentation = project_observation(observation)
            except Exception:
                # UI projection is best effort; it must not change routing or evaluation.
                canonical_presentation = None
            emit_trace(
                self.trace_sink,
                "OBSERVATION_CREATED",
                observation_id=observation.observation_id,
                observation_type=observation.observation_type.value,
                canonical_observation=canonical_presentation,
            )
            visibility_parts = []
            for state_name, capabilities in (
                ("available", observation.visibility.available),
                ("unavailable", observation.visibility.unavailable),
                ("degraded", observation.visibility.degraded),
            ):
                if capabilities:
                    visibility_parts.append(
                        f"{state_name}: {', '.join(sorted(item.value for item in capabilities))}"
                    )
            quality_parts = [
                f"{name}: {value.value}"
                for name, value in (
                    ("packet loss", observation.quality.packet_loss),
                    ("sampling", observation.quality.sampling),
                    ("parser", observation.quality.parser),
                    ("capture gap", observation.quality.capture_gap),
                )
            ]
            visibility_reason = "; ".join(
                (
                    ", ".join(visibility_parts)
                    if visibility_parts
                    else "visibility capabilities unknown",
                    "quality " + ", ".join(quality_parts),
                )
            )
            emit_trace(
                self.trace_sink,
                "VISIBILITY_EVALUATED",
                observation_id=observation.observation_id,
                observation_type=observation.observation_type.value,
                reason=visibility_reason,
            )
        plan = self.router.plan(observation)
        if self.trace_sink is not None:
            for decision in plan.decisions:
                if decision.selected:
                    plugin = self.plugins[decision.target]
                    emit_trace(
                        self.trace_sink,
                        "ROUTED",
                        observation_id=observation.observation_id,
                        observation_type=observation.observation_type.value,
                        lane_id=str(decision.target),
                        mechanism=plugin.manifest().mechanism_id,
                    )
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
                control_event_id=str(uuid.uuid4()),
                schema_version="1.0",
                control_type=ControlType.ERROR,
                ingest_time=datetime.now(timezone.utc),
                event_time=observation.event_time,
                source_id=observation.source_id,
                lane_id=str(decision.target),
                provenance_ref=observation.provenance_ref,
                quality_ref=observation.quality_ref,
                typed_payload={
                    "component": "router",
                    "lane": str(decision.target),
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
