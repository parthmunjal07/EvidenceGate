"""Pure, active SIH presentation projections over immutable results.

The policy in this module is deliberately separate from result
finalization and persistence. It never changes, replaces, or writes a
scientific :class:`~evidencegate.results.types.Result`.
"""
from __future__ import annotations

import math
import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict

from evidencegate.domain.enums import ResultType
from evidencegate.results.types import Result


POLICY_VERSION = "SIH_ALERT_POLICY_V1"
SCHEMA_VERSION = "1.0"


class ConfidenceBasis(str, Enum):
    """What a confidence field actually represents; never omit this basis."""

    MODEL_SCORE = "MODEL_SCORE"
    STATISTICAL_SUPPORT = "STATISTICAL_SUPPORT"
    OBSERVED_EVIDENCE = "OBSERVED_EVIDENCE"


class AlertSeverity(str, Enum):
    """Analyst priority under this policy, not likelihood or impact."""

    REVIEW = "REVIEW"


class StatusKind(str, Enum):
    QUALITY_NOTIFICATION = "QUALITY_NOTIFICATION"
    CAPABILITY_NOTIFICATION = "CAPABILITY_NOTIFICATION"
    EVIDENCE_STATUS = "EVIDENCE_STATUS"
    SYSTEM_CAPABILITY_STATUS = "SYSTEM_CAPABILITY_STATUS"
    PLUGIN_STATUS = "PLUGIN_STATUS"


class StatusPriority(str, Enum):
    INFO = "INFO"
    ATTENTION = "ATTENTION"


class SihAlertProjection(BaseModel):
    """Analyst-attention record backed by one immutable result.

    ``alert`` means analyst attention, not a confirmed malicious attack.
    Numeric confidence is nullable and is meaningful only with its mandatory
    basis. The only current numeric value is the DGA lexical model score.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    alert_id: str
    schema_version: str = SCHEMA_VERSION
    policy_version: str = POLICY_VERSION
    timestamp: datetime
    entity_or_flow_reference: str
    threat_class: str
    mechanism_id: str
    result_type: str
    severity: AlertSeverity
    confidence_score: float | None
    confidence_basis: ConfidenceBasis
    confidence_statement: str
    supporting_evidence: dict[str, Any]
    source_result_ids: tuple[str, ...]
    visibility: dict[str, tuple[str, ...]]
    quality: dict[str, str]
    claim_ceiling: str
    model_refs: tuple[str, ...]
    governing_ids: tuple[str, ...]
    provenance_refs: tuple[str, ...]
    quality_refs: tuple[str, ...]
    parser_refs: tuple[str, ...]


class SihStatusProjection(BaseModel):
    """Non-threat quality, evidence, or system/capability status record."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status_id: str
    schema_version: str = SCHEMA_VERSION
    policy_version: str = POLICY_VERSION
    timestamp: datetime
    entity_or_flow_reference: str
    mechanism_id: str
    result_type: str
    status_kind: StatusKind
    priority: StatusPriority
    supporting_evidence: dict[str, Any]
    missing_prerequisites: tuple[str, ...]
    source_result_ids: tuple[str, ...]
    visibility: dict[str, tuple[str, ...]]
    quality: dict[str, str]
    claim_ceiling: str
    governing_ids: tuple[str, ...]
    provenance_refs: tuple[str, ...]
    quality_refs: tuple[str, ...]
    parser_refs: tuple[str, ...]


ProjectionRecord = SihAlertProjection | SihStatusProjection


class ProjectionPolicyError(ValueError):
    """An admitted source result violates the explicit projection contract."""


def _stable_id(kind: str, result_id: str) -> str:
    return str(uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"urn:evidencegate:{POLICY_VERSION}:{kind}:{result_id}",
    ))


def _visibility(result: Result) -> dict[str, tuple[str, ...]]:
    value = result.visibility_snapshot
    return {
        "available": tuple(sorted(item.value for item in value.available)),
        "unavailable": tuple(sorted(item.value for item in value.unavailable)),
        "degraded": tuple(sorted(item.value for item in value.degraded)),
    }


def _quality(result: Result) -> dict[str, str]:
    value = result.quality_snapshot
    return {
        "packet_loss": value.packet_loss.value,
        "sampling": value.sampling.value,
        "parser": value.parser.value,
        "capture_gap": value.capture_gap.value,
    }


def _evidence(result: Result) -> dict[str, Any]:
    # EvidencePayload returns a detached value, preserving result immutability.
    return {
        "structured": result.evidence.to_value(),
        "evidence_items": list(result.evidence_items),
        "source_observation_ids": list(result.source_observation_ids),
    }


def _presentation_semantics(result: Result) -> tuple[str, ConfidenceBasis]:
    lane = result.lane_id
    if lane.startswith("ddos."):
        return "DDOS", ConfidenceBasis.STATISTICAL_SUPPORT
    if lane.startswith("c2."):
        return "BOTNET_C2_BEACONING", ConfidenceBasis.STATISTICAL_SUPPORT
    if lane == "dga.m1":
        return "DGA", ConfidenceBasis.MODEL_SCORE
    if lane.startswith("dns_tunnelling."):
        return "DNS_TUNNELLING", ConfidenceBasis.OBSERVED_EVIDENCE
    if lane.startswith("encrypted_session."):
        return "MALWARE_IN_ENCRYPTED_SESSION", ConfidenceBasis.OBSERVED_EVIDENCE
    if lane.startswith("recon."):
        return "RECONNAISSANCE", ConfidenceBasis.STATISTICAL_SUPPORT
    if lane.startswith("unusual_transfer."):
        return "DATA_EXFILTRATION", ConfidenceBasis.OBSERVED_EVIDENCE
    raise ProjectionPolicyError(f"no SIH presentation taxonomy for lane {lane!r}")


def _confidence(result: Result, basis: ConfidenceBasis) -> tuple[float | None, str]:
    if basis is not ConfidenceBasis.MODEL_SCORE:
        return None, (
            f"{basis.value}; no numeric maliciousness probability is defined by "
            "this mechanism"
        )
    evidence = result.evidence.to_value()
    value = evidence.get("dga_labelled_lexical_resemblance_score")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProjectionPolicyError("DGA review result is missing its lexical model score")
    score = float(value)
    if not math.isfinite(score):
        raise ProjectionPolicyError("DGA lexical model score must be finite")
    return score, "DGA-labelled lexical resemblance score; not calibrated attack probability"


_STATUS_POLICY: dict[ResultType, tuple[StatusKind, StatusPriority]] = {
    ResultType.QUALITY_DEGRADED: (
        StatusKind.QUALITY_NOTIFICATION, StatusPriority.ATTENTION,
    ),
    ResultType.PREREQUISITE_MISSING: (
        StatusKind.CAPABILITY_NOTIFICATION, StatusPriority.ATTENTION,
    ),
    ResultType.INSUFFICIENT_EVIDENCE: (
        StatusKind.EVIDENCE_STATUS, StatusPriority.INFO,
    ),
    ResultType.ANALYTIC_UNAVAILABLE: (
        StatusKind.SYSTEM_CAPABILITY_STATUS, StatusPriority.ATTENTION,
    ),
    ResultType.PLUGIN_STATUS: (StatusKind.PLUGIN_STATUS, StatusPriority.INFO),
}


def project_result(result: Result) -> tuple[ProjectionRecord, ...]:
    """Project one result into zero or one V1 presentation records.

    Review findings become analyst evidence alerts. Operational and evidence
    lifecycle results remain visibly separate status items. Existing
    ``THREAT_ALERT`` and correlation results are not reinterpreted by this
    policy, which also prevents implicit cross-family fusion.
    """
    common = {
        "timestamp": result.created_time,
        "entity_or_flow_reference": result.entity_reference,
        "mechanism_id": result.mechanism_id or result.lane_id,
        "result_type": result.result_type.value,
        "supporting_evidence": _evidence(result),
        "source_result_ids": (result.result_id,),
        "visibility": _visibility(result),
        "quality": _quality(result),
        "claim_ceiling": result.claim_ceiling,
        "governing_ids": result.governing_ids,
        "provenance_refs": result.provenance_refs,
        "quality_refs": result.quality_refs,
        "parser_refs": result.parser_refs,
    }
    if result.result_type is ResultType.REVIEW_FINDING:
        threat_class, basis = _presentation_semantics(result)
        score, statement = _confidence(result, basis)
        return (SihAlertProjection(
            alert_id=_stable_id("alert", result.result_id),
            threat_class=threat_class,
            severity=AlertSeverity.REVIEW,
            confidence_score=score,
            confidence_basis=basis,
            confidence_statement=statement,
            model_refs=result.model_refs,
            **common,
        ),)
    status_policy = _STATUS_POLICY.get(result.result_type)
    if status_policy is None:
        return ()
    kind, priority = status_policy
    return (SihStatusProjection(
        status_id=_stable_id("status", result.result_id),
        status_kind=kind,
        priority=priority,
        missing_prerequisites=result.missing_prerequisites,
        **common,
    ),)


def project_results(
    results: tuple[Result, ...] | list[Result],
) -> tuple[ProjectionRecord, ...]:
    """Project in source order without deduplicating distinct source results."""
    return tuple(item for result in results for item in project_result(result))
