-- EvidenceGate SQLite Schema v1.1
-- Authority: MVP_IMPLEMENTATION_CONTRACT_v1.1.md §9
-- All tables use CREATE TABLE IF NOT EXISTS for idempotent migrations.

-- ──────────────────────────────────────────────────────────────────────────
-- Schema migration tracking
-- ──────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     INTEGER PRIMARY KEY,
    applied_at  TEXT NOT NULL
);

-- ──────────────────────────────────────────────────────────────────────────
-- Run manifest
-- ──────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS runs (
    run_id          TEXT PRIMARY KEY,
    start_time      TEXT NOT NULL,
    config_snapshot TEXT
);

-- ──────────────────────────────────────────────────────────────────────────
-- Source manifests
-- ──────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS source_manifests (
    source_id       TEXT PRIMARY KEY,
    source_kind     TEXT NOT NULL,
    capture_start   TEXT,
    capture_end     TEXT,
    run_id          TEXT,
    FOREIGN KEY(run_id) REFERENCES runs(run_id)
);

-- ──────────────────────────────────────────────────────────────────────────
-- Governance snapshots
-- ──────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS governance_snapshots (
    analytic_lane       TEXT NOT NULL,
    governance_version  TEXT NOT NULL,
    effective_at        TEXT NOT NULL,
    scientific_status   TEXT NOT NULL,
    scientific_phase    TEXT,
    claim_ceiling       TEXT,
    snapshot_json       TEXT,
    PRIMARY KEY (analytic_lane, governance_version)
);

-- ──────────────────────────────────────────────────────────────────────────
-- Plugin manifests
-- ──────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS plugin_manifests (
    plugin_id           TEXT NOT NULL,
    plugin_version      TEXT NOT NULL,
    analytic_version    TEXT NOT NULL,
    manifest_json       TEXT,
    PRIMARY KEY (plugin_id, plugin_version)
);

-- ──────────────────────────────────────────────────────────────────────────
-- Control events
-- ──────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS control_events (
    control_event_id    TEXT PRIMARY KEY,
    control_type        TEXT NOT NULL,
    ingest_time         TEXT NOT NULL,
    source_id           TEXT,
    lane_id             TEXT,
    payload             TEXT
);

-- ──────────────────────────────────────────────────────────────────────────
-- Quality gaps
-- ──────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS quality_gaps (
    gap_id                  TEXT PRIMARY KEY,
    scope                   TEXT NOT NULL,
    first_known_event_time  TEXT NOT NULL,
    last_known_event_time   TEXT NOT NULL,
    detection_time          TEXT NOT NULL,
    count                   INTEGER NOT NULL,
    reason                  TEXT NOT NULL,
    gap_types               TEXT,         -- JSON array
    gap_action_taken        TEXT
);

-- ──────────────────────────────────────────────────────────────────────────
-- Lane health history
-- ──────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS lane_health_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    lane_id         TEXT NOT NULL,
    changed_at      TEXT NOT NULL,
    health_state    TEXT NOT NULL,
    gap_id          TEXT,               -- associated gap if health changed due to gap
    FOREIGN KEY(gap_id) REFERENCES quality_gaps(gap_id)
);

-- ──────────────────────────────────────────────────────────────────────────
-- Results (append-only, IC-11)
-- ──────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS results (
    result_id               TEXT PRIMARY KEY,
    result_type             TEXT NOT NULL,
    created_time            TEXT NOT NULL,
    entity_reference        TEXT NOT NULL,
    taxonomy_1              TEXT,
    taxonomy_2              TEXT,
    taxonomy_3              TEXT,
    plugin_version          TEXT NOT NULL,
    analytic_version        TEXT NOT NULL,
    status_snapshot         TEXT,
    claim_ceiling           TEXT,
    quality_ref             TEXT,
    provenance_ref          TEXT,
    confidence              TEXT,         -- string or NULL; never a numeric threat score on scaffold
    severity                TEXT,
    reason_code             TEXT,
    evidence_interval_start TEXT,
    evidence_interval_end   TEXT
);

-- ──────────────────────────────────────────────────────────────────────────
-- Evidence items (mandatory child of results — written atomically, IC-18)
-- ──────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS evidence_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    result_id       TEXT NOT NULL,
    evidence_ref    TEXT NOT NULL,
    FOREIGN KEY(result_id) REFERENCES results(result_id)
);

-- ──────────────────────────────────────────────────────────────────────────
-- Provenance references (mandatory child — written atomically, IC-18)
-- ──────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS provenance_references (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    result_id       TEXT NOT NULL,
    provenance_ref  TEXT NOT NULL,
    UNIQUE(result_id, provenance_ref),
    FOREIGN KEY(result_id) REFERENCES results(result_id)
);

-- ──────────────────────────────────────────────────────────────────────────
-- Missing prerequisites (written atomically with result, IC-18)
-- ──────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS missing_prerequisites (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    result_id       TEXT NOT NULL,
    prerequisite    TEXT NOT NULL,
    FOREIGN KEY(result_id) REFERENCES results(result_id)
);

-- ──────────────────────────────────────────────────────────────────────────
-- Result links (for CorrelationFinding only — written atomically, IC-18)
-- ──────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS result_links (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    source_result_id    TEXT NOT NULL,
    linked_result_id    TEXT NOT NULL,
    FOREIGN KEY(source_result_id) REFERENCES results(result_id),
    FOREIGN KEY(linked_result_id) REFERENCES results(result_id)
);

-- ──────────────────────────────────────────────────────────────────────────
-- Metric snapshots
-- ──────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS metric_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    captured_at     TEXT NOT NULL,
    run_id          TEXT,
    snapshot_json   TEXT NOT NULL
);

-- ──────────────────────────────────────────────────────────────────────────
-- Migration record
-- ──────────────────────────────────────────────────────────────────────────
INSERT OR IGNORE INTO schema_migrations (version, applied_at)
    VALUES (1, CURRENT_TIMESTAMP);
