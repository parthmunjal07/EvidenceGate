export type HealthResponse = { status: "ok"; database: "connected" };
export type StatusSnapshot = {
  scientific_status: string;
  integration_status: string;
  governance_version: string;
  readiness: string;
  quality_degraded: boolean;
};
export type QualitySnapshot = {
  packet_loss: string;
  sampling: string;
  parser: string;
  capture_gap: string;
};
export type VisibilitySnapshot = {
  available: string[];
  unavailable: string[];
  degraded: string[];
};
export type ResultDto = {
  result_id: string;
  schema_version: string;
  result_type: string;
  created_time: string;
  lane_id: string;
  family: string;
  plugin_id: string;
  plugin_version: string;
  analytic_version: string;
  governance_version: string;
  entity_reference: string;
  taxonomy: [string, string, string];
  mechanism_id: string | null;
  status_snapshot: StatusSnapshot;
  claim_ceiling: string;
  evidence: Record<string, unknown>;
  evidence_items: string[];
  missing_prerequisites: string[];
  source_observation_ids: string[];
  source_ids: string[];
  quality_snapshot: QualitySnapshot;
  visibility_snapshot: VisibilitySnapshot;
  state_version: number | null;
  config_hash: string | null;
  parser_refs: string[];
  model_refs: string[];
  governing_ids: string[];
  quality_refs: string[];
  provenance_refs: string[];
  evidence_interval: [string, string] | null;
  reason_code: string | null;
};
export type ResultsResponse = {
  results: ResultDto[];
  next_cursor: string | null;
  sync_cursor: string | null;
};
export type FamilyFindingDto = {
  source_result_id: string;
  title: string;
  statements: string[];
  result_type: string;
};
export type FamilyEvidenceViewDto = {
  family_view_id: string;
  family: string;
  time_start: string;
  time_end: string;
  entity_references: string[];
  source_result_ids: string[];
  source_observation_ids: string[];
  findings: FamilyFindingDto[];
  limitations: string[];
  missing_evidence: string[];
  visibility_summary: string[];
  quality_summary: string[];
};
export type FamilyEvidenceResponse = { family_views: FamilyEvidenceViewDto[] };
export type InvestigationLinkDto = {
  link_id: string;
  left_family_view_id: string;
  right_family_view_id: string;
  relation_types: string[];
  shared_source_observation_ids: string[];
  source_result_ids: string[];
  claim_guard: string[];
};
export type InvestigationsResponse = {
  family_views: FamilyEvidenceViewDto[];
  links: InvestigationLinkDto[];
};
export type ConfidenceBasis =
  "MODEL_SCORE" | "STATISTICAL_SUPPORT" | "OBSERVED_EVIDENCE";
export type SihAlertProjection = {
  alert_id: string;
  schema_version: string;
  policy_version: string;
  timestamp: string;
  entity_or_flow_reference: string;
  threat_class: string;
  mechanism_id: string;
  result_type: string;
  severity: "REVIEW";
  confidence_score: number | null;
  confidence_basis: ConfidenceBasis;
  confidence_statement: string;
  supporting_evidence: {
    structured: Record<string, unknown>;
    evidence_items: string[];
    source_observation_ids: string[];
  };
  source_result_ids: string[];
  visibility: VisibilitySnapshot;
  quality: QualitySnapshot;
  claim_ceiling: string;
  model_refs: string[];
  governing_ids: string[];
  provenance_refs: string[];
  quality_refs: string[];
  parser_refs: string[];
};
export type SihStatusProjection = {
  status_id: string;
  schema_version: string;
  policy_version: string;
  timestamp: string;
  entity_or_flow_reference: string;
  mechanism_id: string;
  result_type: string;
  status_kind: string;
  priority: "INFO" | "ATTENTION";
  supporting_evidence: {
    structured: Record<string, unknown>;
    evidence_items: string[];
    source_observation_ids: string[];
  };
  missing_prerequisites: string[];
  source_result_ids: string[];
  visibility: VisibilitySnapshot;
  quality: QualitySnapshot;
  claim_ceiling: string;
  governing_ids: string[];
  provenance_refs: string[];
  quality_refs: string[];
  parser_refs: string[];
};
export type AlertsResponse = {
  policy_version: string;
  policy_status: "ACTIVE";
  meaning_of_alert: "ANALYST_ATTENTION_RECORD";
  alerts: SihAlertProjection[];
  status_items: SihStatusProjection[];
};
export type ReplayRequest = { scenario: string; speed: number };
export type ReplayStatusResponse = {
  state: "IDLE" | "RUNNING" | "COMPLETED" | "FAILED";
  scenario: string | null;
  source_type: string | null;
  records_read: number;
  observations_emitted: number;
  results_persisted: number;
  elapsed_wall_seconds: number;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
};
export type RuntimeTraceEvent = {
  sequence: number;
  kind: string;
  occurred_at: string;
  observation_id: string | null;
  observation_type: string | null;
  lane_id: string | null;
  mechanism: string | null;
  readiness: string | null;
  reason: string | null;
  result_id: string | null;
  source_observation_ids: string[];
  source_record?: SourceRecordPresentationDto | null;
  canonical_observation?: ObservationPresentationDto | null;
};
export type SourceRecordPresentationDto = {
  record_number: number | null;
  event_time: string | null;
  observation_type: string;
  facts: Record<string, unknown>;
};
export type ObservationPresentationDto = {
  observation_id: string;
  observation_type: string;
  event_time: string;
  source_position: string;
  wire_direction: string;
  direction_basis: string;
  finality: string;
  availability_basis: string;
  present_fields: string[];
  identity: {
    observed_identifiers: string[];
    identifier_basis: string;
    role_assignments: { identifier: string; role: string; basis: string }[];
  };
  visibility: {
    available: string[];
    unavailable: string[];
    degraded: string[];
  };
  quality: {
    packet_loss: string;
    sampling: string;
    parser: string;
    capture_gap: string;
  };
  facts: Record<string, unknown>;
};
export type RuntimeTraceResponse = {
  events: RuntimeTraceEvent[];
  latest_sequence: number;
};
export type ScenarioDto = {
  id: string;
  label: string;
  family: string;
  source_type: string;
  asset_version?: string | null;
  demo_title?: string | null;
  demo_purpose?: string | null;
  expected_records?: number | null;
  expected_observations?: number | null;
  expected_routes?: number | null;
  expected_results?: number | null;
  expected_family_views?: number | null;
  expected_relations?: number | null;
  expected_zero_route_observations?: number | null;
  max_trace_events?: number | null;
  needs_dga?: boolean;
  source_label?: string | null;
  episode_summary?: string[];
};
export type RuntimeTarget = {
  lane_id: string;
  mechanism_id: string | null;
  implementation:
    | "ACTIVE_FACTUAL_MECHANISM"
    | "ACTIVE_LEXICAL_MODEL_LANE"
    | "REGISTERED_SHELL";
};
export type FamilyStatus = { family: string; status: string };
export type RuntimeStatusResponse = {
  release_id: string;
  source_sha: string;
  build_sha: string;
  api_contract_version: string;
  state: "ONLINE" | "REPLAYING";
  default_target_count: number;
  active_lane_ids: string[];
  targets: RuntimeTarget[];
  family_status: FamilyStatus[];
  database_status: "connected";
  durable_result_count: number;
  live_subscriber_count: number;
  replay: ReplayStatusResponse;
  scenarios: ScenarioDto[];
  supported_sources: string[];
  dga_model_readiness:
    | "VERIFIED_READY"
    | "ARTIFACT_MISSING"
    | "ARTIFACT_HASH_MISMATCH"
    | "DEPENDENCY_MISMATCH"
    | "MODEL_CONTRACT_MISMATCH";
  dga_model_failure_reason: string | null;
  alert_projection_available: boolean;
  alert_policy_active: boolean;
  alert_policy_version: string | null;
};
export type ResultNotification = {
  event: "result";
  result_id: string;
  created_time: string;
  lane_id: string;
  mechanism_id: string | null;
  result_type: string;
  cursor: string;
};
