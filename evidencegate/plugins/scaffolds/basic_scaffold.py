from typing import Sequence, Any, Optional
import uuid
from datetime import datetime
from evidencegate.registry.plugin import AnalyticPlugin, StateKey
from evidencegate.registry.manifest import PluginManifest
from evidencegate.domain.events import NetworkObservation
from evidencegate.domain.enums import ObservationType, GapAction, ResultType, IntegrationStatus
from evidencegate.domain.quality import QualityGap
from evidencegate.results.types import ResultDraft

class BasicScaffoldPlugin(AnalyticPlugin):
    """
    A scaffold plugin that implements the contract but does not implement any actual science.
    Validates IC-08 (no ThreatAlert from a scaffold).
    """
    def manifest(self) -> PluginManifest:
        return PluginManifest(
            plugin_id="scaffold_01",
            plugin_version="0.1.0",
            analytic_version="0.1.0",
            taxonomy=("Test", "Scaffold", "Basic"),
            accepted_observation_types=(ObservationType.PACKET, ObservationType.FLOW),
            routing_predicate_version="1.0",
            admission_requirements=("some_field",),
            state_key_declaration="source_address",
            scientific_history_duration=None,
            resource_retention_duration="1h",
            gap_action=GapAction.CONTINUE_WITH_QUALITY_FLAG,
            allowed_result_types=(ResultType.REVIEW_FINDING, ResultType.ANALYTIC_UNAVAILABLE),
            integration_status=IntegrationStatus.RUNTIME_SCAFFOLD_READY,
            profiling_hooks_enabled=False,
            governing_claim_ids=(),
            governing_decision_ids=()
        )
        
    def route(self, observation: NetworkObservation) -> bool:
        # Accept anything it's configured for
        return True
        
    def state_key(self, observation: NetworkObservation) -> Optional[StateKey]:
        return StateKey("test_key")
        
    async def process(self, observation: NetworkObservation, context: Any, state: Any) -> Sequence[ResultDraft]:
        # Emits a review finding, validating it doesn't emit a ThreatAlert
        return [
            ResultDraft(
                result_type=ResultType.REVIEW_FINDING,
                entity_reference="test_entity",
                evidence_items=(observation.observation_id,),
                missing_prerequisites=()
            )
        ]
        
    async def on_quality_gap(self, gap: QualityGap, context: Any, state: Any) -> Sequence[ResultDraft]:
        return []
        
    async def on_watermark(self, watermark: Any, context: Any, state: Any) -> Sequence[ResultDraft]:
        return []
        
    async def on_expire(self, key: StateKey, context: Any, state: Any) -> Sequence[ResultDraft]:
        return []
