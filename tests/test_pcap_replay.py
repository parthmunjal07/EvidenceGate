"""Passive raw-PCAP adapter, canonical parity, and product integration tests."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import dpkt
import pytest
from httpx import ASGITransport, AsyncClient

from evidencegate.api.app import create_app
from evidencegate.domain.enums import (
    CapabilityState, IdentityBasis, SourceKind, VisibilityCapability, WireDirection,
)
from evidencegate.ingest.pcap import PcapReplaySource, validate_pcap
from evidencegate.ingest.replay import NdjsonReplaySource, ReplayCanonicalizer, ReplayRunner
from evidencegate.ingest.replay_schema import ReplaySourceRecord, ReplayValidationError
from evidencegate.persistence.sqlite import SqliteWriter
from evidencegate.plugins.providers.registry import build_mvp_runtime_registration
from evidencegate.runtime.supervisor import RuntimeSupervisor


ROOT = Path(__file__).resolve().parents[1]
PCAP = ROOT / "tests" / "fixtures" / "pcap" / "raw_ddos_recon"
ONE_WAY = ROOT / "tests" / "fixtures" / "pcap" / "one_way"
SCHEMA = ROOT / "evidencegate" / "persistence" / "schema.sql"
NOW = datetime(2026, 2, 1, tzinfo=timezone.utc)


async def canonical(bundle: Path):
    source = PcapReplaySource(bundle / "capture.pcap", bundle / "manifest.json")
    manifest = await source.open()
    records = []
    observations = []
    try:
        async for record in source.records():
            records.append(record)
            result = ReplayCanonicalizer().canonicalize(
                record, manifest, f"quality:{manifest.source_id}:{record.position}", NOW,
            )
            observations.extend(result.observations)
    finally:
        await source.close()
    return manifest, records, observations


@pytest.mark.asyncio
async def test_streaming_packet_iteration_and_packet_facts() -> None:
    manifest, records, observations = await canonical(PCAP)
    assert manifest.source_kind is SourceKind.PCAP
    assert [item.position for item in records] == list(range(1, 12))
    assert observations[0].event_time == datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert observations[0].ingest_time == NOW
    assert observations[0].event_time != observations[0].ingest_time

    syn = observations[0]
    assert syn.typed_payload.src_address == "10.0.0.10"
    assert syn.typed_payload.dst_address == "10.0.1.10"
    assert (syn.typed_payload.src_port, syn.typed_payload.dst_port) == (50000, 443)
    assert syn.typed_payload.protocol == 6
    assert syn.typed_payload.flags == ["SYN"]
    assert syn.typed_payload.sequence_facts == {"seq": 100, "ack": 0}
    assert syn.typed_payload.lengths["ip"] == 40
    assert syn.typed_payload.raw_reference == "pcap:controlled-raw-pcap-both:packet:1"
    assert not hasattr(syn.typed_payload, "payload")

    udp, icmp, fragment = observations[6], observations[7], observations[8]
    assert (udp.typed_payload.protocol, udp.typed_payload.dst_port) == (17, 53)
    assert icmp.typed_payload.protocol == 1
    assert icmp.typed_payload.observed_l4_facts == {"protocol": 1, "type": 8, "code": 0}
    assert fragment.typed_payload.fragmentation == {
        "fact_contract": "DDOS_FRAGMENT_FACT_V1", "is_fragment": True,
        "offset": 0, "more_fragments": True,
    }


@pytest.mark.asyncio
async def test_direction_visibility_roles_service_and_retransmission_facts() -> None:
    manifest, _, observations = await canonical(PCAP)
    assert observations[0].wire_direction is WireDirection.FORWARD
    assert observations[2].wire_direction is WireDirection.REVERSE
    for observation in observations:
        assert observation.visibility.state(VisibilityCapability.FORWARD_FACTS) is CapabilityState.AVAILABLE
        assert observation.visibility.state(VisibilityCapability.REVERSE_FACTS) is CapabilityState.AVAILABLE
        assert observation.visibility.state(VisibilityCapability.PACKET_FACTS) is CapabilityState.AVAILABLE
    roles = observations[0].identity.role_assignments
    assert {(item.identifier, item.role, item.basis) for item in roles} == {
        ("10.0.0.10", "initiator_id", IdentityBasis.POLICY_DECLARED_ROLE),
        ("10.0.1.10", "target_id", IdentityBasis.POLICY_DECLARED_ROLE),
        ("service/https", "service_id", IdentityBasis.POLICY_DECLARED_ROLE),
    }
    assert observations[0].typed_payload.sequence_facts == observations[1].typed_payload.sequence_facts


@pytest.mark.asyncio
async def test_one_way_visibility_remains_source_fact() -> None:
    _, _, observations = await canonical(ONE_WAY)
    assert all(item.wire_direction is WireDirection.FORWARD for item in observations)
    assert all(item.visibility.state(VisibilityCapability.FORWARD_FACTS) is CapabilityState.AVAILABLE for item in observations)
    assert all(item.visibility.state(VisibilityCapability.REVERSE_FACTS) is CapabilityState.UNAVAILABLE for item in observations)


@pytest.mark.asyncio
async def test_no_policy_means_unknown_even_for_private_addresses(tmp_path: Path) -> None:
    value = json.loads((PCAP / "manifest.json").read_text(encoding="utf-8"))
    value["direction_policy"] = {"a_networks": [], "b_networks": []}
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    source = PcapReplaySource(PCAP / "capture.pcap", path)
    manifest = await source.open()
    records = source.records()
    try:
        first = await anext(records)
        observation = ReplayCanonicalizer().canonicalize(
            first, manifest, "quality:test", NOW,
        ).observations[0]
        assert observation.wire_direction is WireDirection.UNKNOWN
        assert observation.direction_basis.value == "UNKNOWN"
    finally:
        await records.aclose()
        await source.close()


@pytest.mark.asyncio
async def test_missing_roles_fail_closed_and_reflection_requires_sidecar() -> None:
    manifest, records, observations = await canonical(PCAP)
    registration = build_mvp_runtime_registration(NOW)
    supervisor = RuntimeSupervisor(
        registration.plugins, registration.governances, lambda *_: None,  # not started
        reorder_policies=registration.reorder_policies,
    )
    generic_udp = supervisor.router.plan(observations[6])
    declared_reflection = supervisor.router.plan(observations[9])
    assert "ddos.reflection_victim" not in {str(item) for item in generic_udp.selected_targets}
    assert "ddos.reflection_victim" in {str(item) for item in declared_reflection.selected_targets}

    no_roles = ReplaySourceRecord(
        raw_data=records[0].raw_data, timestamp=records[0].timestamp,
        position=records[0].position, finality=records[0].finality,
        declared_observed_fields=records[0].declared_observed_fields,
        role_assignments=(), canonicalization_options={},
        wire_direction=WireDirection.FORWARD,
    )
    observation = ReplayCanonicalizer().canonicalize(
        no_roles, manifest, "quality:no-roles", NOW,
    ).observations[0]
    assert not supervisor.router.plan(observation).selected_targets


@pytest.mark.asyncio
async def test_pcap_and_typed_record_canonical_and_route_parity() -> None:
    _, _, pcap_observations = await canonical(PCAP)
    typed_source = NdjsonReplaySource(ROOT / "tests" / "fixtures" / "replay" / "raw_ddos_recon_parity")
    typed_manifest = await typed_source.open()
    typed_observations = []
    try:
        async for typed in typed_source.records():
            typed_observations.extend(ReplayCanonicalizer().canonicalize(
                typed, typed_manifest, f"quality:typed:{typed.position}", NOW,
            ).observations)
    finally:
        await typed_source.close()
    assert len(pcap_observations) == len(typed_observations) == 11
    registration = build_mvp_runtime_registration(NOW)
    supervisor = RuntimeSupervisor(
        registration.plugins, registration.governances, lambda *_: None,
        reorder_policies=registration.reorder_policies,
    )
    for left, right in zip(pcap_observations, typed_observations):
        assert left.typed_payload == right.typed_payload
        assert left.event_time == right.event_time
        assert left.wire_direction == right.wire_direction
        assert left.visibility == right.visibility
        assert left.quality == right.quality
        assert left.identity == right.identity
        assert supervisor.router.plan(left).selected_targets == supervisor.router.plan(right).selected_targets


@pytest.mark.asyncio
async def test_corrupt_and_unsupported_capture_fail_closed(tmp_path: Path) -> None:
    manifest = json.loads((PCAP / "manifest.json").read_text(encoding="utf-8"))
    manifest["packet_count"] = None
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    corrupt = tmp_path / "capture.pcap"
    corrupt.write_bytes((PCAP / "capture.pcap").read_bytes()[:40])
    with pytest.raises(ReplayValidationError):
        await validate_pcap(corrupt, manifest_path)

    unsupported = tmp_path / "unsupported.pcap"
    with unsupported.open("wb") as handle:
        writer = dpkt.pcap.Writer(handle, linktype=dpkt.pcap.DLT_RAW)
        writer.writepkt(b"\x45" + b"\x00" * 19, ts=1)
        writer.close()
    manifest["capture_file"] = unsupported.name
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ReplayValidationError, match="UnsupportedLinkType"):
        await PcapReplaySource(unsupported, manifest_path).open()


@pytest.mark.asyncio
async def test_pcap_runtime_sqlite_zero_to_many_and_restart_durability(tmp_path: Path) -> None:
    database = tmp_path / "pcap.db"
    writer = SqliteWriter(database, SCHEMA)
    writer.connect()
    persisted = []

    async def persist(result, _target):
        if await writer.write_result(result):
            persisted.append(result)

    registration = build_mvp_runtime_registration(NOW)
    supervisor = RuntimeSupervisor(
        registration.plugins, registration.governances, persist,
        reorder_policies=registration.reorder_policies,
    )
    summary = await ReplayRunner(
        PcapReplaySource(PCAP / "capture.pcap", PCAP / "manifest.json"),
        supervisor, speed=0,
    ).run()
    assert summary.records_read == summary.observations_emitted == 11
    assert summary.routed_mechanism_updates > summary.observations_emitted
    lanes = {item.lane_id for item in persisted}
    assert {"ddos.syn_state", "ddos.udp_demand", "ddos.reflection_victim", "ddos.fragment_demand", "recon.h", "recon.v", "recon.2d", "recon.tcp"} <= lanes
    retransmission_results = [item for item in persisted if item.lane_id == "ddos.syn_state"]
    assert any(item.evidence.to_value().get("recognized_retransmissions") == 1 for item in retransmission_results)
    count = await writer.count_results()
    writer.close()
    restarted = SqliteWriter(database, SCHEMA)
    restarted.connect()
    assert await restarted.count_results() == count
    restarted.close()


@pytest.mark.asyncio
async def test_allowlisted_pcap_api_status_persistence_and_notifications(tmp_path: Path) -> None:
    app = create_app(tmp_path / "api.db")
    async with app.router.lifespan_context(app):
        service = app.state.service
        subscription = service.broadcaster.subscribe()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            runtime = (await client.get("/runtime")).json()
            assert "RAW_PCAP_REPLAY" in runtime["supported_sources"]
            scenario = next(item for item in runtime["scenarios"] if item["id"] == "raw_pcap_ddos_recon")
            assert scenario["source_type"] == "PCAP"
            started = await client.post("/replay", json={"scenario": scenario["id"], "speed": 0})
            assert started.status_code == 202
            status = await service.wait_for_replay()
            assert status.state == "COMPLETED"
            assert status.source_type == "PCAP"
            assert status.results_persisted > 0
            notice = await subscription.get()
            assert notice.event == "result"
            results = (await client.get("/results", params={"source_id": "controlled-raw-pcap-both"})).json()
            assert results["results"]
            rejected = await client.post("/replay", json={"scenario": str(PCAP / "capture.pcap"), "speed": 0})
            assert rejected.status_code == 422
        service.broadcaster.unsubscribe(subscription)
