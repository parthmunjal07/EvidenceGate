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
    confidence: float = 0.0
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
    result_type: ResultType
    entity_reference: str
    evidence_items: tuple[str, ...]
    missing_prerequisites: tuple[str, ...]
    evidence_interval: Optional[tuple[datetime, datetime]] = None
    reason_code: Optional[ReasonCode] = None
    confidence: Optional[str] = None
    severity: Optional[str] = None
    linked_result_ids: tuple[str, ...] = field(default_factory=tuple)
