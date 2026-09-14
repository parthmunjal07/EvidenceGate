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
from evidencegate.domain.enums import AdmissionReason, ScientificStatus, EvidenceReadiness
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
    those are EvaluationReadinessEvaluator concerns.
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

        # Factual field presence: if present_fields is explicitly set and non-empty,
        # we could check required fields here. For the MVP scaffold this is permissive.
        # A real implementation would check manifest.admission_requirements.

        admitted = len(reasons) == 0
        return IngestAdmissionDecision(
            admitted=admitted,
            reasons=tuple(reasons),
            quality_ref=observation.quality_ref,
            governance_version=governance.governance_version,
        )


# ---------------------------------------------------------------------------
# Evaluation Readiness Evaluator
# ---------------------------------------------------------------------------

class EvaluationReadinessEvaluator:
    """
    Phase 2 evaluation readiness check. Runs after factual state update.
    Returns an EvaluationReadinessDecision describing the lifecycle state.
    Never rejects an observation from ingest; only advises on evaluation.
    """
    @staticmethod
    def evaluate(
        observation_count: int,
        state_evicted: bool = False,
        terminal_pending: bool = False,
        warmup_threshold: int = 1,
    ) -> EvaluationReadinessDecision:
        """
        Minimal scaffold readiness lifecycle.

        - observation_count == 0: should not happen post-update, but guard.
        - observation_count <= warmup_threshold: WARMING_UP.
        - observation_count > warmup_threshold: READY.
        - state_evicted=True: STATE_EVICTED (takes precedence).
        - terminal_pending=True: TERMINAL_EVIDENCE_PENDING.

        No threat-specific thresholds, windows, or science.
        """
        if state_evicted:
            return EvaluationReadinessDecision(
                readiness=EvidenceReadiness.STATE_EVICTED,
                reason="State was evicted; evidence continuity broken.",
            )
        if terminal_pending:
            return EvaluationReadinessDecision(
                readiness=EvidenceReadiness.TERMINAL_EVIDENCE_PENDING,
                reason="Waiting for terminal evidence.",
            )
        if observation_count <= warmup_threshold:
            return EvaluationReadinessDecision(
                readiness=EvidenceReadiness.WARMING_UP,
                reason=f"Only {observation_count} observation(s) seen; warming up.",
            )
        return EvaluationReadinessDecision(readiness=EvidenceReadiness.READY)
