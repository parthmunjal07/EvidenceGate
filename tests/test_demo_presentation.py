"""Public workbench projections, fail-open behavior, and deployment headers."""
from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from evidencegate.api.app import create_app
from evidencegate.api.privacy import public_reference_list
from evidencegate.api.service import default_scenarios
from evidencegate.results.finalizer import result_id_for
from tests.test_product_surface import client_for, make_result


def test_runtime_default_scenarios_are_only_curated_and_internal_is_opt_in(monkeypatch):
    monkeypatch.delenv("EVIDENCEGATE_DEV_SCENARIOS", raising=False)
    scenarios = default_scenarios(Path.cwd())
    assert set(scenarios) == {
        "mixed_ddos_recon", "ddos_one_way", "c2_recurrence", "dga_lexical",
        "encrypted_tls_session", "raw_pcap_ddos_recon",
    }
    assert all("tests" not in str(item.bundle).lower() for item in scenarios.values())
    mixed = scenarios["mixed_ddos_recon"]
    assert mixed.bundle == Path.cwd() / "evidencegate" / "demo_data" / "mixed_ddos_recon_v2"
    assert mixed.demo_contract and mixed.demo_contract["asset_version"] == "mixed_ddos_recon_v2"
    assert mixed.demo_contract["expected_records"] == 12
    encrypted = scenarios["encrypted_tls_session"]
    assert encrypted.demo_contract["asset_version"] == "encrypted_tls_session_v1"
    assert encrypted.demo_contract["expected_results"] == 1
    monkeypatch.setenv("EVIDENCEGATE_DEV_SCENARIOS", "1")
    internal = default_scenarios(Path.cwd())
    assert "encrypted_session" in internal and "mixed_ddos_recon_internal" in internal


def test_public_reference_filter_removes_private_locators_and_local_paths():
    values = [
        "model:DGA-A1-M1-R1", "sha256:" + "a" * 64,
        "drive:private-folder-id", "https://drive.google.com/file/d/private-id",
        r"C:\Users\person\model.joblib", "/home/person/model.joblib",
    ]
    assert public_reference_list(values) == ["model:DGA-A1-M1-R1", "sha256:" + "a" * 64]


@pytest.mark.asyncio
async def test_trace_source_and_canonical_summaries_are_safe_and_complete(tmp_path):
    async with client_for(tmp_path / "presentation.db") as (client, service):
        runtime = (await client.get("/runtime")).json()
        assert {item["id"] for item in runtime["scenarios"]} == {
            "mixed_ddos_recon", "ddos_one_way", "c2_recurrence", "dga_lexical",
            "encrypted_tls_session", "raw_pcap_ddos_recon",
        }
        assert (await client.post("/replay", json={"scenario": "mixed_ddos_recon", "speed": 0})).status_code == 202
        status = await service.wait_for_replay()
        assert status.state == "COMPLETED"
        events = (await client.get("/runtime/trace", params={"after": 0, "limit": 500})).json()["events"]
        source = [event["source_record"] for event in events if event["kind"] == "SOURCE_RECORD_ACCEPTED"]
        observations = [event["canonical_observation"] for event in events if event["kind"] == "OBSERVATION_CREATED"]
        assert len(source) == len(observations) == 12
        assert source[0]["facts"]["source_address"] == "198.51.100.10"
        assert observations[0]["facts"]["destination_address"] == "192.0.2.10"
        assert "PACKET_FACTS" in observations[0]["visibility"]["available"]
        assert "REVERSE_FACTS" in observations[0]["visibility"]["unavailable"]
        assert observations[0]["quality"]["packet_loss"] == "UNKNOWN"
        assert observations[0]["identity"]["role_assignments"]
        text = str(events).lower()
        for forbidden in ("raw_data", "payload_bytes", "drive.google.com", "drive:", "users\\", "/home/"):
            assert forbidden not in text


@pytest.mark.asyncio
async def test_presentation_projection_failures_do_not_interrupt_replay_or_persistence(tmp_path, monkeypatch):
    import evidencegate.api.observation_presentation as presentation_module

    def fail_projection(*_args, **_kwargs):
        raise RuntimeError("controlled presentation failure")

    monkeypatch.setattr(presentation_module, "project_source_record", fail_projection)
    monkeypatch.setattr(presentation_module, "project_observation", fail_projection)
    async with client_for(tmp_path / "fail-open.db") as (client, service):
        started = await client.post("/replay", json={"scenario": "mixed_ddos_recon", "speed": 0})
        assert started.status_code == 202
        status = await service.wait_for_replay()
        assert status.state == "COMPLETED" and status.results_persisted == 65
        assert len((await client.get("/results", params={"limit": 500})).json()["results"]) == 65
        trace = (await client.get("/runtime/trace", params={"after": 0, "limit": 500})).json()["events"]
        assert any(event["kind"] == "SOURCE_RECORD_ACCEPTED" and event["source_record"] is None for event in trace)
        assert any(event["kind"] == "OBSERVATION_CREATED" and event["canonical_observation"] is None for event in trace)


@pytest.mark.asyncio
async def test_historical_result_private_provenance_is_filtered_from_public_api(tmp_path):
    database = tmp_path / "historical.db"
    original = make_result("historical")
    historic = dataclasses.replace(
        original, result_id="", model_refs=("model:DGA-A1-M1-R1", "drive:private-id"),
        provenance_refs=("/home/private/model.joblib", "sha256:" + "b" * 64),
    )
    historic = dataclasses.replace(historic, result_id=result_id_for(historic))
    async with client_for(database) as (_client, service):
        await service.persist_and_publish(historic)
    async with client_for(database) as (client, _service):
        item = (await client.get(f"/results/{historic.result_id}")).json()
        assert item["model_refs"] == ["model:DGA-A1-M1-R1"]
        assert item["provenance_refs"] == ["sha256:" + "b" * 64]


@pytest.mark.asyncio
async def test_public_mode_disables_schema_adds_noindex_headers_and_robots(tmp_path, monkeypatch):
    monkeypatch.setenv("EVIDENCEGATE_PUBLIC_MODE", "1")
    async with client_for(tmp_path / "public.db") as (client, _service):
        for path in ("/", "/health", "/robots.txt"):
            response = await client.get(path)
            assert response.status_code == 200
            assert response.headers["x-robots-tag"] == "noindex, nofollow, noarchive, nosnippet"
            assert response.headers["x-content-type-options"] == "nosniff"
        assert "noindex, nofollow" in (await client.get("/")).text
        assert (await client.get("/")).headers["cache-control"] == "no-store"
        manifest = await client.get("/release-manifest.json")
        assert manifest.headers["cache-control"] == "no-store"
        runtime = (await client.get("/runtime")).json()
        assert runtime["release_id"] == manifest.json()["release_id"]
        assert "source_sha" in runtime
        assert (await client.get("/robots.txt")).text == "User-agent: *\nDisallow: /\n"
        for path in ("/docs", "/redoc", "/openapi.json"):
            assert (await client.get(path)).status_code == 404
