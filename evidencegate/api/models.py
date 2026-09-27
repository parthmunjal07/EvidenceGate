"""Typed public API contracts for the EvidenceGate product surface."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from evidencegate.api.projection import SihAlertProjection, SihStatusProjection


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HealthResponse(StrictModel):
    status: Literal["ok"]
    database: Literal["connected"]


class StatusSnapshotDto(StrictModel):
    scientific_status: str
    integration_status: str
    governance_version: str
    readiness: str
    quality_degraded: bool


class QualitySnapshotDto(StrictModel):
    packet_loss: str
    sampling: str
    parser: str
    capture_gap: str


class VisibilitySnapshotDto(StrictModel):
    available: list[str]
    unavailable: list[str]
    degraded: list[str]


class ResultDto(StrictModel):
    result_id: str
    schema_version: str
    result_type: str
    created_time: datetime
    lane_id: str
    family: str
    plugin_id: str
    plugin_version: str
    analytic_version: str
    governance_version: str
    entity_reference: str
    taxonomy: tuple[str, str, str]
    mechanism_id: str | None
    status_snapshot: StatusSnapshotDto
    claim_ceiling: str
    evidence: dict[str, Any]
    evidence_items: list[str]
    missing_prerequisites: list[str]
    source_observation_ids: list[str]
    source_ids: list[str]
    quality_snapshot: QualitySnapshotDto
    visibility_snapshot: VisibilitySnapshotDto
    state_version: int | None
    config_hash: str | None
    parser_refs: list[str]
    model_refs: list[str]
    governing_ids: list[str]
    quality_refs: list[str]
    provenance_refs: list[str]
    evidence_interval: tuple[datetime, datetime] | None
    reason_code: str | None = None


class ResultsResponse(StrictModel):
    results: list[ResultDto]
    next_cursor: str | None
    sync_cursor: str | None = Field(
        description="High-water cursor for durable forward resynchronization."
    )


class FamilyFindingDto(StrictModel):
    source_result_id: str
    title: str
    statements: list[str]
    result_type: str


class FamilyEvidenceViewDto(StrictModel):
    family_view_id: str
    family: str
    time_start: datetime
    time_end: datetime
    entity_references: list[str]
    source_result_ids: list[str]
    source_observation_ids: list[str]
    findings: list[FamilyFindingDto]
    limitations: list[str]
    missing_evidence: list[str]
    visibility_summary: list[str]
    quality_summary: list[str]


class FamilyEvidenceResponse(StrictModel):
    family_views: list[FamilyEvidenceViewDto]


class InvestigationLinkDto(StrictModel):
    link_id: str
    left_family_view_id: str
    right_family_view_id: str
    relation_types: list[str]
    shared_source_observation_ids: list[str]
    source_result_ids: list[str]
    claim_guard: list[str]


class InvestigationsResponse(StrictModel):
    family_views: list[FamilyEvidenceViewDto]
    links: list[InvestigationLinkDto]


class ReplayRequest(StrictModel):
    scenario: str
    speed: float = Field(default=0, ge=0, le=1000)


class ReplayStatusResponse(StrictModel):
    state: Literal["IDLE", "RUNNING", "COMPLETED", "FAILED"]
    scenario: str | None
    source_type: str | None = None
    records_read: int
    observations_emitted: int
    results_persisted: int
    elapsed_wall_seconds: float
    started_at: datetime | None
    finished_at: datetime | None
    error: str | None


class RuntimeTraceEventDto(StrictModel):
    sequence: int
    kind: str
    occurred_at: datetime
    observation_id: str | None = None
    observation_type: str | None = None
    lane_id: str | None = None
    mechanism: str | None = None
    readiness: str | None = None
    reason: str | None = None
    result_id: str | None = None
    source_observation_ids: list[str] = Field(default_factory=list)
    source_record: "SourceRecordPresentationDto | None" = None
    canonical_observation: "ObservationPresentationDto | None" = None


class SourceRecordPresentationDto(StrictModel):
    record_number: int | None = None
    event_time: str | None = None
    observation_type: str
    facts: dict[str, Any]


class ObservationPresentationDto(StrictModel):
    observation_id: str
    observation_type: str
    event_time: str
    source_position: str
    wire_direction: str
    direction_basis: str
    finality: str
    availability_basis: str
    present_fields: list[str]
    identity: dict[str, Any]
    visibility: dict[str, list[str]]
    quality: dict[str, str]
    facts: dict[str, Any]


RuntimeTraceEventDto.model_rebuild()


class RuntimeTraceResponse(StrictModel):
    events: list[RuntimeTraceEventDto]
    latest_sequence: int


class ScenarioDto(StrictModel):
    id: str
    label: str
    family: str
    source_type: str = "NDJSON"


class TargetStatusDto(StrictModel):
    lane_id: str
    mechanism_id: str | None
    implementation: Literal[
        "ACTIVE_FACTUAL_MECHANISM", "ACTIVE_LEXICAL_MODEL_LANE", "REGISTERED_SHELL"
    ]


class FamilyStatusDto(StrictModel):
    family: str
    status: str


class RuntimeStatusResponse(StrictModel):
    state: Literal["ONLINE", "REPLAYING"]
    default_target_count: int
    active_lane_ids: list[str]
    targets: list[TargetStatusDto]
    family_status: list[FamilyStatusDto]
    database_status: Literal["connected"]
    durable_result_count: int
    live_subscriber_count: int
    replay: ReplayStatusResponse
    scenarios: list[ScenarioDto]
    supported_sources: list[str] = Field(default_factory=list)
    dga_model_readiness: Literal[
        "VERIFIED_READY", "ARTIFACT_MISSING", "ARTIFACT_HASH_MISMATCH",
        "DEPENDENCY_MISMATCH", "MODEL_CONTRACT_MISMATCH",
    ]
    dga_model_failure_reason: str | None = None
    alert_projection_available: bool = False
    alert_policy_active: bool = True
    alert_policy_version: str | None = None


class AlertsResponse(StrictModel):
    policy_version: str
    policy_status: Literal["ACTIVE"] = "ACTIVE"
    meaning_of_alert: Literal["ANALYST_ATTENTION_RECORD"] = "ANALYST_ATTENTION_RECORD"
    alerts: list[SihAlertProjection]
    status_items: list[SihStatusProjection]


class ResultNotification(StrictModel):
    event: Literal["result"] = "result"
    result_id: str
    created_time: datetime
    lane_id: str
    mechanism_id: str | None
    result_type: str
    cursor: str


class StreamGap(StrictModel):
    event: Literal["stream_gap"] = "stream_gap"
    resync_required: Literal[True] = True
