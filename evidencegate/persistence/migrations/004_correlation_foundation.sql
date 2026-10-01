-- CORR-04A derived, versioned correlation facts and exact Result pairs.
-- Existing Results are immutable; this migration only queues derivation work.

CREATE TABLE correlation_facts (
    fact_id                 TEXT PRIMARY KEY,
    source_result_id        TEXT NOT NULL,
    source_result_hash      TEXT NOT NULL,
    fact_kind               TEXT NOT NULL CHECK (fact_kind IN (
        'EXACT_OBSERVATION', 'SCOPED_ENTITY', 'PEER', 'DOMAIN',
        'OBSERVED_DNS_ANSWER', 'SERVICE', 'SESSION', 'TARGET_SERVICE',
        'PROTOCOL_CONTEXT'
    )),
    normalized_value        TEXT NOT NULL,
    namespace               TEXT NOT NULL,
    scope                   TEXT NOT NULL,
    role                    TEXT NOT NULL,
    identity_basis          TEXT NOT NULL,
    event_interval_start    TEXT NOT NULL,
    event_interval_end      TEXT NOT NULL,
    event_time_basis        TEXT NOT NULL,
    available_time          TEXT,
    source_observation_ids  TEXT NOT NULL,
    visibility_basis        TEXT NOT NULL,
    quality_basis           TEXT NOT NULL,
    source_fields           TEXT NOT NULL,
    derivation_basis        TEXT NOT NULL,
    normalizer_version      TEXT NOT NULL,
    derivation_version      TEXT NOT NULL,
    FOREIGN KEY(source_result_id) REFERENCES results(result_id),
    UNIQUE(source_result_id, source_result_hash, derivation_version,
           fact_kind, namespace, scope, role, normalized_value)
);

CREATE INDEX ix_correlation_facts_lookup
    ON correlation_facts(fact_kind, namespace, scope, role, normalized_value);
CREATE INDEX ix_correlation_facts_event_interval
    ON correlation_facts(event_interval_start, event_interval_end);
CREATE INDEX ix_correlation_facts_source
    ON correlation_facts(source_result_id, source_result_hash);

CREATE TABLE correlation_candidates (
    pair_id                     TEXT PRIMARY KEY,
    left_result_id              TEXT NOT NULL,
    right_result_id             TEXT NOT NULL,
    left_source_result_hash     TEXT NOT NULL,
    right_source_result_hash    TEXT NOT NULL,
    relation_policy             TEXT NOT NULL,
    relation_policy_version     TEXT NOT NULL,
    matched_reasons             TEXT NOT NULL,
    matched_fact_ids            TEXT NOT NULL,
    source_observation_ids      TEXT NOT NULL,
    left_event_interval_start   TEXT NOT NULL,
    left_event_interval_end     TEXT NOT NULL,
    left_event_time_basis       TEXT NOT NULL,
    right_event_interval_start  TEXT NOT NULL,
    right_event_interval_end    TEXT NOT NULL,
    right_event_time_basis      TEXT NOT NULL,
    event_time_relationship     TEXT NOT NULL,
    left_visibility             TEXT NOT NULL,
    right_visibility            TEXT NOT NULL,
    left_quality                TEXT NOT NULL,
    right_quality               TEXT NOT NULL,
    left_source_provenance      TEXT NOT NULL,
    right_source_provenance     TEXT NOT NULL,
    status                      TEXT NOT NULL,
    claim_guard                 TEXT NOT NULL,
    FOREIGN KEY(left_result_id) REFERENCES results(result_id),
    FOREIGN KEY(right_result_id) REFERENCES results(result_id),
    UNIQUE(left_result_id, right_result_id, relation_policy, relation_policy_version),
    CHECK(left_result_id < right_result_id)
);

CREATE INDEX ix_correlation_candidates_left
    ON correlation_candidates(left_result_id, pair_id);
CREATE INDEX ix_correlation_candidates_right
    ON correlation_candidates(right_result_id, pair_id);
CREATE INDEX ix_correlation_candidates_policy
    ON correlation_candidates(relation_policy, relation_policy_version, pair_id);

CREATE TABLE correlation_outbox (
    outbox_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source_result_id    TEXT NOT NULL,
    source_result_hash  TEXT NOT NULL,
    derivation_version  TEXT NOT NULL,
    status              TEXT NOT NULL CHECK (status IN ('PENDING', 'COMPLETED')),
    created_at           TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at         TEXT,
    FOREIGN KEY(source_result_id) REFERENCES results(result_id),
    UNIQUE(source_result_id, source_result_hash, derivation_version)
);

CREATE INDEX ix_correlation_outbox_pending
    ON correlation_outbox(status, outbox_id);

-- Re-derive historical facts asynchronously under a separately versioned
-- contract. No source Result identity or payload is changed.
INSERT INTO correlation_outbox (
    source_result_id, source_result_hash, derivation_version, status
)
SELECT result_id, content_hash, 'corr-04a-fact-v1', 'PENDING'
FROM results
WHERE content_hash IS NOT NULL;
