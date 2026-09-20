"""Conservative, stateless base class for M6 provider integration shells."""
from datetime import datetime
from typing import Any, Mapping, Optional, Sequence

from evidencegate.domain.enums import (
    AnalyticFamily, AvailabilityBasis, CapabilityState, Finality, GapAction,
    IntegrationStatus, ObservationType, OfficialPsCategory, ResultType,
    VisibilityCapability,
)
from evidencegate.domain.events import NetworkObservation
from evidencegate.domain.quality import QualityGap
from evidencegate.registry.manifest import PluginManifest
from evidencegate.registry.plugin import (
    AnalyticPlugin, PluginProcessOutcome, PluginStateSnapshot, StateKey,
)
from evidencegate.results.types import ResultDraft


class ProviderShellPlugin(AnalyticPlugin):
    """A structural route participant; it deliberately performs no analytics."""

    plugin_id: str
    category: OfficialPsCategory
    family: AnalyticFamily
    taxonomy: tuple[str, str, str]
    accepted_types: tuple[ObservationType, ...]
    capabilities_by_type: Mapping[ObservationType, frozenset[VisibilityCapability]]

    def manifest(self) -> PluginManifest:
        return PluginManifest(
            plugin_id=self.plugin_id, plugin_version="0.1.0", analytic_version="shell-0.1.0",
            taxonomy=self.taxonomy, accepted_observation_types=self.accepted_types,
            routing_predicate_version="structural-1", admission_requirements=(),
            required_fields=(), required_observation_contracts=(),
            required_visibility_capabilities=frozenset(), required_quality=(),
            allowed_finality=tuple(Finality), allowed_availability_basis=tuple(AvailabilityBasis),
            state_key_declaration=None, scientific_history_duration=None,
            resource_retention_duration=None, gap_action=GapAction.CONTINUE_WITH_QUALITY_FLAG,
            allowed_result_types=(ResultType.QUALITY_DEGRADED, ResultType.PLUGIN_STATUS),
            integration_status=IntegrationStatus.RUNTIME_SCAFFOLD_READY,
            profiling_hooks_enabled=False, governing_claim_ids=(), governing_decision_ids=(),
            official_ps_category=self.category, analytic_family=self.family,
        )

    def route(self, observation: NetworkObservation) -> bool:
        required = self.capabilities_by_type.get(observation.observation_type)
        return required is not None and any(
            observation.visibility.state(capability) is CapabilityState.AVAILABLE
            for capability in required
        )

    def state_key(self, observation: NetworkObservation) -> Optional[StateKey]:
        return None

    async def process(self, observation: NetworkObservation, context: Any,
                      state: PluginStateSnapshot | None) -> PluginProcessOutcome:
        return PluginProcessOutcome()

    async def on_quality_gap(self, gap: QualityGap, context: Any, state: Any) -> Sequence[ResultDraft]:
        return ()

    async def on_watermark(self, watermark: datetime, context: Any) -> PluginProcessOutcome:
        return PluginProcessOutcome()

    async def on_expire(self, key: StateKey, context: Any,
                        state: PluginStateSnapshot) -> PluginProcessOutcome:
        return PluginProcessOutcome()
