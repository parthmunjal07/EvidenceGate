"""
results/validator.py — ResultValidator enforcing contract §8 and IC-17.

IC-17: Governance owns allowed_result_types. Result permissions are NEVER
inferred from scientific status names. ResultValidator must reject every
result type not explicitly listed in governance.allowed_result_types.

allowed_result_types is now tuple[ResultType, ...] (enum values), so we
compare result.result_type (a ResultType enum) directly against the tuple,
never against string representations.
"""
from evidencegate.results.types import EvidencePayload, Result, ResultStatusSnapshot, ThreatAlert
from evidencegate.domain.events import VisibilityProfile
from evidencegate.domain.quality import EvidenceQuality
from evidencegate.domain.enums import ResultType, ScientificStatus
from evidencegate.domain.governance import LaneGovernance


class ResultValidator:
    """
    Validates results against governance constraints.

    Rejects:
    - Any result type not explicitly listed in governance.allowed_result_types (IC-17).
    - Any ThreatAlert from a governance-unavailable or scaffold lane (IC-08).
    - A ThreatAlert without confidence semantics defined (contract §8).
    - Confidence / severity on a non-ThreatAlert result (contract §8).
    - A result whose taxonomy / version / governance snapshot is missing.
    """

    @staticmethod
    def validate(result: Result, governance: LaneGovernance) -> None:
        # ── Taxonomy and versioning ─────────────────────────────────────────
        if not result.taxonomy or len(result.taxonomy) != 3:
            raise ValueError(
                f"Result {result.result_id} missing valid 3-level taxonomy."
            )
        if not result.schema_version:
            raise ValueError(f"Result {result.result_id} missing schema version.")
        if not result.lane_id:
            raise ValueError(f"Result {result.result_id} missing lane id.")
        if not result.plugin_id:
            raise ValueError(f"Result {result.result_id} missing plugin id.")
        if not result.plugin_version or not result.analytic_version:
            raise ValueError(
                f"Result {result.result_id} missing plugin/analytic version."
            )
        if not result.governance_version:
            raise ValueError(f"Result {result.result_id} missing governance version.")
        if not result.claim_ceiling:
            raise ValueError(f"Result {result.result_id} missing claim ceiling.")
        if not isinstance(result.status_snapshot, ResultStatusSnapshot):
            raise ValueError(f"Result {result.result_id} has invalid status snapshot.")
        if result.status_snapshot.governance_version != result.governance_version:
            raise ValueError(f"Result {result.result_id} has inconsistent governance version.")
        if result.schema_version != "2.0":
            if not result.mechanism_id or not result.mechanism_id.strip():
                raise ValueError(f"Result {result.result_id} missing mechanism id.")
            if not isinstance(result.evidence, EvidencePayload):
                raise ValueError(f"Result {result.result_id} has invalid evidence payload.")
            if not isinstance(result.quality_snapshot, EvidenceQuality):
                raise ValueError(f"Result {result.result_id} has invalid quality snapshot.")
            if not isinstance(result.visibility_snapshot, VisibilityProfile):
                raise ValueError(f"Result {result.result_id} has invalid visibility snapshot.")
            if result.state_version is not None and (
                isinstance(result.state_version, bool)
                or not isinstance(result.state_version, int)
                or result.state_version < 1
            ):
                raise ValueError(f"Result {result.result_id} has invalid state version.")

        # ── IC-17: Governance explicitly owns allowed_result_types ──────────
        # Compare ResultType enum value directly — never infer from status names.
        # governance.allowed_result_types is tuple[ResultType, ...].
        if result.result_type not in governance.allowed_result_types:
            raise ValueError(
                f"Result type {result.result_type.value} is not allowed by governance."
            )

        # ── IC-08: No ThreatAlert from scaffold / unavailable lanes ─────────
        is_scaffold = governance.scientific_status in (
            ScientificStatus.ANALYTIC_UNAVAILABLE,
            ScientificStatus.EVIDENCE_CONSTRUCTION,
        )

        if isinstance(result, ThreatAlert):
            if is_scaffold:
                raise ValueError(
                    "ThreatAlert cannot be emitted from a scaffold/unavailable lane (IC-08)."
                )
            if not result.confidence:
                raise ValueError(
                    "ThreatAlert must define confidence semantics (contract §8)."
                )

        # ── No confidence/severity on non-alert results ─────────────────────
        if not isinstance(result, ThreatAlert):
            if (
                getattr(result, "confidence", None) is not None
                or getattr(result, "severity", None) is not None
            ):
                raise ValueError(
                    f"Result type {result.result_type.value} cannot carry confidence/severity."
                )
