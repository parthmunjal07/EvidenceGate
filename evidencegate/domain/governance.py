from dataclasses import dataclass
from datetime import datetime
from evidencegate.domain.enums import ScientificStatus

@dataclass(frozen=True, slots=True)
class LaneGovernance:
    analytic_lane: str
    scientific_status: ScientificStatus
    scientific_phase: str
    scientific_blockers: tuple[str, ...]
    claim_ceiling: str
    governance_version: str
    effective_at: datetime
    
    # Optional parameters (from Amendment/contract)
    demo_capability: str | None = None
    enabled_mode: str | None = None
