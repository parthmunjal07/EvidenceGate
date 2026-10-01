from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta, timezone

import pytest

from evidencegate.correlation.contracts import (
    ClaimType,
    CorrelationFactKind,
    CorrelationFactSeed,
    DerivationBasis,
    EventInterval,
    EventTimeBasis,
    IdentityBasis,
    RelationPolicy,
    canonical_pair_id,
    validate_claim,
)
from evidencegate.correlation.engine import RELATION_POLICIES
from evidencegate.domain.enums import (
    EvidenceReadiness,
    IntegrationStatus,
    QualityState,
    ResultType,
    ScientificStatus,
    VisibilityCapability,
)
from evidencegate.domain.events import VisibilityProfile
from evidencegate.domain.quality import EvidenceQuality
from evidencegate.persistence.sqlite import SqliteWriter
from evidencegate.results.finalizer import canonical_result_content, result_id_for
from evidencegate.results.types import (
    EvidencePayload,
    ResultStatusSnapshot,
    ReviewFinding,
)


SCHEMA = "evidencegate/persistence/schema.sql"
NOW = datetime(2026, 9, 29, tzinfo=timezone.utc)


def make_result(
    lane: str,
    suffix: str,
    observations: tuple[str, ...],
    *,
    at: datetime = NOW,
    entity: str = "same-provider-reference",
    protocol: str = "tcp",
    quality: EvidenceQuality | None = None,
    visibility: VisibilityProfile | None = None,
) -> ReviewFinding:
    value = ReviewFinding(
        result_id="",
        schema_version="3.0",
        result_type=ResultType.REVIEW_FINDING,
        created_time=at,
        lane_id=lane,
        plugin_id=f"provider.{lane}",
        plugin_version="1",
        analytic_version="1",
        governance_version="gov-1",
        entity_reference=entity,
        taxonomy=("network", lane, "evidence"),
        status_snapshot=ResultStatusSnapshot(
            ScientificStatus.EVIDENCE_CONSTRUCTION,
            IntegrationStatus.BASELINE_IMPLEMENTED,
            "gov-1",
            EvidenceReadiness.READY,
            False,
        ),
        claim_ceiling="FACTUAL_EVIDENCE_ONLY",
        evidence_items=(f"measurement-{suffix}",),
        missing_prerequisites=(),
        governing_ids=("decision-1",),
        quality_refs=("quality:source",),
        provenance_refs=(f"source:{suffix}",),
        mechanism_id=f"mechanism.{lane}",
        evidence=EvidencePayload.from_value({"protocol": protocol, "suffix": suffix}),
        source_observation_ids=observations,
        source_ids=(f"capture:{suffix}",),
        quality_snapshot=quality or EvidenceQuality(),
        visibility_snapshot=visibility or VisibilityProfile(),
    )
    return dataclasses.replace(value, result_id=result_id_for(value))


async def drain(writer: SqliteWriter) -> int:
    total = 0
    while processed := await writer.process_correlation_outbox_batch(limit=500):
        total += processed
    return total


@pytest.mark.asyncio
async def test_clean_migration_adds_versioned_derived_tables_and_outbox(tmp_path):
    writer = SqliteWriter(tmp_path / "fresh.db", SCHEMA)
    writer.connect()
    tables = {
        row[0]
        for row in writer._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert {
        "correlation_facts",
        "correlation_candidates",
        "correlation_outbox",
    } <= tables
    assert (
        writer._conn.execute("SELECT COUNT(*) FROM schema_migrations WHERE version = 4").fetchone()[
            0
        ]
        == 1
    )
    writer.close()


@pytest.mark.asyncio
async def test_v4_migration_backfills_versioned_work_without_changing_source_results(tmp_path):
    database = tmp_path / "backfill.db"
    writer = SqliteWriter(database, SCHEMA)
    writer.connect()
    result = make_result("ddos.syn_state", "historical", ("obs-old",))
    await writer.write_result(result)
    source_before = writer._conn.execute(
        "SELECT result_id, content_hash FROM results WHERE result_id=?", (result.result_id,)
    ).fetchone()
    writer._conn.execute("DROP TABLE correlation_candidates")
    writer._conn.execute("DROP TABLE correlation_facts")
    writer._conn.execute("DROP TABLE correlation_outbox")
    writer._conn.execute("DELETE FROM schema_migrations WHERE version=4")
    writer._conn.commit()
    writer.close()

    migrated = SqliteWriter(database, SCHEMA)
    migrated.connect()
    pending = migrated._conn.execute(
        """SELECT source_result_id, source_result_hash, status
           FROM correlation_outbox"""
    ).fetchone()
    source_after = migrated._conn.execute(
        "SELECT result_id, content_hash FROM results WHERE result_id=?", (result.result_id,)
    ).fetchone()
    assert pending == (result.result_id, source_before[1], "PENDING")
    assert source_after == source_before
    migrated.close()


@pytest.mark.asyncio
async def test_failed_materialization_keeps_outbox_work_for_restart_retry(tmp_path, monkeypatch):
    database = tmp_path / "restart.db"
    writer = SqliteWriter(database, SCHEMA)
    writer.connect()
    result = make_result("ddos.syn_state", "restart", ("obs-restart",))
    await writer.write_result(result)

    def fail_lookup(_conn, _facts):
        raise RuntimeError("transient derivation failure")

    monkeypatch.setattr(writer, "_find_matching_facts", fail_lookup)
    with pytest.raises(RuntimeError, match="transient"):
        await writer.process_correlation_outbox_batch()
    assert (
        writer._conn.execute(
            "SELECT status FROM correlation_outbox WHERE source_result_id=?", (result.result_id,)
        ).fetchone()[0]
        == "PENDING"
    )
    assert writer._conn.execute("SELECT COUNT(*) FROM correlation_facts").fetchone()[0] == 0
    writer.close()

    monkeypatch.undo()
    restarted = SqliteWriter(database, SCHEMA)
    restarted.connect()
    assert await restarted.process_correlation_outbox_batch() == 1
    assert (
        restarted._conn.execute(
            "SELECT status FROM correlation_outbox WHERE source_result_id=?", (result.result_id,)
        ).fetchone()[0]
        == "COMPLETED"
    )
    assert restarted._conn.execute("SELECT COUNT(*) FROM correlation_facts").fetchone()[0] == 1
    restarted.close()


@pytest.mark.asyncio
async def test_exact_observation_materializes_precise_cross_family_pair_and_is_immutable(
    tmp_path,
):
    writer = SqliteWriter(tmp_path / "exact.db", SCHEMA)
    writer.connect()
    left = make_result("ddos.syn_state", "left", ("obs-shared",))
    right = make_result("recon.h", "right", ("obs-shared",), at=NOW + timedelta(days=2))
    for item in (left, right):
        await writer.write_result(item)
    before = {
        item.result_id: (
            result_id_for(item),
            canonical_result_content(item),
            writer._conn.execute(
                "SELECT content_hash FROM results WHERE result_id=?", (item.result_id,)
            ).fetchone()[0],
        )
        for item in (left, right)
    }

    assert await drain(writer) == 2
    candidates = await writer.list_correlation_candidates()
    assert len(candidates) == 1
    pair = candidates[0]
    assert (pair.left_result_id, pair.right_result_id) == tuple(
        sorted((left.result_id, right.result_id))
    )
    assert pair.source_observation_ids == ("obs-shared",)
    assert pair.matched_facts[0].reason.value == "EXACT_SHARED_SOURCE_OBSERVATION"
    assert pair.relation_policy is RelationPolicy.EXACT_OBSERVATION
    assert pair.pair_id == canonical_pair_id(
        pair.left_result_id, pair.right_result_id, pair.relation_policy_version
    )
    assert pair.status.value == "CANDIDATE_FOR_JOINT_REVIEW"
    assert pair.event_time_relationship.value == "NON_OVERLAPPING_INTERVALS"
    for item in (left, right):
        assert await writer.get_result(item.result_id) == item
        assert before[item.result_id] == (
            result_id_for(item),
            canonical_result_content(item),
            writer._conn.execute(
                "SELECT content_hash FROM results WHERE result_id=?", (item.result_id,)
            ).fetchone()[0],
        )
    assert writer._conn.execute("SELECT COUNT(*) FROM correlation_facts").fetchone()[0] == 2
    writer.close()


@pytest.mark.asyncio
async def test_different_observations_do_not_link_and_entity_protocol_or_time_are_not_joins(
    tmp_path,
):
    writer = SqliteWriter(tmp_path / "no-fallback.db", SCHEMA)
    writer.connect()
    left = make_result("ddos.syn_state", "left", ("obs-left",))
    right = make_result("recon.h", "right", ("obs-right",), at=NOW + timedelta(milliseconds=1))
    await writer.write_result(left)
    await writer.write_result(right)
    await drain(writer)
    assert await writer.list_correlation_candidates() == ()
    kinds = {
        row[0]
        for row in writer._conn.execute(
            "SELECT DISTINCT fact_kind FROM correlation_facts"
        ).fetchall()
    }
    assert kinds == {CorrelationFactKind.EXACT_OBSERVATION.value}
    writer.close()


@pytest.mark.asyncio
async def test_same_family_results_do_not_create_cross_family_pair(tmp_path):
    writer = SqliteWriter(tmp_path / "same-family.db", SCHEMA)
    writer.connect()
    await writer.write_result(make_result("recon.h", "one", ("obs-1",)))
    await writer.write_result(make_result("recon.v", "two", ("obs-1",)))
    await drain(writer)
    assert await writer.list_correlation_candidates() == ()
    writer.close()


@pytest.mark.asyncio
async def test_duplicate_outbox_delivery_and_reasons_are_idempotent_and_deterministic(tmp_path):
    writer = SqliteWriter(tmp_path / "idempotent.db", SCHEMA)
    writer.connect()
    left = make_result("ddos.syn_state", "left", ("obs-b", "obs-a"))
    right = make_result("recon.h", "right", ("obs-a", "obs-b"))
    await writer.write_result(left)
    await writer.write_result(right)
    assert await writer.process_correlation_outbox_batch(limit=1) == 1
    assert await writer.process_correlation_outbox_batch(limit=500) == 1
    first = (await writer.list_correlation_candidates())[0]
    assert first.source_observation_ids == ("obs-a", "obs-b")
    assert len(first.matched_facts) == 2
    assert await writer.process_correlation_outbox_batch(limit=500) == 0
    assert await writer.write_result(right) is False
    assert (await writer.list_correlation_candidates())[0] == first
    assert writer._conn.execute("SELECT COUNT(*) FROM correlation_facts").fetchone()[0] == 4
    assert writer._conn.execute("SELECT COUNT(*) FROM correlation_candidates").fetchone()[0] == 1
    writer.close()


@pytest.mark.asyncio
async def test_degraded_visibility_and_quality_are_preserved_in_derived_pair(tmp_path):
    writer = SqliteWriter(tmp_path / "degraded.db", SCHEMA)
    writer.connect()
    left_quality = EvidenceQuality(packet_loss=QualityState.DEGRADED)
    left_visibility = VisibilityProfile(unavailable=frozenset({VisibilityCapability.REVERSE_FACTS}))
    left = make_result(
        "ddos.syn_state",
        "one-way",
        ("obs-1",),
        quality=left_quality,
        visibility=left_visibility,
    )
    right = make_result("recon.h", "peer", ("obs-1",))
    await writer.write_result(left)
    await writer.write_result(right)
    await drain(writer)
    pair = (await writer.list_correlation_candidates())[0]
    left_side = pair.left_result_id == left.result_id
    assert (pair.left_quality if left_side else pair.right_quality) == left_quality
    assert (pair.left_visibility if left_side else pair.right_visibility) == left_visibility
    writer.close()


def test_cross_time_policies_are_disabled_and_claim_guard_rejects_forbidden_claims():
    assert RELATION_POLICIES[RelationPolicy.EXACT_OBSERVATION].enabled is True
    for policy in RelationPolicy:
        config = RELATION_POLICIES[policy]
        if policy is not RelationPolicy.EXACT_OBSERVATION:
            assert config.enabled is False
            assert config.window_seconds is None
    with pytest.raises(ValueError, match="prohibited"):
        validate_claim(ClaimType.SAME_ATTACKER)
    with pytest.raises(TypeError, match="ClaimType"):
        validate_claim("same attacker")  # type: ignore[arg-type]


def test_typed_entity_fact_requires_explicit_identity_basis():
    with pytest.raises(ValueError, match="explicit typed identity"):
        CorrelationFactSeed(
            fact_kind=CorrelationFactKind.SCOPED_ENTITY,
            normalized_value="192.0.2.10",
            namespace="network.host",
            scope="tenant:1",
            role="peer",
            identity_basis=IdentityBasis.EXACT_SOURCE_OBSERVATION_ID,
            event_interval=EventInterval(NOW, NOW, EventTimeBasis.RESULT_EVENT_TIME),
            available_time=None,
            source_result_id="result:test",
            source_result_hash="hash",
            source_observation_ids=("obs-1",),
            visibility_basis=VisibilityProfile(),
            quality_basis=EvidenceQuality(),
            source_fields=("typed_peer",),
            derivation_basis=DerivationBasis.EXPLICIT_TYPED_SOURCE_FIELD,
            normalizer_version="typed-entity-v1",
        )


@pytest.mark.asyncio
async def test_indexed_lookup_avoids_global_pair_enumeration(tmp_path):
    writer = SqliteWriter(tmp_path / "indexed.db", SCHEMA)
    writer.connect()
    for index in range(80):
        await writer.write_result(
            make_result("ddos.syn_state", f"d{index}", (f"unrelated-{index}",))
        )
        await writer.write_result(
            make_result("recon.h", f"r{index}", (f"unrelated-{index + 1000}",))
        )
    await writer.write_result(make_result("ddos.syn_state", "match-d", ("one-shared",)))
    await writer.write_result(make_result("recon.h", "match-r", ("one-shared",)))
    await drain(writer)
    plan = writer._conn.execute(
        """EXPLAIN QUERY PLAN SELECT fact_id FROM correlation_facts
           WHERE fact_kind='EXACT_OBSERVATION'
             AND namespace='evidencegate.source_observation'
             AND scope='source_observation_id' AND role='observed'
             AND normalized_value=?""",
        ("one-shared",),
    ).fetchall()
    assert any("ix_correlation_facts_lookup" in row[-1] for row in plan)
    assert len(await writer.list_correlation_candidates()) == 1
    writer.close()
