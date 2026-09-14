from dataclasses import dataclass, field
from datetime import datetime
from typing import Sequence, Any, Optional
from evidencegate.domain.enums import ResultType, AnalyticUnavailableReason


@dataclass(frozen=True, slots=True)
class Result:
    result_id: str
    result_type: ResultType
    created_time: datetime
    entity_reference: str
    plugin_version: str
    analytic_version: str
    status_snapshot: dict[str, Any]
    claim_ceiling: str
    evidence_items: tuple[str, ...]
    missing_prerequisites: tuple[str, ...]
    governing_ids: tuple[str, ...]

    taxonomy: tuple[str, str, str] | None = None
    quality_ref: str | None = None
    provenance_ref: str | None = None
    evidence_interval: tuple[datetime, datetime] | None = None


@dataclass(frozen=True, slots=True)
class ThreatAlert(Result):
    # confidence must be explicitly supplied; no default — prevents accidentally emitting
    # a zero-confidence alert. Per IC-08 scaffolds cannot persist ThreatAlert at all.
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
    """
    Mutable-ish staging object that a plugin returns before the runtime
    promotes it to a persisted, immutable Result.  Uses AnalyticUnavailableReason
    for the reason_code field (previously referenced an undefined 'ReasonCode').
    """
    result_type: ResultType
    entity_reference: str
    evidence_items: tuple[str, ...]
    missing_prerequisites: tuple[str, ...]
    evidence_interval: Optional[tuple[datetime, datetime]] = None
    reason_code: Optional[AnalyticUnavailableReason] = None
    confidence: Optional[str] = None
    severity: Optional[str] = None
    linked_result_ids: tuple[str, ...] = field(default_factory=tuple)


# Union alias used throughout the runtime
Result_T = (
    ThreatAlert | ReviewFinding | AnalyticUnavailable | PrerequisiteMissing
    | InsufficientEvidence | QualityDegraded | PluginStatus | CorrelationFinding
)
