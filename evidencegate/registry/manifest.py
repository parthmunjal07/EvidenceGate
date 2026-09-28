from dataclasses import dataclass
from datetime import timedelta
from evidencegate.domain.enums import (
    AvailabilityBasis,
    Finality,
    GapAction,
    IntegrationStatus,
    ObservationType,
    ResultType,
    VisibilityCapability,
    OfficialPsCategory,
    AnalyticFamily,
)
from evidencegate.domain.quality import QualityRequirement


@dataclass(frozen=True, slots=True)
class StateResourcePolicy:
    """Runtime resource limits, deliberately separate from mechanism science."""

    max_entries: int
    max_ttl: timedelta

    def __post_init__(self) -> None:
        if isinstance(self.max_entries, bool) or not isinstance(self.max_entries, int):
            raise TypeError("max_entries must be a non-bool integer")
        if self.max_entries <= 0:
            raise ValueError("max_entries must be greater than zero")
        if not isinstance(self.max_ttl, timedelta):
            raise TypeError("max_ttl must be a timedelta")
        if self.max_ttl <= timedelta(0):
            raise ValueError("max_ttl must be positive")


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
    # Shells that emit no results may omit this; finalization requires it.
    official_ps_category: OfficialPsCategory | None = None
    analytic_family: AnalyticFamily | None = None
    mechanism_id: str | None = None
    # Engineering capacity/retention limits; never a scientific window.
    state_resource_policy: StateResourcePolicy | None = None
    # Immutable runtime-owned configuration provenance for result finalization.
    config_hash: str | None = None

    def __post_init__(self) -> None:
        if self.config_hash is not None and (
            not isinstance(self.config_hash, str) or not self.config_hash.strip()
        ):
            raise ValueError("config_hash must be a non-empty string or None")
