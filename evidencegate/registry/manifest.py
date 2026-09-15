from dataclasses import dataclass, field
from typing import Sequence
from evidencegate.domain.enums import ObservationType, GapAction, ResultType, IntegrationStatus

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
    minimum_quality: str | None
    minimum_visibility: str | None
    allowed_finality: tuple[bool, ...]
    allowed_availability_basis: tuple[str, ...]
    state_key_declaration: str | None
    scientific_history_duration: str | None
    resource_retention_duration: str | None
    
    gap_action: GapAction
    allowed_result_types: tuple[ResultType, ...]
    integration_status: IntegrationStatus
    
    profiling_hooks_enabled: bool
    governing_claim_ids: tuple[str, ...]
    governing_decision_ids: tuple[str, ...]
