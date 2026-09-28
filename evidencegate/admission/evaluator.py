"""
admission/evaluator.py — Two-phase admission decisions as required by IC-16 and contract §6.3.

Phase 1 — IngestAdmissionDecision (runs BEFORE factual state update):
  Checks: required factual fields, supported observation contract,
  minimum safe quality/visibility, governance ingest_permitted.
  MUST NOT reject for WARMING_UP, INSUFFICIENT_HISTORY, or STATE_EVICTED.

Phase 2 — EvaluationReadinessDecision (runs AFTER factual state update):
  Checks lifecycle state and decides whether the plugin can evaluate.
  States: READY, WARMING_UP, INSUFFICIENT_HISTORY, STATE_EVICTED,
          TERMINAL_EVIDENCE_PENDING.
"""

from dataclasses import dataclass
from typing import Optional
from evidencegate.domain.enums import (
    AdmissionReason,
    CapabilityState,
    EvidenceReadiness,
)
from evidencegate.domain.events import NetworkObservation
from evidencegate.domain.governance import LaneGovernance
from evidencegate.registry.manifest import PluginManifest


# ---------------------------------------------------------------------------
# Phase 1: Ingest Admission Decision
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class IngestAdmissionDecision:
    """
    Typed decision produced by the ingest admission check (Phase 1).
    Runs before factual state update. Rejection reasons may only include
    factual/governance reasons — never WARMING_UP, INSUFFICIENT_HISTORY,
    or STATE_EVICTED (those are Phase 2 EvaluationReadiness states).
    """

    admitted: bool
    reasons: tuple[AdmissionReason, ...]
    quality_ref: Optional[str]
    governance_version: str


# Keep old name as alias for backwards compatibility in tests that still import it
@dataclass(frozen=True, slots=True)
class AdmissionDecision:
    """
    Legacy alias kept so existing tests that import AdmissionDecision still work.
    New code should use IngestAdmissionDecision.
    """

    admitted: bool
    reasons: tuple[AdmissionReason, ...]
    quality_ref: Optional[str]
    governance_version: str


# ---------------------------------------------------------------------------
# Phase 2: Evaluation Readiness Decision
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EvaluationReadinessDecision:
    """
    Typed decision produced after factual state update (Phase 2).
    Communicates whether the analytic can evaluate and why.
    WARMING_UP / INSUFFICIENT_HISTORY / STATE_EVICTED must never prevent
    the factual state ingestion above — they are purely post-update lifecycle
    states (IC-16).
    """

    readiness: EvidenceReadiness
    reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Admission Evaluator
# ---------------------------------------------------------------------------


class AdmissionEvaluator:
    """
    Ingest Admission (Phase 1) only. Checks required fields, observation
    contract, minimum quality/visibility, and governance ingest_permitted.

    It must NOT check WARMING_UP / INSUFFICIENT_HISTORY / STATE_EVICTED;
    those are mechanism-owned evaluation-readiness concerns.
    """

    @staticmethod
    def evaluate(
        observation: NetworkObservation,
        manifest: PluginManifest,
        governance: LaneGovernance,
    ) -> IngestAdmissionDecision:
        reasons: list[AdmissionReason] = []
        # Check governance ingest permission
        if not governance.ingest_permitted:
            reasons.append(AdmissionReason.ANALYTIC_UNAVAILABLE)

        # Check that the observation type is accepted by this plugin
        if observation.observation_type not in manifest.accepted_observation_types:
            reasons.append(AdmissionReason.UNSUPPORTED_OBSERVATION_CONTRACT)

        # Check required fields
        for field in manifest.required_fields:
            if field not in observation.present_fields:
                reasons.append(AdmissionReason.PREREQUISITE_MISSING)

        # Check observation contracts
        if manifest.required_observation_contracts and manifest.required_observation_contracts[
            0
        ] not in ("NOT_YET_GOVERNED", "NOT_APPLICABLE"):
            if observation.observation_contract not in manifest.required_observation_contracts:
                reasons.append(AdmissionReason.UNSUPPORTED_OBSERVATION_CONTRACT)

        # Check finality
        if manifest.allowed_finality and observation.finality not in manifest.allowed_finality:
            reasons.append(AdmissionReason.UNSUPPORTED_FINALITY)

        # Check availability basis
        if (
            manifest.allowed_availability_basis
            and observation.availability_basis not in manifest.allowed_availability_basis
        ):
            reasons.append(AdmissionReason.UNSUPPORTED_AVAILABILITY)

        # Typed factual capability and quality checks. quality_ref is provenance,
        # never a proxy for sufficiency.
        for capability in manifest.required_visibility_capabilities:
            if observation.visibility.state(capability) is not CapabilityState.AVAILABLE:
                reasons.append(AdmissionReason.INSUFFICIENT_VISIBILITY)
        for requirement in manifest.required_quality:
            if observation.quality.state(requirement.fact) not in requirement.allowed_states:
                reasons.append(AdmissionReason.INSUFFICIENT_VISIBILITY)

        admitted = len(reasons) == 0
        return IngestAdmissionDecision(
            admitted=admitted,
            reasons=tuple(reasons),
            quality_ref=observation.quality_ref,
            governance_version=governance.governance_version,
        )
