from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Sequence
from evidencegate.domain.enums import ResultType, ReasonCode

@dataclass(frozen=True, slots=True)
class BaseResult:
    result_id: str
    result_type: ResultType
    created_time: datetime
    entity_reference: str
    taxonomy: tuple[str, str, str]
    plugin_version: str
    analytic_version: str
    status_snapshot: dict[str, str]
    claim_ceiling: str
    quality_ref: str
    provenance_ref: str
    evidence_items: tuple[str, ...]
    missing_prerequisites: tuple[str, ...]
    governing_ids: tuple[str, ...]
    evidence_interval: Optional[tuple[datetime, datetime]] = None

@dataclass(frozen=True, slots=True)
class ThreatAlert(BaseResult):
    confidence: Optional[str] = None
    severity: Optional[str] = None

@dataclass(frozen=True, slots=True)
class ReviewFinding(BaseResult):
    pass

@dataclass(frozen=True, slots=True)
class AnalyticUnavailable(BaseResult):
    reason_code: ReasonCode = ReasonCode.SCIENTIFIC_NOT_READY

@dataclass(frozen=True, slots=True)
class PrerequisiteMissing(BaseResult):
    pass

@dataclass(frozen=True, slots=True)
class InsufficientEvidence(BaseResult):
    pass

@dataclass(frozen=True, slots=True)
class QualityDegraded(BaseResult):
    pass

@dataclass(frozen=True, slots=True)
class PluginStatus(BaseResult):
    pass

@dataclass(frozen=True, slots=True)
class CorrelationFinding(BaseResult):
    linked_result_ids: tuple[str, ...] = field(default_factory=tuple)

Result = (
    ThreatAlert | ReviewFinding | AnalyticUnavailable | PrerequisiteMissing |
    InsufficientEvidence | QualityDegraded | PluginStatus | CorrelationFinding
)

# A ResultDraft is what a plugin yields before validation/enrichment
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
