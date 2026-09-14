from dataclasses import dataclass
from datetime import datetime
from evidencegate.domain.enums import ScientificStatus, ResultType


@dataclass(frozen=True, slots=True)
class LaneGovernance:
    """
    Read-only, versioned scientific governance snapshot. Loaded at run start.
    Plugin code cannot change it. IC-09, IC-17.

    allowed_result_types: tuple[ResultType, ...] — governance explicitly owns which
    result types a lane may emit. ResultValidator must reject every result type not
    in this set. Permissions are NEVER inferred from scientific_status names (IC-17).

    ingest_permitted: bool — when False, IngestAdmissionDecision must reject
    the observation before factual state update. IC-16 ensures that WARMING_UP /
    INSUFFICIENT_HISTORY / STATE_EVICTED are not ingest-admission reasons;
    they are EvaluationReadiness states that run after factual state update.
    """
    analytic_lane: str
    scientific_status: ScientificStatus
    scientific_phase: str
    scientific_blockers: tuple[str, ...]
    claim_ceiling: str
    governance_version: str
    effective_at: datetime
    # Explicit ResultType tuples, not strings (IC-17)
    allowed_result_types: tuple[ResultType, ...]
    ingest_permitted: bool

    # Optional engineering-demonstration descriptors — must not change
    # scientific_status or claim ceiling (contract §5)
    demo_capability: str | None = None
    enabled_mode: str | None = None
