-- M6.5: structured mechanism evidence and runtime provenance.
-- Additive only: existing v1/v2 rows retain their IDs and scientific content.
ALTER TABLE results ADD COLUMN mechanism_id TEXT;
ALTER TABLE results ADD COLUMN evidence_json TEXT;
ALTER TABLE results ADD COLUMN quality_snapshot_json TEXT;
ALTER TABLE results ADD COLUMN visibility_snapshot_json TEXT;
ALTER TABLE results ADD COLUMN state_version INTEGER;
ALTER TABLE results ADD COLUMN config_hash TEXT;

CREATE TABLE source_observation_ids (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    result_id TEXT NOT NULL,
    source_observation_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    UNIQUE(result_id, position),
    UNIQUE(result_id, source_observation_id),
    FOREIGN KEY(result_id) REFERENCES results(result_id)
);

CREATE TABLE result_source_ids (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    result_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    UNIQUE(result_id, position),
    UNIQUE(result_id, source_id),
    FOREIGN KEY(result_id) REFERENCES results(result_id)
);

CREATE TABLE parser_references (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    result_id TEXT NOT NULL,
    parser_ref TEXT NOT NULL,
    position INTEGER NOT NULL,
    UNIQUE(result_id, position),
    UNIQUE(result_id, parser_ref),
    FOREIGN KEY(result_id) REFERENCES results(result_id)
);

CREATE TABLE model_references (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    result_id TEXT NOT NULL,
    model_ref TEXT NOT NULL,
    position INTEGER NOT NULL,
    UNIQUE(result_id, position),
    UNIQUE(result_id, model_ref),
    FOREIGN KEY(result_id) REFERENCES results(result_id)
);

CREATE INDEX ix_results_mechanism_created_result
    ON results(mechanism_id, created_time, result_id);
CREATE INDEX ix_source_observation_ids_observation
    ON source_observation_ids(source_observation_id, result_id);
CREATE INDEX ix_result_source_ids_source
    ON result_source_ids(source_id, result_id);
