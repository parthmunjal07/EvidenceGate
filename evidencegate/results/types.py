"""Immutable result contracts and plugin-owned result drafts."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from evidencegate.domain.enums import (
    AnalyticUnavailableReason,
    EvidenceReadiness,
    IntegrationStatus,
    ResultType,
    ScientificStatus,
)


@dataclass(frozen=True, slots=True)
class ResultStatusSnapshot:
    """Runtime-known governance and operational facts at result emission."""

    scientific_status: ScientificStatus
    integration_status: IntegrationStatus
    governance_version: str
    readiness: EvidenceReadiness
    quality_degraded: bool


@dataclass(frozen=True, slots=True)
class Result:
    """Runtime-finalized, immutable scientific result."""

    result_id: str
    schema_version: str
    result_type: ResultType
    created_time: datetime
    lane_id: str
    plugin_id: str
    plugin_version: str
    analytic_version: str
    governance_version: str
    entity_reference: str
    taxonomy: tuple[str, str, str]
    status_snapshot: ResultStatusSnapshot
    claim_ceiling: str
    evidence_items: tuple[str, ...]
    missing_prerequisites: tuple[str, ...]
    governing_ids: tuple[str, ...]
    quality_refs: tuple[str, ...]
    provenance_refs: tuple[str, ...]
    evidence_interval: tuple[datetime, datetime] | None = None

    # M5-01 leaves persistence v1 untouched. These compatibility views let
    # the existing writer consume a final result until M5-02.
    @property
    def quality_ref(self) -> str | None:
        return self.quality_refs[0] if self.quality_refs else None

    @property
    def provenance_ref(self) -> str | None:
        return self.provenance_refs[0] if self.provenance_refs else None


@dataclass(frozen=True, slots=True)
class ThreatAlert(Result):
    confidence: str | None = None
    severity: str | None = None


@dataclass(frozen=True, slots=True)
class AnalyticUnavailable(Result):
    reason_code: AnalyticUnavailableReason = AnalyticUnavailableReason.SCIENTIFIC_NOT_READY


@dataclass(frozen=True, slots=True)
class ReviewFinding(Result):
    pass


@dataclass(frozen=True, slots=True)
class PrerequisiteMissing(Result):
    pass


@dataclass(frozen=True, slots=True)
class InsufficientEvidence(Result):
    pass


@dataclass(frozen=True, slots=True)
class QualityDegraded(Result):
    pass


@dataclass(frozen=True, slots=True)
class PluginStatus(Result):
    pass


@dataclass(frozen=True, slots=True)
class CorrelationFinding(Result):
    linked_result_ids: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class ResultDraft:
    """Small plugin-owned request for runtime result finalization."""

    result_type: ResultType
    entity_reference: str
    evidence_items: tuple[str, ...]
    missing_prerequisites: tuple[str, ...]
    evidence_interval: Optional[tuple[datetime, datetime]] = None
    reason_code: Optional[AnalyticUnavailableReason] = None
    confidence: Optional[str] = None
    severity: Optional[str] = None
    linked_result_ids: tuple[str, ...] = field(default_factory=tuple)


Result_T = (
    ThreatAlert | ReviewFinding | AnalyticUnavailable | PrerequisiteMissing
    | InsufficientEvidence | QualityDegraded | PluginStatus | CorrelationFinding
)
