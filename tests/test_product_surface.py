"""M12 durable API, bounded live stream, replay, and dashboard contracts."""
from __future__ import annotations

import asyncio
import dataclasses
import re
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

from evidencegate.api.app import create_app, sse_encode
from evidencegate.api.models import ResultNotification, StreamGap
from evidencegate.domain.enums import (
    EvidenceReadiness, IntegrationStatus, ResultType, ScientificStatus,
)
from evidencegate.domain.events import VisibilityProfile
from evidencegate.domain.quality import EvidenceQuality
from evidencegate.results.finalizer import result_id_for
from evidencegate.results.types import EvidencePayload, ResultStatusSnapshot, ReviewFinding


BASE = datetime(2026, 9, 22, tzinfo=timezone.utc)


def make_result(
    suffix: str, *, at: datetime | None = None, lane: str = "dns_tunnelling.t1",
    mechanism: str = "DNS-T1", source: str = "source-a",
) -> ReviewFinding:
    result = ReviewFinding(
        result_id="", schema_version="3.0", result_type=ResultType.REVIEW_FINDING,
        created_time=at or BASE, lane_id=lane, plugin_id=f"provider.{lane}",
        plugin_version="1.0", analytic_version="1.0", governance_version="gov-1",
        entity_reference=f"entity-{suffix}", taxonomy=("Network", "Evidence", suffix),
        status_snapshot=ResultStatusSnapshot(
            ScientificStatus.EVIDENCE_CONSTRUCTION,
            IntegrationStatus.BASELINE_IMPLEMENTED, "gov-1",
            EvidenceReadiness.READY, False,
        ),
        claim_ceiling="FACTUAL_EVIDENCE_ONLY", evidence_items=(f"item-{suffix}",),
        missing_prerequisites=(), governing_ids=("decision-1",),
        quality_refs=("quality-1",), provenance_refs=("fixture:bounded",),
        mechanism_id=mechanism,
        evidence=EvidencePayload.from_value({"measurement": suffix}),
        source_observation_ids=(f"observation-{suffix}",), source_ids=(source,),
        quality_snapshot=EvidenceQuality(), visibility_snapshot=VisibilityProfile(),
        state_version=1, config_hash="config-1", parser_refs=("parser-1",),
        model_refs=(),
    )
    return dataclasses.replace(result, result_id=result_id_for(result))


@asynccontextmanager
async def client_for(database: Path, **kwargs):
    app = create_app(database, **kwargs)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test",
        ) as client:
            yield client, app.state.service


@pytest.mark.asyncio
async def test_empty_database_health_runtime_and_openapi(tmp_path):
    async with client_for(tmp_path / "empty.db") as (client, _service):
        assert (await client.get("/health")).json() == {
            "status": "ok", "database": "connected",
        }
        assert (await client.get("/results")).json() == {
            "results": [], "next_cursor": None, "sync_cursor": None,
        }
        runtime = (await client.get("/runtime")).json()
        assert runtime["default_target_count"] == 16
        assert runtime["database_status"] == "connected"
        assert runtime["active_lane_ids"] == [
            "ddos.syn_state", "ddos.udp_demand", "ddos.reflection_victim",
            "ddos.source_diversity", "ddos.icmp_demand", "ddos.fragment_demand",
            "ddos.connection_churn", "c2.r1", "dga.m1",
            "dns_tunnelling.t1", "encrypted_session.enc_a", "recon.h",
            "recon.v", "recon.2d", "recon.tcp", "unusual_transfer.m1",
        ]
        assert runtime["alert_policy_active"] is True
        assert runtime["alert_policy_version"] == "SIH_ALERT_POLICY_V1"
        dga = next(item for item in runtime["targets"] if item["lane_id"] == "dga.m1")
        assert dga == {
            "lane_id": "dga.m1", "mechanism_id": "DGA-A1-M1",
            "implementation": "ACTIVE_LEXICAL_MODEL_LANE",
        }
        dga_family = next(item for item in runtime["family_status"] if item["family"] == "DGA")
        assert dga_family["status"] == "ACTIVE LANE — MODEL UNAVAILABLE"
        assert runtime["dga_model_readiness"] == "ARTIFACT_MISSING"
        schema = (await client.get("/openapi.json")).json()
        assert {"/health", "/results", "/results/{result_id}", "/alerts", "/events", "/replay", "/replay/status", "/runtime"} <= set(schema["paths"])
        dashboard = await client.get("/")
        assert dashboard.status_code == 200
        assert '<div id="root"></div>' in dashboard.text
        assert "/assets/" in dashboard.text
        assets = re.findall(r'(?:src|href)="(/assets/[^"]+)"', dashboard.text)
        assert len(assets) >= 2
        built_assets = [await client.get(path) for path in assets]
        assert all(asset.status_code == 200 and asset.content for asset in built_assets)
        bundle = "\n".join(asset.text for asset in built_assets)
        assert "Analyst alerts" in bundle and "Evidence results" in bundle
        assert "Not calibrated attack probability" in bundle
        assert "Numeric attack probability is not defined by this analytic." in bundle
        assert "stream_gap" in bundle
        assert (await client.get("/health")).status_code == 200
        assert (await client.get("/runtime")).status_code == 200
        assert (await client.get("/results")).status_code == 200
        assert (await client.get("/alerts")).status_code == 200


@pytest.mark.asyncio
async def test_operator_console_preserves_scientific_and_presentation_boundaries(tmp_path):
    async with client_for(tmp_path / "console.db") as (client, _service):
        page = (await client.get("/")).text
        assets = re.findall(r'(?:src|href)="(/assets/[^"]+)"', page)
        bundle = "\n".join([(await client.get(path)).text for path in assets])
        assert 'id="root"' in page
        assert "DGA-labelled lexical resemblance score" in bundle
        assert "Not calibrated attack probability" in bundle
        assert "Numeric attack probability is not defined by this analytic." in bundle
        assert "claim_ceiling" in bundle
        assert "default_target_count" in bundle and "dga_model_readiness" in bundle
        assert "EVIDENCEGATE_ENABLE_CANDIDATE_ALERTS" not in page + bundle
        assert "global risk" not in (page + bundle).lower()
        css = next(path for path in assets if path.endswith(".css"))
        styles = (await client.get(css)).text
        assert "prefers-reduced-motion:reduce" in styles
        assert "width<=760px" in styles


@pytest.mark.asyncio
async def test_results_serialization_pagination_filters_and_sync_cursor(tmp_path):
    async with client_for(tmp_path / "query.db") as (client, service):
        values = (
            make_result("one", at=BASE, source="source-a"),
            make_result("two", at=BASE + timedelta(seconds=1), lane="c2.r1", mechanism="C2-M1", source="source-b"),
            make_result("three", at=BASE + timedelta(seconds=2), source="source-a"),
        )
        for value in values:
            await service.persist_and_publish(value)

        first = (await client.get("/results", params={"limit": 2})).json()
        assert [item["result_id"] for item in first["results"]] == [values[2].result_id, values[1].result_id]
        assert first["next_cursor"] and first["sync_cursor"].startswith("after.")
        second = (await client.get("/results", params={"limit": 2, "cursor": first["next_cursor"]})).json()
        assert [item["result_id"] for item in second["results"]] == [values[0].result_id]

        by_lane = (await client.get("/results", params={"lane": "c2.r1"})).json()["results"]
        assert [item["result_id"] for item in by_lane] == [values[1].result_id]
        by_mechanism = (await client.get("/results", params={"mechanism_id": "DNS-T1"})).json()["results"]
        assert {item["result_id"] for item in by_mechanism} == {values[0].result_id, values[2].result_id}
        by_source = (await client.get("/results", params={"source_id": "source-b"})).json()["results"]
        assert [item["result_id"] for item in by_source] == [values[1].result_id]
        by_type = (await client.get("/results", params={"result_type": "REVIEW_FINDING"})).json()["results"]
        assert len(by_type) == 3
        by_time = (await client.get("/results", params={
            "created-after": (BASE + timedelta(milliseconds=500)).isoformat(),
            "created-before": (BASE + timedelta(seconds=1, milliseconds=500)).isoformat(),
        })).json()["results"]
        assert [item["result_id"] for item in by_time] == [values[1].result_id]

        body = first["results"][0]
        assert body["evidence"] == {"measurement": "three"}
        assert body["source_observation_ids"] == ["observation-three"]
        assert body["provenance_refs"] == ["fixture:bounded"]
        assert "confidence" not in body and "severity" not in body
        assert (await client.get(f"/results/{values[0].result_id}")).json()["result_id"] == values[0].result_id

        newer = make_result("four", at=BASE + timedelta(seconds=3))
        await service.persist_and_publish(newer)
        continuation = (await client.get("/results", params={"cursor": first["sync_cursor"]})).json()
        assert [item["result_id"] for item in continuation["results"]] == [newer.result_id]


@pytest.mark.asyncio
async def test_results_validation_is_typed_and_bounded(tmp_path):
    async with client_for(tmp_path / "errors.db") as (client, _service):
        for params in (
            {"cursor": "not-a-cursor"}, {"limit": 0}, {"limit": 501},
            {"lane": "not.registered"}, {"result_type": "NOT_A_RESULT"},
            {"created-after": "not-a-time"},
        ):
            response = await client.get("/results", params=params)
            assert response.status_code == 422
            assert "Traceback" not in response.text


@pytest.mark.asyncio
async def test_persist_then_publish_multiple_subscribers_and_sse_encoding(tmp_path):
    async with client_for(tmp_path / "live.db") as (_client, service):
        one = service.broadcaster.subscribe()
        two = service.broadcaster.subscribe()
        result = make_result("live")
        assert await service.persist_and_publish(result)
        assert await service.writer.get_result(result.result_id) == result
        messages = await asyncio.gather(one.get(), two.get())
        assert all(isinstance(item, ResultNotification) for item in messages)
        assert all(item.result_id == result.result_id for item in messages)
        assert all(item.cursor.startswith("after.") for item in messages)
        wire = sse_encode(messages[0])
        assert wire.startswith("event: result\ndata: ") and result.result_id in wire


@pytest.mark.asyncio
async def test_events_endpoint_emits_a_real_persisted_notification(tmp_path):
    app = create_app(tmp_path / "events.db")

    class ConnectedRequest:
        async def is_disconnected(self):
            return False

    async with app.router.lifespan_context(app):
        endpoint = next(route.endpoint for route in app.routes if route.path == "/events")
        response = await endpoint(ConnectedRequest())
        ready = await anext(response.body_iterator)
        assert ready == "event: ready\ndata: {}\n\n"
        result = make_result("events-endpoint")
        await app.state.service.persist_and_publish(result)
        event = await asyncio.wait_for(anext(response.body_iterator), timeout=1)
        assert event.startswith("event: result\ndata: ") and result.result_id in event
        await response.body_iterator.aclose()
        assert app.state.service.broadcaster.subscriber_count == 0


@pytest.mark.asyncio
async def test_persistence_failure_is_never_published(tmp_path, monkeypatch):
    async with client_for(tmp_path / "failure.db") as (_client, service):
        subscription = service.broadcaster.subscribe()

        async def fail(_result):
            raise RuntimeError("controlled persistence failure")

        monkeypatch.setattr(service.writer, "write_result", fail)
        with pytest.raises(RuntimeError, match="controlled persistence failure"):
            await service.persist_and_publish(make_result("failure"))
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(subscription.get(), timeout=0.02)


@pytest.mark.asyncio
async def test_slow_client_gap_does_not_affect_sqlite_and_rest_resync(tmp_path):
    async with client_for(tmp_path / "slow.db", subscriber_queue_size=1) as (client, service):
        subscription = service.broadcaster.subscribe()
        first = make_result("slow-one", at=BASE)
        second = make_result("slow-two", at=BASE + timedelta(seconds=1))
        await service.persist_and_publish(first)
        await service.persist_and_publish(second)
        gap = await subscription.get()
        assert isinstance(gap, StreamGap) and gap.resync_required
        assert await service.writer.count_results() == 2
        durable = (await client.get("/results")).json()["results"]
        assert {item["result_id"] for item in durable} == {first.result_id, second.result_id}


@pytest.mark.asyncio
async def test_allowlist_rejects_paths_and_mixed_replay_is_zero_to_many(tmp_path):
    async with client_for(tmp_path / "mixed.db") as (client, service):
        arbitrary = await client.post("/replay", json={"scenario": "C:/private/capture", "speed": 0})
        assert arbitrary.status_code == 422
        extra_path = await client.post("/replay", json={
            "scenario": "mixed_ddos_recon", "speed": 0, "path": "C:/private/capture",
        })
        assert extra_path.status_code == 422
        assert (await client.post("/replay", json={
            "scenario": "mixed_ddos_recon", "speed": -1,
        })).status_code == 422

        subscription = service.broadcaster.subscribe()
        started = await client.post("/replay", json={"scenario": "mixed_ddos_recon", "speed": 0})
        assert started.status_code == 202
        status = await service.wait_for_replay()
        assert status.state == "COMPLETED"
        assert status.records_read == status.observations_emitted == 2
        assert status.results_persisted > 1
        notification = await asyncio.wait_for(subscription.get(), timeout=1)
        assert isinstance(notification, ResultNotification)
        results = (await client.get("/results", params={"limit": 500})).json()["results"]
        families = {item["family"] for item in results}
        assert {"DDoS", "Reconnaissance"} <= families
        assert all(item["result_type"] != "THREAT_ALERT" for item in results)
        assert all("confidence" not in item and "severity" not in item for item in results)


@pytest.mark.asyncio
async def test_dga_demo_runs_real_model_persists_rest_and_publishes(tmp_path, monkeypatch):
    model = Path("artifacts/dga/local/DGA_M1_R1_SERIALIZED_MODEL.joblib").resolve()
    monkeypatch.setenv("EVIDENCEGATE_DGA_MODEL", str(model))
    async with client_for(tmp_path / "dga-demo.db") as (client, service):
        runtime = (await client.get("/runtime")).json()
        assert runtime["dga_model_readiness"] == "VERIFIED_READY"
        dga_family = next(item for item in runtime["family_status"] if item["family"] == "DGA")
        assert dga_family["status"] == "ACTIVE M1 LEXICAL MODEL EVIDENCE"
        subscription = service.broadcaster.subscribe()
        response = await client.post("/replay", json={"scenario": "dga_lexical", "speed": 0})
        assert response.status_code == 202
        status = await service.wait_for_replay()
        assert status.state == "COMPLETED" and status.results_persisted == 2
        notifications = [await asyncio.wait_for(subscription.get(), timeout=1) for _ in range(2)]
        assert {item.mechanism_id for item in notifications} == {"DGA-A1-M1", "DNS-T1"}
        results = (await client.get("/results", params={"limit": 10})).json()["results"]
        dga = next(item for item in results if item["mechanism_id"] == "DGA-A1-M1")
        assert dga["result_type"] == "REVIEW_FINDING"
        assert dga["evidence"]["dga_labelled_lexical_resemblance_score"] == pytest.approx(
            0.9851716132182514, abs=1e-12
        )
        assert "C3-DEC-DGA-M1-R1-PROMOTION-V1" in dga["governing_ids"]
        assert "sha256:39da209d2cfd869dd284e10b8a07adc04826c95146712cc6854a69b9873890df" in dga["model_refs"]
        assert dga["config_hash"] and dga["source_observation_ids"]
        assert dga["visibility_snapshot"]["available"]
        assert dga["quality_snapshot"]["parser"] == "CLEAR"
        assert dga["claim_ceiling"].startswith("DGA_LABELLED_LEXICAL_REVIEW_EVIDENCE_ONLY")


@pytest.mark.asyncio
async def test_only_one_replay_runs_and_runtime_reports_replaying(tmp_path):
    async with client_for(tmp_path / "one-at-a-time.db") as (client, _service):
        started = await client.post("/replay", json={"scenario": "c2_recurrence", "speed": 1})
        assert started.status_code == 202
        assert (await client.get("/replay/status")).json()["state"] == "RUNNING"
        assert (await client.get("/runtime")).json()["state"] == "REPLAYING"
        second = await client.post("/replay", json={"scenario": "dns_observation", "speed": 0})
        assert second.status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("scenario", "family", "mechanism"),
    (
        ("c2_recurrence", "C2 / Beaconing", "C2-M1"),
        ("dns_observation", "DNS Tunnelling", "DNS-T1"),
        ("encrypted_session", "Encrypted Sessions", "ENC-A"),
        ("transfer_magnitude", "Data Exfiltration", "CAT6-EX-M1"),
    ),
)
async def test_family_replays_display_real_results(tmp_path, scenario, family, mechanism):
    async with client_for(tmp_path / f"{scenario}.db") as (client, service):
        response = await client.post("/replay", json={"scenario": scenario, "speed": 0})
        assert response.status_code == 202
        status = await service.wait_for_replay()
        assert status.state == "COMPLETED" and status.results_persisted > 0
        results = (await client.get("/results", params={"mechanism_id": mechanism})).json()["results"]
        assert results and {item["family"] for item in results} == {family}
        assert {item["mechanism_id"] for item in results} == {mechanism}
        if scenario == "c2_recurrence":
            assert {item["result_type"] for item in results} == {
                "INSUFFICIENT_EVIDENCE", "REVIEW_FINDING",
            }
            filtered = (await client.get("/results", params={
                "mechanism_id": mechanism, "result_type": "INSUFFICIENT_EVIDENCE",
            })).json()["results"]
            assert filtered and {item["result_type"] for item in filtered} == {"INSUFFICIENT_EVIDENCE"}


@pytest.mark.asyncio
async def test_restart_preserves_durable_results(tmp_path):
    database = tmp_path / "restart.db"
    result = make_result("restart")
    async with client_for(database) as (_client, service):
        await service.persist_and_publish(result)
    async with client_for(database) as (client, _service):
        restored = (await client.get("/results")).json()["results"]
        assert [item["result_id"] for item in restored] == [result.result_id]


def test_active_projection_contract_is_wired_to_default_api():
    app = create_app(":memory:")
    schema = app.openapi()
    serialized = str(schema)
    assert "SihAlertProjection" in serialized
    assert any(route.path == "/alerts" for route in app.routes)
