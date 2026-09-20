from dataclasses import dataclass
from evidencegate.domain.enums import (
    AvailabilityBasis, Finality, GapAction, IntegrationStatus, ObservationType,
    ResultType, VisibilityCapability,
)
from evidencegate.domain.quality import QualityRequirement

@dataclass(frozen=True, slots=True)
class PluginManifest:
    plugin_id: str
    plugin_version: str
    analytic_version: str
    
    taxonomy: tuple[str, str, str]
    accepted_observation_types: tuple[ObservationType, ...]
    routing_predicate_version: str
    
    admission_requirements: tuple[str, ...]
    required_fields: tuple[str, ...]
    required_observation_contracts: tuple[str, ...]
    required_visibility_capabilities: frozenset[VisibilityCapability]
    required_quality: tuple[QualityRequirement, ...]
    allowed_finality: tuple[Finality, ...]
    allowed_availability_basis: tuple[AvailabilityBasis, ...]
    state_key_declaration: str | None
    scientific_history_duration: str | None
    resource_retention_duration: str | None
    
    gap_action: GapAction
    allowed_result_types: tuple[ResultType, ...]
    integration_status: IntegrationStatus
    
    profiling_hooks_enabled: bool
    governing_claim_ids: tuple[str, ...]
    governing_decision_ids: tuple[str, ...]
