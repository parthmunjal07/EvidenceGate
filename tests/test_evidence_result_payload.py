"""M6.5 structured evidence, mechanism provenance, and schema-v3 tests."""

import dataclasses
import hashlib
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from evidencegate.domain.enums import (
    EvidenceReadiness,
    QualityState,
    ResultType,
    ScientificStatus,
    VisibilityCapability,
)
from evidencegate.domain.events import VisibilityProfile
from evidencegate.domain.governance import LaneGovernance
from evidencegate.domain.quality import EvidenceQuality
from evidencegate.persistence.sqlite import ResultIdentityConflict, SqliteWriter
from evidencegate.plugins.providers.registry import build_mvp_provider_registry
from evidencegate.plugins.scaffolds.basic_scaffold import BasicScaffoldPlugin
from evidencegate.results.finalizer import (
    ResultEmissionContext,
    ResultFinalizer,
    canonical_result_content,
    result_id_for,
)
from evidencegate.results.types import (
    EvidencePayload,
    ResultDraft,
    ResultStatusSnapshot,
    ReviewFinding,
)


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
SCHEMA = "evidencegate/persistence/schema.sql"


def manifest(**changes):
    defaults = dict(
        plugin_id="evidence-plugin",
        plugin_version="plugin-1",
        analytic_version="analytic-1",
        mechanism_id="mechanism.alpha",
        taxonomy=("network", "evidence", "measurement"),
        governing_claim_ids=("claim-1",),
        governing_decision_ids=("decision-1",),
        allowed_result_types=(ResultType.REVIEW_FINDING,),
    )
    defaults.update(changes)
    return dataclasses.replace(BasicScaffoldPlugin().manifest(), **defaults)


def governance():
    return LaneGovernance(
        analytic_lane="lane-evidence",
        scientific_status=ScientificStatus.EVIDENCE_CONSTRUCTION,
        scientific_phase="plumbing",
        scientific_blockers=(),
        claim_ceiling="REVIEW_ONLY",
        governance_version="gov-1",
        effective_at=NOW,
        allowed_result_types=(ResultType.REVIEW_FINDING,),
        ingest_permitted=True,
    )


def context(**changes):
    defaults = dict(
        lane_id="lane-evidence",
        causal_result_time=NOW,
        quality_refs=("quality:1",),
        provenance_refs=("provenance:1",),
        readiness=EvidenceReadiness.READY,
        quality_degraded=False,
        trigger_reference="obs-1",
        source_observation_ids=("obs-1",),
        source_ids=("source-1",),
        quality_snapshot=EvidenceQuality(
            packet_loss=QualityState.CLEAR,
            sampling=QualityState.DEGRADED,
        ),
        visibility_snapshot=VisibilityProfile(
            available=frozenset({VisibilityCapability.FORWARD_FACTS}),
            unavailable=frozenset({VisibilityCapability.REVERSE_FACTS}),
        ),
        state_version=7,
    )
    defaults.update(changes)
    return ResultEmissionContext(**defaults)


def draft(evidence=None, **changes):
    defaults = dict(
        result_type=ResultType.REVIEW_FINDING,
        entity_reference="entity-1",
        evidence_items=("fact:outer-flow",),
        missing_prerequisites=("reverse-handshake",),
        evidence={} if evidence is None else evidence,
    )
    defaults.update(changes)
    return ResultDraft(**defaults)


def finalize(*, evidence=None, manifest_value=None, context_value=None, **draft_changes):
    return ResultFinalizer.finalize(
        draft(evidence, **draft_changes),
        manifest_value or manifest(),
        governance(),
        context_value or context(),
    )


def test_evidence_payload_is_canonical_and_deeply_immutable() -> None:
    original = {
        "peer": "203.0.113.8",
        "summary": {"median_iat_ms": 4020.0, "states": [True, None, 12]},
    }
    result = finalize(evidence=original)
    reordered = finalize(
        evidence={
            "summary": {"states": [True, None, 12], "median_iat_ms": 4020.0},
            "peer": "203.0.113.8",
        }
    )

    assert result.evidence == reordered.evidence
    assert result.evidence.canonical_json == (
        '{"peer":"203.0.113.8","summary":{"median_iat_ms":4020.0,"states":[true,null,12]}}'
    )
    original["summary"]["states"].append("mutated")
    detached = result.evidence.to_value()
    detached["peer"] = "mutated"
    assert result.evidence == reordered.evidence


def test_evidence_enum_and_datetime_serialization_is_stable() -> None:
    offset_time = NOW.astimezone(timezone(timedelta(hours=5, minutes=30)))
    first = EvidencePayload.from_value(
        {
            "kind": ResultType.REVIEW_FINDING,
            "when": NOW,
        }
    )
    second = EvidencePayload.from_value(
        {
            "when": offset_time,
            "kind": ResultType.REVIEW_FINDING,
        }
    )
    assert first == second
    assert first.to_value() == {
        "kind": "REVIEW_FINDING",
        "when": "2026-01-01T00:00:00.000000+00:00",
    }


@pytest.mark.parametrize(
    "unsupported",
    [
        float("nan"),
        float("inf"),
        {"set"},
        object(),
        {1: "not-a-json-key"},
        datetime(2026, 1, 1),
    ],
)
def test_unsupported_or_non_finite_evidence_is_rejected(unsupported) -> None:
    value = unsupported if isinstance(unsupported, dict) else {"value": unsupported}
    with pytest.raises((TypeError, ValueError)):
        finalize(evidence=value)


def test_result_identity_tracks_all_scientific_and_runtime_provenance() -> None:
    baseline = finalize(evidence={"interval_count": 12})
    assert baseline == finalize(evidence={"interval_count": 12})
    variants = (
        finalize(evidence={"interval_count": 13}),
        finalize(
            evidence={"interval_count": 12}, manifest_value=manifest(mechanism_id="mechanism.beta")
        ),
        finalize(
            evidence={"interval_count": 12},
            context_value=context(source_observation_ids=("obs-2",)),
        ),
        finalize(
            evidence={"interval_count": 12},
            context_value=context(
                visibility_snapshot=VisibilityProfile(
                    available=frozenset({VisibilityCapability.REVERSE_FACTS})
                )
            ),
        ),
        finalize(
            evidence={"interval_count": 12},
            context_value=context(
                quality_snapshot=EvidenceQuality(packet_loss=QualityState.DEGRADED)
            ),
        ),
        finalize(evidence={"interval_count": 12}, context_value=context(state_version=8)),
    )
    assert all(item.result_id != baseline.result_id for item in variants)


def test_runtime_injects_mechanism_sources_quality_visibility_and_state() -> None:
    quality = EvidenceQuality(
        packet_loss=QualityState.DEGRADED,
        sampling=QualityState.CLEAR,
        parser=QualityState.UNKNOWN,
        capture_gap=QualityState.CLEAR,
    )
    visibility = VisibilityProfile(
        available=frozenset({VisibilityCapability.FORWARD_FACTS}),
        unavailable=frozenset({VisibilityCapability.REVERSE_FACTS}),
        degraded=frozenset({VisibilityCapability.FLOW_FACTS}),
    )
    result = finalize(
        evidence={"bytes": 42},
        source_observation_ids=("obs-2", "obs-1", "obs-2"),
        context_value=context(
            source_observation_ids=("obs-1",),
            source_ids=("source-1", "source-1", "source-2"),
            quality_snapshot=quality,
            visibility_snapshot=visibility,
            state_version=9,
        ),
    )

    assert result.schema_version == "3.0"
    assert result.mechanism_id == "mechanism.alpha"
    assert result.source_observation_ids == ("obs-1", "obs-2")
    assert result.source_ids == ("source-1", "source-2")
    assert result.quality_snapshot == quality
    assert result.visibility_snapshot == visibility
    assert result.state_version == 9
    assert result.model_refs == ()


def test_plugin_cannot_forge_runtime_owned_metadata() -> None:
    base = dict(
        result_type=ResultType.REVIEW_FINDING,
        entity_reference="entity",
        evidence_items=(),
        missing_prerequisites=(),
    )
    for field_name in (
        "plugin_id",
        "mechanism_id",
        "plugin_version",
        "analytic_version",
        "governance_version",
        "claim_ceiling",
        "taxonomy",
        "source_ids",
        "quality_snapshot",
        "visibility_snapshot",
        "state_version",
        "config_hash",
        "parser_refs",
        "model_refs",
    ):
        with pytest.raises(TypeError):
            ResultDraft(**base, **{field_name: "forged"})

    with pytest.raises(ValueError, match="mechanism_id"):
        finalize(manifest_value=manifest(mechanism_id=None))


@pytest.mark.asyncio
async def test_v3_persistence_round_trip_and_duplicate_integrity(tmp_path) -> None:
    result = finalize(
        evidence={"interval_count": 12, "median_iat_ms": 4020},
        context_value=context(
            config_hash="sha256:config",
            parser_refs=("parser:v1", "parser:v1", "parser:v2"),
            model_refs=("model:approved-v1",),
        ),
    )
    writer = SqliteWriter(tmp_path / "v3.db", SCHEMA)
    writer.connect()
    await writer.write_result(result)
    await writer.write_result(result)

    assert await writer.get_result(result.result_id) == result
    assert (
        writer._conn.execute(
            "SELECT COUNT(*) FROM results WHERE result_id=?", (result.result_id,)
        ).fetchone()[0]
        == 1
    )
    assert (
        writer._conn.execute(
            "SELECT evidence_json FROM results WHERE result_id=?", (result.result_id,)
        ).fetchone()[0]
        == result.evidence.canonical_json
    )

    divergent = dataclasses.replace(
        result, evidence=EvidencePayload.from_value({"interval_count": 99})
    )
    with pytest.raises(ResultIdentityConflict):
        await writer.write_result(divergent)
    writer.close()


@pytest.mark.asyncio
async def test_v2_to_v3_migration_preserves_existing_row_and_identity(tmp_path) -> None:
    database = tmp_path / "v2.db"
    legacy = sqlite3.connect(database)
    legacy.executescript(open(SCHEMA, encoding="utf-8").read())
    migration = open(
        "evidencegate/persistence/migrations/002_results_v2.sql", encoding="utf-8"
    ).read()
    legacy.executescript(
        "BEGIN;\n" + migration + "\nINSERT INTO schema_migrations(version, applied_at) "
        "VALUES(2, CURRENT_TIMESTAMP);\nCOMMIT;"
    )
    v2 = ReviewFinding(
        result_id="",
        schema_version="2.0",
        result_type=ResultType.REVIEW_FINDING,
        created_time=NOW,
        lane_id="legacy-lane",
        plugin_id="legacy-plugin",
        plugin_version="1",
        analytic_version="1",
        governance_version="gov-1",
        entity_reference="legacy-entity",
        taxonomy=("A", "B", "C"),
        status_snapshot=ResultStatusSnapshot(
            ScientificStatus.EVIDENCE_CONSTRUCTION,
            BasicScaffoldPlugin().manifest().integration_status,
            "gov-1",
            EvidenceReadiness.READY,
            False,
        ),
        claim_ceiling="REVIEW_ONLY",
        evidence_items=(),
        missing_prerequisites=(),
        governing_ids=(),
        quality_refs=(),
        provenance_refs=(),
    )
    v2 = dataclasses.replace(v2, result_id=result_id_for(v2))
    content_hash = hashlib.sha256(canonical_result_content(v2).encode()).hexdigest()
    legacy.execute(
        """INSERT INTO results (
            result_id, content_hash, schema_version, result_type, created_time,
            lane_id, plugin_id, plugin_version, analytic_version, governance_version,
            entity_reference, taxonomy_1, taxonomy_2, taxonomy_3,
            scientific_status, integration_status, readiness, quality_degraded,
            claim_ceiling
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            v2.result_id,
            content_hash,
            v2.schema_version,
            v2.result_type.value,
            v2.created_time.isoformat(timespec="microseconds"),
            v2.lane_id,
            v2.plugin_id,
            v2.plugin_version,
            v2.analytic_version,
            v2.governance_version,
            v2.entity_reference,
            *v2.taxonomy,
            v2.status_snapshot.scientific_status.value,
            v2.status_snapshot.integration_status.value,
            v2.status_snapshot.readiness.value,
            0,
            v2.claim_ceiling,
        ),
    )
    legacy.commit()
    legacy.close()

    writer = SqliteWriter(database, SCHEMA)
    writer.connect()
    stored = writer._conn.execute(
        "SELECT result_id, content_hash, mechanism_id, evidence_json FROM results"
    ).fetchone()
    assert stored == (v2.result_id, content_hash, None, None)
    assert await writer.get_result(v2.result_id) == v2
    assert (
        writer._conn.execute("SELECT COUNT(*) FROM schema_migrations WHERE version=3").fetchone()[0]
        == 1
    )
    writer.close()


def test_default_registry_has_no_remaining_provider_shell() -> None:
    plugins, _ = build_mvp_provider_registry(NOW)
    assert "dga" not in plugins and "dga.m1" in plugins
    assert all(plugin.manifest().mechanism_id is not None for plugin in plugins.values())
