"""Active SIH projection policy and product-surface tests."""
from __future__ import annotations

import dataclasses
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import httpx
import pytest

from evidencegate.api.app import create_app
from evidencegate.api.projection import (
    POLICY_VERSION, ConfidenceBasis, SihAlertProjection, SihStatusProjection,
    StatusKind, project_result, project_results,
)
from evidencegate.domain.enums import (
    AnalyticUnavailableReason, EvidenceReadiness, IntegrationStatus, ResultType,
    ScientificStatus,
)
from evidencegate.domain.events import VisibilityProfile
from evidencegate.domain.quality import EvidenceQuality
from evidencegate.results.finalizer import result_id_for
from evidencegate.results.types import (
    AnalyticUnavailable, EvidencePayload, InsufficientEvidence, PluginStatus,
    PrerequisiteMissing, QualityDegraded, ResultStatusSnapshot, ReviewFinding,
)


BASE = datetime(2026, 9, 23, tzinfo=timezone.utc)


def result_for(
    lane: str, mechanism: str, *, suffix: str = "one",
    result_class=ReviewFinding, result_type: ResultType = ResultType.REVIEW_FINDING,
    evidence: dict | None = None,
):
    common = dict(
        result_id="", schema_version="3.0", result_type=result_type,
        created_time=BASE, lane_id=lane, plugin_id=f"provider.{lane}",
        plugin_version="1", analytic_version="1", governance_version="gov-1",
        entity_reference=f"entity:{suffix}", taxonomy=("network", "evidence", suffix),
        status_snapshot=ResultStatusSnapshot(
            ScientificStatus.EVIDENCE_CONSTRUCTION,
            IntegrationStatus.BASELINE_IMPLEMENTED, "gov-1",
            EvidenceReadiness.READY, result_type is ResultType.QUALITY_DEGRADED,
        ),
        claim_ceiling=f"FACTUAL_{suffix.upper()}_ONLY",
        evidence_items=(f"evidence:{suffix}",), missing_prerequisites=(),
        governing_ids=("decision-1",), quality_refs=("quality-1",),
        provenance_refs=("fixture:projection",), mechanism_id=mechanism,
        evidence=EvidencePayload.from_value(evidence or {"measurement": suffix}),
        source_observation_ids=("shared-observation",), source_ids=("source-1",),
        quality_snapshot=EvidenceQuality(), visibility_snapshot=VisibilityProfile(),
        state_version=1, config_hash="config-1", parser_refs=("parser-1",),
        model_refs=("sha256:model",) if lane == "dga.m1" else (),
    )
    if result_class is AnalyticUnavailable:
        result = result_class(
            **common, reason_code=AnalyticUnavailableReason.IMPLEMENTATION_NOT_READY,
        )
    else:
        result = result_class(**common)
    return dataclasses.replace(result, result_id=result_id_for(result))


@pytest.mark.parametrize(
    ("lane", "mechanism", "threat_class", "basis"),
    (
        ("ddos.udp_demand", "DDOS-A-UDP", "DDOS", ConfidenceBasis.STATISTICAL_SUPPORT),
        ("c2.r1", "C2-M1", "BOTNET_C2_BEACONING", ConfidenceBasis.STATISTICAL_SUPPORT),
        ("dns_tunnelling.t1", "DNS-T1", "DNS_TUNNELLING", ConfidenceBasis.OBSERVED_EVIDENCE),
        ("encrypted_session.enc_a", "ENC-A", "MALWARE_IN_ENCRYPTED_SESSION", ConfidenceBasis.OBSERVED_EVIDENCE),
        ("recon.h", "RECON-H", "RECONNAISSANCE", ConfidenceBasis.STATISTICAL_SUPPORT),
        ("unusual_transfer.m1", "CAT6-EX-M1", "DATA_EXFILTRATION", ConfidenceBasis.OBSERVED_EVIDENCE),
    ),
)
def test_non_dga_review_projection_has_basis_without_fake_number(
    lane, mechanism, threat_class, basis,
):
    source = result_for(lane, mechanism)
    before = dataclasses.asdict(source)
    (projected,) = project_result(source)
    assert isinstance(projected, SihAlertProjection)
    assert projected.threat_class == threat_class
    assert projected.confidence_basis is basis
    assert projected.confidence_score is None
    assert projected.severity.value == "REVIEW"
    assert projected.source_result_ids == (source.result_id,)
    assert projected.claim_ceiling == source.claim_ceiling
    assert projected.provenance_refs == source.provenance_refs
    assert projected.quality_refs == source.quality_refs
    assert projected.parser_refs == source.parser_refs
    assert dataclasses.asdict(source) == before
    assert projected == project_result(source)[0]
    other = result_for(lane, mechanism, suffix="other")
    assert projected.alert_id != project_result(other)[0].alert_id


def test_dga_model_score_is_labelled_and_not_an_attack_probability():
    source = result_for(
        "dga.m1", "DGA-A1-M1",
        evidence={"dga_labelled_lexical_resemblance_score": 0.9851716132182514},
    )
    first = project_result(source)[0]
    second = project_result(source)[0]
    assert isinstance(first, SihAlertProjection)
    assert first.alert_id == second.alert_id
    assert first.policy_version == POLICY_VERSION
    assert first.confidence_score == pytest.approx(0.9851716132182514)
    assert first.confidence_basis is ConfidenceBasis.MODEL_SCORE
    assert first.confidence_statement == (
        "DGA-labelled lexical resemblance score; not calibrated attack probability"
    )
    assert first.model_refs == source.model_refs


@pytest.mark.parametrize(
    ("result_class", "result_type", "kind", "priority"),
    (
        (QualityDegraded, ResultType.QUALITY_DEGRADED, StatusKind.QUALITY_NOTIFICATION, "ATTENTION"),
        (PrerequisiteMissing, ResultType.PREREQUISITE_MISSING, StatusKind.CAPABILITY_NOTIFICATION, "ATTENTION"),
        (InsufficientEvidence, ResultType.INSUFFICIENT_EVIDENCE, StatusKind.EVIDENCE_STATUS, "INFO"),
        (AnalyticUnavailable, ResultType.ANALYTIC_UNAVAILABLE, StatusKind.SYSTEM_CAPABILITY_STATUS, "ATTENTION"),
        (PluginStatus, ResultType.PLUGIN_STATUS, StatusKind.PLUGIN_STATUS, "INFO"),
    ),
)
def test_non_review_results_are_separate_status_items(result_class, result_type, kind, priority):
    source = result_for(
        "dns_tunnelling.t1", "DNS-T1", result_class=result_class,
        result_type=result_type,
    )
    (projected,) = project_result(source)
    assert isinstance(projected, SihStatusProjection)
    assert projected.status_kind is kind
    assert projected.priority.value == priority
    assert projected.status_id == project_result(source)[0].status_id
    assert projected.claim_ceiling == source.claim_ceiling
    serialized = projected.model_dump()
    assert "threat_class" not in serialized
    assert "confidence_score" not in serialized
    assert "severity" not in serialized


def test_one_observation_can_produce_multiple_unfused_projections():
    dns = result_for("dns_tunnelling.t1", "DNS-T1", suffix="dns")
    dga = result_for(
        "dga.m1", "DGA-A1-M1", suffix="dga",
        evidence={"dga_labelled_lexical_resemblance_score": 0.8},
    )
    projected = project_results([dns, dga])
    assert len(projected) == 2
    assert {item.threat_class for item in projected if isinstance(item, SihAlertProjection)} == {
        "DNS_TUNNELLING", "DGA",
    }
    assert len({item.alert_id for item in projected if isinstance(item, SihAlertProjection)}) == 2
    assert all(len(item.source_result_ids) == 1 for item in projected)
    assert {item.confidence_basis for item in projected} == {
        ConfidenceBasis.MODEL_SCORE, ConfidenceBasis.OBSERVED_EVIDENCE,
    }
    assert {item.claim_ceiling for item in projected} == {
        dns.claim_ceiling, dga.claim_ceiling,
    }


@asynccontextmanager
async def active_client(database):
    app = create_app(database)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test",
        ) as client:
            yield client, app.state.service


@pytest.mark.asyncio
async def test_active_endpoint_is_default_and_refresh_is_deterministic(tmp_path):
    async with active_client(tmp_path / "alerts.db") as (client, service):
        dga = result_for(
            "dga.m1", "DGA-A1-M1",
            evidence={"dga_labelled_lexical_resemblance_score": 0.9},
        )
        status = result_for(
            "dga.m1", "DGA-A1-M1", suffix="unavailable",
            result_class=AnalyticUnavailable,
            result_type=ResultType.ANALYTIC_UNAVAILABLE,
        )
        dns = result_for("dns_tunnelling.t1", "DNS-T1", suffix="dns")
        recon = result_for("recon.h", "RECON-H", suffix="recon")
        await service.persist_and_publish(dga)
        await service.persist_and_publish(status)
        await service.persist_and_publish(dns)
        await service.persist_and_publish(recon)
        first = (await client.get("/alerts")).json()
        second = (await client.get("/alerts")).json()
        assert first == second
        assert first["policy_status"] == "ACTIVE"
        assert first["policy_version"] == "SIH_ALERT_POLICY_V1"
        assert first["meaning_of_alert"] == "ANALYST_ATTENTION_RECORD"
        assert len(first["alerts"]) == 3
        assert len(first["status_items"]) == 1
        assert [item for item in first["alerts"] if item["source_result_ids"] == [dga.result_id]]
        family_response = (await client.get("/family-evidence")).json()
        dga_dns = next(view for view in family_response["family_views"] if view["family"] == "DGA + DNS")
        assert set(dga_dns["source_result_ids"]) == {dga.result_id, dns.result_id, status.result_id}
        assert len(dga_dns["findings"]) == 3
        investigation = (await client.get("/investigations")).json()
        assert len(investigation["links"]) == 1
        assert investigation["links"][0]["relation_types"] == ["SHARED_SOURCE_OBSERVATION"]
        before = (await client.get(f"/results/{dga.result_id}")).json()
        assert before["result_id"] == dga.result_id
        result_body = (await client.get(f"/results/{dga.result_id}")).json()
        assert result_body["result_id"] == dga.result_id
        runtime = (await client.get("/runtime")).json()
        assert runtime["alert_projection_available"] is True
        assert runtime["alert_policy_active"] is True
        assert runtime["alert_policy_version"] == POLICY_VERSION
        dashboard = await client.get("/")
        assert '<div id="root"></div>' in dashboard.text
        assert "/assets/" in dashboard.text


def test_alert_endpoint_is_present_by_default_and_explicitly_disableable():
    app = create_app(":memory:")
    assert "/alerts" in app.openapi()["paths"]
    disabled = create_app(":memory:", alerts_enabled=False)
    assert "/alerts" not in disabled.openapi()["paths"]
    assert "/family-evidence" in app.openapi()["paths"]
    assert "/investigations" in app.openapi()["paths"]
