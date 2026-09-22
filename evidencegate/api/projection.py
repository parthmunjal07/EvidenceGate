"""Inactive, versioned presentation contract for a future SIH alert policy.

Nothing in the current runtime constructs this model. A human-approved mapping
policy is required before immutable evidence results may be projected into it.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict


class ConfidenceBasis(str, Enum):
    MODEL_PROBABILITY = "MODEL_PROBABILITY"
    MODEL_SCORE = "MODEL_SCORE"
    RULE_MATCH = "RULE_MATCH"
    STATISTICAL_SUPPORT = "STATISTICAL_SUPPORT"
    EVIDENCE_COMPLETENESS = "EVIDENCE_COMPLETENESS"


class SihAlertProjection(BaseModel):
    """Design-only v1 projection; it is not an active API response."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    projection_version: str = "1.0-design"
    alert_id: str
    timestamp: datetime
    entity_reference: str
    threat_class: str
    mechanism_id: str
    severity: str
    confidence_score: float
    confidence_basis: ConfidenceBasis
    supporting_evidence: dict[str, Any]
    source_result_ids: tuple[str, ...]
    visibility: dict[str, tuple[str, ...]]
    quality: dict[str, str]
    claim_ceiling: str
