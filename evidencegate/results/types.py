"""Immutable result contracts and plugin-owned result drafts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json
import math
from typing import Optional

from evidencegate.domain.enums import (
    AnalyticUnavailableReason,
    EvidenceReadiness,
    IntegrationStatus,
    ResultType,
    ScientificStatus,
)
from evidencegate.domain.events import VisibilityProfile
from evidencegate.domain.quality import EvidenceQuality


def _canonical_evidence_value(value: object) -> object:
    """Return a JSON-compatible value without stringifying unknown objects."""
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("evidence numeric values must be finite")
        return value
    if isinstance(value, Enum):
        return _canonical_evidence_value(value.value)
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("evidence datetimes must be timezone-aware")
        return value.astimezone(timezone.utc).isoformat(timespec="microseconds")
    if isinstance(value, (list, tuple)):
        return [_canonical_evidence_value(item) for item in value]
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("evidence object keys must be strings")
        return {key: _canonical_evidence_value(item) for key, item in value.items()}
    raise TypeError(f"unsupported evidence value: {type(value).__name__}")


@dataclass(frozen=True, slots=True)
class EvidencePayload:
    """Deeply immutable, canonical structured mechanism evidence."""

    canonical_json: str

    def __post_init__(self) -> None:
        try:
            value = json.loads(self.canonical_json)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("evidence payload must contain canonical JSON") from exc
        if not isinstance(value, dict):
            raise ValueError("evidence payload root must be an object")
        canonical = self._dump(value)
        if canonical != self.canonical_json:
            raise ValueError("evidence payload JSON is not canonical")

    @classmethod
    def from_value(cls, value: object) -> "EvidencePayload":
        if isinstance(value, cls):
            return value
        canonical_value = _canonical_evidence_value(value)
        if not isinstance(canonical_value, dict):
            raise TypeError("evidence payload root must be an object")
        return cls(cls._dump(canonical_value))

    @staticmethod
    def _dump(value: object) -> str:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )

    def to_value(self) -> dict[str, object]:
        """Return a detached mutable view; the stored payload stays immutable."""
        value = json.loads(self.canonical_json)
        if not isinstance(value, dict):  # Defensive against manually forged data.
            raise ValueError("evidence payload root must be an object")
        return value


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
    mechanism_id: str | None = None
    evidence: EvidencePayload = field(default_factory=lambda: EvidencePayload("{}"))
    source_observation_ids: tuple[str, ...] = field(default_factory=tuple)
    source_ids: tuple[str, ...] = field(default_factory=tuple)
    quality_snapshot: EvidenceQuality = field(default_factory=EvidenceQuality)
    visibility_snapshot: VisibilityProfile = field(default_factory=VisibilityProfile)
    state_version: int | None = None
    config_hash: str | None = None
    parser_refs: tuple[str, ...] = field(default_factory=tuple)
    model_refs: tuple[str, ...] = field(default_factory=tuple)


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
    evidence: object = field(default_factory=dict)
    source_observation_ids: tuple[str, ...] = field(default_factory=tuple)


Result_T = (
    ThreatAlert
    | ReviewFinding
    | AnalyticUnavailable
    | PrerequisiteMissing
    | InsufficientEvidence
    | QualityDegraded
    | PluginStatus
    | CorrelationFinding
)
