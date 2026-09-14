CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    start_time TEXT NOT NULL,
    config_snapshot TEXT
);

CREATE TABLE IF NOT EXISTS results (
    result_id TEXT PRIMARY KEY,
    result_type TEXT NOT NULL,
    created_time TEXT NOT NULL,
    entity_reference TEXT NOT NULL,
    taxonomy_1 TEXT,
    taxonomy_2 TEXT,
    taxonomy_3 TEXT,
    plugin_version TEXT NOT NULL,
    analytic_version TEXT NOT NULL,
    status_snapshot TEXT,
    claim_ceiling TEXT,
    quality_ref TEXT,
    provenance_ref TEXT,
    confidence TEXT,
    severity TEXT,
    reason_code TEXT,
    evidence_interval_start TEXT,
    evidence_interval_end TEXT
);

CREATE TABLE IF NOT EXISTS evidence_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    result_id TEXT NOT NULL,
    evidence_ref TEXT NOT NULL,
    FOREIGN KEY(result_id) REFERENCES results(result_id)
);

CREATE TABLE IF NOT EXISTS missing_prerequisites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    result_id TEXT NOT NULL,
    prerequisite TEXT NOT NULL,
    FOREIGN KEY(result_id) REFERENCES results(result_id)
);

CREATE TABLE IF NOT EXISTS result_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_result_id TEXT NOT NULL,
    linked_result_id TEXT NOT NULL,
    FOREIGN KEY(source_result_id) REFERENCES results(result_id),
    FOREIGN KEY(linked_result_id) REFERENCES results(result_id)
);

CREATE TABLE IF NOT EXISTS control_events (
    control_event_id TEXT PRIMARY KEY,
    control_type TEXT NOT NULL,
    ingest_time TEXT NOT NULL,
    payload TEXT
);

CREATE TABLE IF NOT EXISTS quality_gaps (
    gap_id TEXT PRIMARY KEY,
    scope TEXT NOT NULL,
    first_known_event_time TEXT NOT NULL,
    last_known_event_time TEXT NOT NULL,
    detection_time TEXT NOT NULL,
    count INTEGER NOT NULL,
    reason TEXT NOT NULL
);

-- Basic inserts to satisfy schema migration check
INSERT OR IGNORE INTO schema_migrations (version, applied_at) VALUES (1, CURRENT_TIMESTAMP);
