"""Pure runtime-owned promotion from ``ResultDraft`` to immutable ``Result``."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from evidencegate.domain.enums import EvidenceReadiness, ResultType
from evidencegate.domain.events import VisibilityProfile
from evidencegate.domain.governance import LaneGovernance
from evidencegate.domain.quality import EvidenceQuality
from evidencegate.registry.manifest import PluginManifest
from evidencegate.results.types import (
    AnalyticUnavailable,
    CorrelationFinding,
    EvidencePayload,
    InsufficientEvidence,
    PluginStatus,
    PrerequisiteMissing,
    QualityDegraded,
    Result,
    ResultDraft,
    ResultStatusSnapshot,
    Result_T,
    ReviewFinding,
    ThreatAlert,
)
from evidencegate.results.validator import ResultValidator


RESULT_SCHEMA_VERSION = "3.0"


@dataclass(frozen=True, slots=True)
class ResultEmissionContext:
    """Small immutable runtime context for one result emission.

    ``causal_result_time`` is included in the semantic identity. It is supplied
    by the observation or lifecycle event-time boundary, never wall-clock time.
    ``trigger_reference`` identifies the normal observation or lifecycle cause.
    """

    lane_id: str
    causal_result_time: datetime
    quality_refs: tuple[str, ...]
    provenance_refs: tuple[str, ...]
    readiness: EvidenceReadiness
    quality_degraded: bool
    trigger_reference: str | None = None
    source_observation_ids: tuple[str, ...] = ()
    source_ids: tuple[str, ...] = ()
    quality_snapshot: EvidenceQuality = EvidenceQuality()
    visibility_snapshot: VisibilityProfile = VisibilityProfile()
    state_version: int | None = None
    config_hash: str | None = None
    parser_refs: tuple[str, ...] = ()
    model_refs: tuple[str, ...] = ()


def _ordered_unique(values: tuple[str, ...]) -> tuple[str, ...]:
    """Deduplicate references without changing their first-seen order."""
    return tuple(dict.fromkeys(value for value in values if value))


def _canonical_value(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("result identity requires timezone-aware datetimes")
        return value.astimezone(timezone.utc).isoformat(timespec="microseconds")
    if isinstance(value, tuple):
        return [_canonical_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _canonical_value(item) for key, item in value.items()}
    return value


def canonical_result_content(result: Result) -> str:
    """Stable JSON for deterministic result identity; excludes ``result_id``."""
    content = {
        "schema_version": result.schema_version,
        "result_type": result.result_type,
        "created_time": result.created_time,
        "lane_id": result.lane_id,
        "plugin_id": result.plugin_id,
        "plugin_version": result.plugin_version,
        "analytic_version": result.analytic_version,
        "governance_version": result.governance_version,
        "entity_reference": result.entity_reference,
        "taxonomy": result.taxonomy,
        "status_snapshot": (
            result.status_snapshot.scientific_status,
            result.status_snapshot.integration_status,
            result.status_snapshot.governance_version,
            result.status_snapshot.readiness,
            result.status_snapshot.quality_degraded,
        ),
        "claim_ceiling": result.claim_ceiling,
        "evidence_items": result.evidence_items,
        "missing_prerequisites": result.missing_prerequisites,
        "governing_ids": result.governing_ids,
        "quality_refs": result.quality_refs,
        "provenance_refs": result.provenance_refs,
        "evidence_interval": result.evidence_interval,
    }
    if result.schema_version != "2.0":
        content.update(
            {
                "mechanism_id": result.mechanism_id,
                "evidence": result.evidence.to_value(),
                "source_observation_ids": result.source_observation_ids,
                "source_ids": result.source_ids,
                "quality_snapshot": {
                    "packet_loss": result.quality_snapshot.packet_loss,
                    "sampling": result.quality_snapshot.sampling,
                    "parser": result.quality_snapshot.parser,
                    "capture_gap": result.quality_snapshot.capture_gap,
                },
                "visibility_snapshot": {
                    "available": tuple(
                        sorted(result.visibility_snapshot.available, key=lambda item: item.value)
                    ),
                    "unavailable": tuple(
                        sorted(result.visibility_snapshot.unavailable, key=lambda item: item.value)
                    ),
                    "degraded": tuple(
                        sorted(result.visibility_snapshot.degraded, key=lambda item: item.value)
                    ),
                },
                "state_version": result.state_version,
                "config_hash": result.config_hash,
                "parser_refs": result.parser_refs,
                "model_refs": result.model_refs,
            }
        )
    if isinstance(result, ThreatAlert):
        content["confidence"] = result.confidence
        content["severity"] = result.severity
    elif isinstance(result, AnalyticUnavailable):
        content["reason_code"] = result.reason_code
    elif isinstance(result, CorrelationFinding):
        content["linked_result_ids"] = result.linked_result_ids
    return json.dumps(_canonical_value(content), sort_keys=True, separators=(",", ":"))


def result_id_for(result: Result) -> str:
    return "result:" + hashlib.sha256(canonical_result_content(result).encode("utf-8")).hexdigest()


class ResultFinalizer:
    """Construct and validate a final result without persistence side effects."""

    _result_classes: dict[ResultType, type[Result]] = {
        ResultType.THREAT_ALERT: ThreatAlert,
        ResultType.REVIEW_FINDING: ReviewFinding,
        ResultType.ANALYTIC_UNAVAILABLE: AnalyticUnavailable,
        ResultType.PREREQUISITE_MISSING: PrerequisiteMissing,
        ResultType.INSUFFICIENT_EVIDENCE: InsufficientEvidence,
        ResultType.QUALITY_DEGRADED: QualityDegraded,
        ResultType.PLUGIN_STATUS: PluginStatus,
        ResultType.CORRELATION_FINDING: CorrelationFinding,
    }

    @classmethod
    def finalize(
        cls,
        draft: ResultDraft,
        manifest: PluginManifest,
        governance: LaneGovernance,
        context: ResultEmissionContext,
    ) -> Result_T:
        if not isinstance(draft, ResultDraft):
            raise TypeError("result finalization requires a ResultDraft")
        if draft.result_type not in cls._result_classes:
            raise ValueError(f"unsupported result type: {draft.result_type!r}")
        if not manifest.mechanism_id or not manifest.mechanism_id.strip():
            raise ValueError("a result-emitting plugin requires a non-empty mechanism_id")
        if (
            context.causal_result_time.tzinfo is None
            or context.causal_result_time.utcoffset() is None
        ):
            raise ValueError("causal_result_time must be timezone-aware")
        if not isinstance(context.quality_snapshot, EvidenceQuality):
            raise TypeError("quality_snapshot must be EvidenceQuality")
        if not isinstance(context.visibility_snapshot, VisibilityProfile):
            raise TypeError("visibility_snapshot must be VisibilityProfile")
        if context.state_version is not None and (
            isinstance(context.state_version, bool)
            or not isinstance(context.state_version, int)
            or context.state_version < 1
        ):
            raise ValueError("state_version must be a positive integer or None")
        if context.config_hash is not None and (
            not isinstance(context.config_hash, str) or not context.config_hash.strip()
        ):
            raise ValueError("config_hash must be a non-empty string or None")
        if draft.result_type is not ResultType.THREAT_ALERT and (
            draft.confidence is not None or draft.severity is not None
        ):
            raise ValueError(
                f"Result type {draft.result_type.value} cannot carry confidence/severity."
            )
        if draft.result_type is not ResultType.CORRELATION_FINDING and draft.linked_result_ids:
            raise ValueError("linked_result_ids are only valid for CorrelationFinding")

        evidence_items = _ordered_unique(
            draft.evidence_items
            + ((context.trigger_reference,) if context.trigger_reference else ())
        )
        governing_ids = _ordered_unique(
            manifest.governing_claim_ids + manifest.governing_decision_ids
        )
        common = dict(
            result_id="",
            schema_version=RESULT_SCHEMA_VERSION,
            result_type=draft.result_type,
            created_time=context.causal_result_time,
            lane_id=context.lane_id,
            plugin_id=manifest.plugin_id,
            mechanism_id=manifest.mechanism_id,
            plugin_version=manifest.plugin_version,
            analytic_version=manifest.analytic_version,
            governance_version=governance.governance_version,
            entity_reference=draft.entity_reference,
            taxonomy=manifest.taxonomy,
            status_snapshot=ResultStatusSnapshot(
                scientific_status=governance.scientific_status,
                integration_status=manifest.integration_status,
                governance_version=governance.governance_version,
                readiness=context.readiness,
                quality_degraded=context.quality_degraded,
            ),
            claim_ceiling=governance.claim_ceiling,
            evidence_items=evidence_items,
            evidence=EvidencePayload.from_value(draft.evidence),
            missing_prerequisites=_ordered_unique(draft.missing_prerequisites),
            governing_ids=governing_ids,
            quality_refs=_ordered_unique(context.quality_refs),
            provenance_refs=_ordered_unique(context.provenance_refs),
            evidence_interval=draft.evidence_interval,
            source_observation_ids=_ordered_unique(
                context.source_observation_ids + draft.source_observation_ids
            ),
            source_ids=_ordered_unique(context.source_ids),
            quality_snapshot=context.quality_snapshot,
            visibility_snapshot=context.visibility_snapshot,
            state_version=context.state_version,
            config_hash=context.config_hash,
            parser_refs=_ordered_unique(context.parser_refs),
            model_refs=_ordered_unique(context.model_refs),
        )
        result_class = cls._result_classes[draft.result_type]
        extra: dict[str, object] = {}
        if result_class is ThreatAlert:
            extra = {"confidence": draft.confidence, "severity": draft.severity}
        elif result_class is AnalyticUnavailable:
            extra = {"reason_code": draft.reason_code} if draft.reason_code is not None else {}
        elif result_class is CorrelationFinding:
            extra = {"linked_result_ids": _ordered_unique(draft.linked_result_ids)}

        provisional = result_class(**common, **extra)
        result = result_class(**{**common, **extra, "result_id": result_id_for(provisional)})
        ResultValidator.validate(result, governance)
        return result  # type: ignore[return-value]
