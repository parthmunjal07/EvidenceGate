"""CAT6-EX-M1: factual directional transfer-magnitude measurement."""
from datetime import datetime
from typing import Any, Sequence

from evidencegate.domain.enums import (
    AnalyticFamily, AvailabilityBasis, CapabilityState, Finality, GapAction,
    IntegrationStatus, ObservationType, OfficialPsCategory, ResultType,
    VisibilityCapability,
)
from evidencegate.domain.events import NetworkObservation
from evidencegate.domain.quality import QualityGap
from evidencegate.registry.manifest import PluginManifest
from evidencegate.registry.plugin import PluginProcessOutcome, PluginStateSnapshot, StateKey
from evidencegate.results.types import ResultDraft
from .common import ProviderShellPlugin


class UnusualTransferShellPlugin(ProviderShellPlugin):
    """Unregistered compatibility shell retained for import compatibility."""
    plugin_id = "provider.unusual_transfer.shell"
    category = OfficialPsCategory.DATA_EXFILTRATION
    family = AnalyticFamily.UNUSUAL_TRANSFER
    taxonomy = ("Network", "Unusual Transfer", "Provider Shell")
    accepted_types = (ObservationType.PACKET, ObservationType.FLOW)
    capabilities_by_type = {ObservationType.PACKET: frozenset({VisibilityCapability.PACKET_FACTS}), ObservationType.FLOW: frozenset({VisibilityCapability.FLOW_FACTS})}


class ExfilM1TransferPlugin:
    """Measure exporter-declared C-to-S flow counters without interpreting risk."""
    _recognized = ("bytes_c2s", "packets_c2s", "bytes_s2c", "packets_s2c")
    _forward = ("bytes_c2s", "packets_c2s")
    _manifest = PluginManifest(
        plugin_id="provider.unusual_transfer.m1", plugin_version="0.1.0", analytic_version="cat6-ex-m1-0.1.0",
        taxonomy=("Network", "Data Exfiltration", "Transfer Magnitude Measurement"),
        accepted_observation_types=(ObservationType.FLOW,), routing_predicate_version="factual-directional-counters-1",
        admission_requirements=("FLOW_FACTS and observable client-to-server counter",),
        required_fields=("flow_id_basis", "endpoints", "protocol", "start_time", "end_time", "supplied_directional_counters", "exporter_semantics"),
        required_observation_contracts=(), required_visibility_capabilities=frozenset({VisibilityCapability.FLOW_FACTS}),
        required_quality=(), allowed_finality=tuple(Finality), allowed_availability_basis=tuple(AvailabilityBasis),
        state_key_declaration=None, scientific_history_duration=None, resource_retention_duration=None,
        gap_action=GapAction.CONTINUE_WITH_QUALITY_FLAG, allowed_result_types=(ResultType.REVIEW_FINDING,),
        integration_status=IntegrationStatus.BASELINE_IMPLEMENTED, profiling_hooks_enabled=False,
        governing_claim_ids=(), governing_decision_ids=(), official_ps_category=OfficialPsCategory.DATA_EXFILTRATION,
        analytic_family=AnalyticFamily.UNUSUAL_TRANSFER, mechanism_id="CAT6-EX-M1",
    )

    def manifest(self) -> PluginManifest:
        return self._manifest

    def route(self, observation: NetworkObservation) -> bool:
        if observation.observation_type is not ObservationType.FLOW:
            return False
        # Degraded directional facts remain observed; unavailable/unknown do not.
        if observation.visibility.state(VisibilityCapability.FORWARD_FACTS) not in (CapabilityState.AVAILABLE, CapabilityState.DEGRADED):
            return False
        return any(name in observation.typed_payload.supplied_directional_counters for name in self._forward)

    @staticmethod
    def _counter(name: str, counters: dict[str, int]) -> int | None:
        if name not in counters:
            return None
        value = counters[name]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{name} must be a non-boolean integer >= 0")
        return value

    def state_key(self, observation: NetworkObservation) -> None:
        return None

    async def process(self, observation: NetworkObservation, context: Any, state: PluginStateSnapshot | None) -> PluginProcessOutcome:
        payload = observation.typed_payload
        if not payload.exporter_semantics:
            raise ValueError("exporter_semantics must be non-empty")
        if payload.end_time < payload.start_time:
            raise ValueError("end_time cannot precede start_time")
        counters = {name: value for name in self._recognized if (value := self._counter(name, payload.supplied_directional_counters)) is not None}
        if not any(name in counters for name in self._forward):
            raise ValueError("CAT6-EX-M1 requires an observed client-to-server counter")
        duration = (payload.end_time - payload.start_time).total_seconds()
        evidence: dict[str, object] = {
            "evidence_kind": "TRANSFER_MAGNITUDE_MEASUREMENT", "flow_id_basis": payload.flow_id_basis,
            "protocol": payload.protocol, "exporter_semantics": payload.exporter_semantics,
            "start_time": payload.start_time, "end_time": payload.end_time, "duration_seconds": duration,
            "direction_scope": "CLIENT_TO_SERVER_MAGNITUDE", "recognized_directional_counters": counters,
        }
        if "endpoints" in observation.present_fields:
            evidence["endpoints_source_order"] = payload.endpoints
        if "sampling" in observation.present_fields:
            evidence["sampling"] = payload.sampling
        if "documented_end_state" in observation.present_fields:
            evidence["documented_end_state"] = payload.documented_end_state
        if duration > 0:
            for name, value in counters.items():
                evidence[f"{name}_per_second"] = value / duration
        return PluginProcessOutcome((ResultDraft(ResultType.REVIEW_FINDING, observation.observation_id, (), (), (payload.start_time, payload.end_time), evidence=evidence),))

    async def on_quality_gap(self, gap: QualityGap, context: Any, state: Any) -> Sequence[ResultDraft]:
        return ()

    async def on_watermark(self, watermark: datetime, context: Any) -> PluginProcessOutcome:
        return PluginProcessOutcome()

    async def on_expire(self, key: StateKey, context: Any, state: PluginStateSnapshot) -> PluginProcessOutcome:
        return PluginProcessOutcome()
