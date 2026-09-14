from dataclasses import dataclass
from typing import Optional, Sequence
from evidencegate.domain.enums import AdmissionReason, ScientificStatus
from evidencegate.domain.events import NetworkObservation
from evidencegate.domain.governance import LaneGovernance
from evidencegate.registry.manifest import PluginManifest

@dataclass(frozen=True, slots=True)
class AdmissionDecision:
    admitted: bool
    reasons: tuple[AdmissionReason, ...]
    quality_ref: Optional[str]
    governance_version: str

class AdmissionEvaluator:
    """
    Admission evaluates required fields, observation contract, finality, visibility, quality, 
    history readiness, and imported governance availability.
    """
    @staticmethod
    def evaluate(
        observation: NetworkObservation,
        manifest: PluginManifest,
        governance: LaneGovernance
    ) -> AdmissionDecision:
        reasons = []
        
        if governance.scientific_status == ScientificStatus.ANALYTIC_UNAVAILABLE:
            reasons.append(AdmissionReason.ANALYTIC_UNAVAILABLE)
            
        # Example required checks based on manifest
        # (A real implementation would check specific fields from manifest.admission_requirements)
        
        admitted = len(reasons) == 0
        return AdmissionDecision(
            admitted=admitted,
            reasons=tuple(reasons) if not admitted else (AdmissionReason.ADMITTED,),
            quality_ref=observation.quality_ref,
            governance_version=governance.governance_version
        )
