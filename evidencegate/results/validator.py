from evidencegate.results.types import Result, ThreatAlert, AnalyticUnavailable
from evidencegate.domain.enums import ResultType, ScientificStatus
from evidencegate.domain.governance import LaneGovernance

class ResultValidator:
    """
    ResultValidator rejects:
    - any ThreatAlert from a governance-unavailable or scaffold lane;
    - a ThreatAlert with absent/undefined confidence semantics;
    - confidence/severity/threat score on a scaffold or inappropriate non-alert result;
    - a result whose taxonomy/version/governance snapshot is missing.
    """
    @staticmethod
    def validate(result: Result, governance: LaneGovernance) -> None:
        if not result.taxonomy or len(result.taxonomy) != 3:
            raise ValueError(f"Result {result.result_id} missing valid 3-level taxonomy.")
        if not result.plugin_version or not result.analytic_version:
            raise ValueError(f"Result {result.result_id} missing plugin/analytic version.")
        
        is_scaffold = governance.scientific_status in (
            ScientificStatus.ANALYTIC_UNAVAILABLE,
            ScientificStatus.EVIDENCE_CONSTRUCTION
        )
        
        if isinstance(result, ThreatAlert):
            if is_scaffold:
                raise ValueError("ThreatAlert cannot be emitted from a scaffold/unavailable lane.")
            if not result.confidence:
                raise ValueError("ThreatAlert must define confidence semantics.")
        
        # Enforce no confidence/severity on inappropriate results
        if not isinstance(result, ThreatAlert):
            if getattr(result, "confidence", None) is not None or getattr(result, "severity", None) is not None:
                raise ValueError(f"Result type {result.result_type} cannot have confidence/severity.")
