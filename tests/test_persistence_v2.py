"""M5-02 immutable-result SQLite repository tests."""
import dataclasses
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from evidencegate.domain.enums import AnalyticUnavailableReason, EvidenceReadiness, IntegrationStatus, ResultType, ScientificStatus
from evidencegate.persistence.sqlite import PersistenceError, ResultIdentityConflict, SqliteWriter
from evidencegate.results.finalizer import result_id_for
from evidencegate.results.types import AnalyticUnavailable, CorrelationFinding, InsufficientEvidence, PluginStatus, PrerequisiteMissing, QualityDegraded, ResultDraft, ResultStatusSnapshot, ReviewFinding, ThreatAlert


SCHEMA = "evidencegate/persistence/schema.sql"


def make_result(cls=ReviewFinding, *, at=None, lane="lane-a", suffix="", **extra):
    result_type = next(kind for kind, candidate in {
        ResultType.THREAT_ALERT: ThreatAlert, ResultType.REVIEW_FINDING: ReviewFinding,
        ResultType.ANALYTIC_UNAVAILABLE: AnalyticUnavailable, ResultType.PREREQUISITE_MISSING: PrerequisiteMissing,
        ResultType.INSUFFICIENT_EVIDENCE: InsufficientEvidence, ResultType.QUALITY_DEGRADED: QualityDegraded,
        ResultType.PLUGIN_STATUS: PluginStatus, ResultType.CORRELATION_FINDING: CorrelationFinding,
    }.items() if candidate is cls)
    result = cls(result_id="", schema_version="2.0", result_type=result_type,
        created_time=at or datetime(2026, 1, 1, tzinfo=timezone.utc), lane_id=lane,
        plugin_id="plugin-a", plugin_version="1.0", analytic_version="1.0", governance_version="gov-1",
        entity_reference="entity" + suffix, taxonomy=("A", "B", "C"),
        status_snapshot=ResultStatusSnapshot(ScientificStatus.EVIDENCE_CONSTRUCTION, IntegrationStatus.RUNTIME_SCAFFOLD_READY, "gov-1", EvidenceReadiness.READY, False),
        claim_ceiling="REVIEW_ONLY", evidence_items=("ev-1", "ev-2"), missing_prerequisites=("need-1", "need-2"),
        governing_ids=("claim-1", "decision-1"), quality_refs=("quality-1", "quality-2"),
        provenance_refs=("provenance-1", "provenance-2"), **extra)
    return dataclasses.replace(result, result_id=result_id_for(result))


@pytest.mark.asyncio
async def test_fresh_database_applies_v2_and_preserves_every_tuple(tmp_path):
    writer = SqliteWriter(tmp_path / "fresh.db", SCHEMA)
    writer.connect()
    result = make_result(evidence_interval=(datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2026, 1, 1, 1, tzinfo=timezone.utc)))
    await writer.write_result(result)
    assert await writer.get_result(result.result_id) == result
    assert writer._conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert writer._conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    assert writer._conn.execute("SELECT COUNT(*) FROM schema_migrations WHERE version=2").fetchone()[0] == 1
    writer.close()


@pytest.mark.asyncio
async def test_all_final_subtypes_round_trip(tmp_path):
    writer = SqliteWriter(tmp_path / "subtypes.db", SCHEMA); writer.connect()
    review = make_result(ReviewFinding, suffix="review")
    results = [
        make_result(ThreatAlert, confidence="HIGH", severity="LOW"), review,
        make_result(AnalyticUnavailable, suffix="unavailable", reason_code=AnalyticUnavailableReason.GOVERNANCE_DISABLED),
        make_result(PrerequisiteMissing, suffix="prereq"), make_result(InsufficientEvidence, suffix="insufficient"),
        make_result(QualityDegraded, suffix="quality"), make_result(PluginStatus, suffix="status"),
    ]
    for result in results:
        await writer.write_result(result)
        assert await writer.get_result(result.result_id) == result
    correlation = make_result(CorrelationFinding, suffix="correlation", linked_result_ids=(review.result_id,))
    await writer.write_result(correlation)
    assert await writer.get_result(correlation.result_id) == correlation
    writer.close()


@pytest.mark.asyncio
async def test_identity_duplicates_invalid_ids_and_atomic_child_failure(tmp_path, monkeypatch):
    writer = SqliteWriter(tmp_path / "identity.db", SCHEMA); writer.connect()
    result = make_result()
    await writer.write_result(result)
    await writer.write_result(result)
    assert writer._conn.execute("SELECT COUNT(*) FROM evidence_items WHERE result_id=?", (result.result_id,)).fetchone()[0] == 2
    divergent = dataclasses.replace(result, entity_reference="changed")
    with pytest.raises(ResultIdentityConflict):
        await writer.write_result(divergent)
    invalid = dataclasses.replace(make_result(suffix="invalid"), result_id="result:not-canonical")
    with pytest.raises(ResultIdentityConflict):
        await writer.write_result(invalid)
    pending = make_result(suffix="rollback")
    def fail_children(*_args):
        raise RuntimeError("child failure")
    monkeypatch.setattr(writer, "_insert_children", fail_children)
    with pytest.raises(RuntimeError, match="child failure"):
        await writer.write_result(pending)
    assert writer._conn.execute("SELECT COUNT(*) FROM results WHERE result_id=?", (pending.result_id,)).fetchone()[0] == 0
    writer.close()


@pytest.mark.asyncio
async def test_v1_migration_is_idempotent_and_hashless_collision_is_rejected(tmp_path):
    db = tmp_path / "legacy.db"
    # A genuine v1 schema is initialized before the v2 repository connects.
    legacy = sqlite3.connect(db)
    legacy.executescript(open(SCHEMA, encoding="utf-8").read())
    result = make_result()
    legacy.execute("INSERT INTO results (result_id, result_type, created_time, entity_reference, plugin_version, analytic_version) VALUES (?, 'REVIEW_FINDING', '2020-01-01T00:00:00+00:00', 'legacy', '1', '1')", (result.result_id,))
    legacy.commit(); legacy.close()
    writer = SqliteWriter(db, SCHEMA); writer.connect()
    assert writer._conn.execute("SELECT COUNT(*) FROM results").fetchone()[0] == 1
    with pytest.raises(ResultIdentityConflict):
        await writer.write_result(result)
    writer.close()
    writer = SqliteWriter(db, SCHEMA); writer.connect()
    assert writer._conn.execute("SELECT COUNT(*) FROM schema_migrations WHERE version=2").fetchone()[0] == 1
    await writer.write_result(make_result(suffix="new"))
    writer.close()


@pytest.mark.asyncio
async def test_indexed_filters_and_cursor_pagination(tmp_path):
    writer = SqliteWriter(tmp_path / "listing.db", SCHEMA); writer.connect()
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    results = [make_result(at=base + timedelta(seconds=offset), suffix=f"{offset}-{index}", lane="lane-a" if index != 1 else "lane-b") for index, offset in enumerate((0, 1, 1))]
    for result in results:
        await writer.write_result(result)
    page_one = await writer.list_results(limit=2)
    page_two = await writer.list_results(limit=2, cursor=writer.cursor_for(page_one[-1]))
    assert page_one + page_two == tuple(sorted(results, key=lambda r: (r.created_time, r.result_id), reverse=True))
    assert await writer.list_results(limit=10, lane_id="lane-b") == (results[1],)
    assert await writer.list_results(limit=10, result_type=ResultType.REVIEW_FINDING) == tuple(sorted(results, key=lambda r: (r.created_time, r.result_id), reverse=True))
    assert await writer.get_result("does-not-exist") is None
    with pytest.raises(TypeError):
        await writer.write_result(ResultDraft(ResultType.REVIEW_FINDING, "e", (), ()))
    writer.close()
    with pytest.raises(PersistenceError):
        await writer.get_result(results[0].result_id)
