"""Controlled-MVP default activation integration for DDoS and Recon lanes."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from evidencegate.ingest.replay import NdjsonReplaySource, ReplayRunner, validate_bundle
from evidencegate.persistence.sqlite import SqliteWriter
from evidencegate.plugins.providers.registry import (
    DDOS_RECON_MVP_ACTIVATION_DECISION_ID,
    build_mvp_runtime_registration,
)
from evidencegate.results.types import ThreatAlert
from evidencegate.runtime.supervisor import RuntimeSupervisor


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
SCHEMA = Path("evidencegate/persistence/schema.sql")
FIXTURES = Path("tests/fixtures/replay")


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ("default_activation_tcp", "default_activation_udp"))
async def test_default_activation_fixtures_validate(name):
    assert await validate_bundle(FIXTURES / name) == 2


async def run_default(bundle: str, database: Path):
    registration = build_mvp_runtime_registration(NOW)
    writer = SqliteWriter(database, SCHEMA)
    writer.connect()
    emitted = []

    async def persist(result, lane):
        emitted.append((str(lane), result))
        await writer.write_result(result)

    supervisor = RuntimeSupervisor(
        registration.plugins,
        registration.governances,
        persist,
        shard_count=1,
        reorder_policies=registration.reorder_policies,
    )
    try:
        summary = await ReplayRunner(
            NdjsonReplaySource(FIXTURES / bundle),
            supervisor,
            clock=lambda: NOW,
        ).run()
        stored = [await writer.get_result(result.result_id) for _, result in emitted]
        return summary, emitted, stored, registration
    finally:
        writer.close()


@pytest.mark.asyncio
async def test_default_tcp_zero_to_many_and_sqlite_round_trip(tmp_path):
    summary, emitted, stored, registration = await run_default(
        "default_activation_tcp", tmp_path / "tcp.db"
    )
    assert summary.records_read == summary.observations_emitted == 2
    activated = {
        lane for lane, _ in emitted if lane.startswith("ddos.") or lane.startswith("recon.")
    }
    assert activated == {
        "ddos.syn_state",
        "ddos.source_diversity",
        "ddos.connection_churn",
        "recon.h",
        "recon.v",
        "recon.2d",
        "recon.tcp",
    }
    assert stored == [result for _, result in emitted]
    for lane, result in emitted:
        if lane not in activated:
            continue
        manifest = registration.plugins[lane].manifest()
        assert DDOS_RECON_MVP_ACTIVATION_DECISION_ID in result.governing_ids
        assert result.mechanism_id == manifest.mechanism_id
        assert result.config_hash == manifest.config_hash
        assert result.claim_ceiling == registration.governances[lane].claim_ceiling
        assert not isinstance(result, ThreatAlert)
        assert not hasattr(result, "score")


@pytest.mark.asyncio
async def test_default_udp_zero_to_many_and_independent_results(tmp_path):
    _, emitted, stored, registration = await run_default(
        "default_activation_udp", tmp_path / "udp.db"
    )
    activated = [(lane, result) for lane, result in emitted if lane.startswith("ddos.")]
    assert {lane for lane, _ in activated} == {
        "ddos.udp_demand",
        "ddos.reflection_victim",
        "ddos.source_diversity",
    }
    assert len({result.result_id for _, result in activated}) == len(activated)
    assert stored == [result for _, result in emitted]
    for lane, result in activated:
        manifest = registration.plugins[lane].manifest()
        assert DDOS_RECON_MVP_ACTIVATION_DECISION_ID in result.governing_ids
        assert result.mechanism_id == manifest.mechanism_id
        assert result.config_hash == manifest.config_hash
        assert result.claim_ceiling == registration.governances[lane].claim_ceiling
        assert not isinstance(result, ThreatAlert)


def test_default_plugin_capacity_values_are_exact():
    plugins = build_mvp_runtime_registration(NOW).plugins
    assert plugins["ddos.syn_state"].manifest().state_resource_policy.max_entries == 1024
    for lane in (
        "ddos.udp_demand",
        "ddos.reflection_victim",
        "ddos.source_diversity",
        "ddos.icmp_demand",
        "ddos.fragment_demand",
        "ddos.connection_churn",
    ):
        assert plugins[lane].manifest().state_resource_policy.max_entries == 512
    assert plugins["ddos.reflection_victim"].max_sources_per_window == 256
    assert plugins["ddos.source_diversity"].max_sources_per_window == 256
    assert plugins["ddos.connection_churn"].max_attempts_per_window == 256
    for lane in ("recon.h", "recon.v", "recon.2d", "recon.tcp"):
        plugin = plugins[lane]
        assert plugin.manifest().state_resource_policy.max_entries == 1024
        assert plugin.config.max_events_per_key == 16
        assert plugin.config.state_ttl.total_seconds() == 3600
        assert tuple(item.total_seconds() for item in plugin.config.horizons) == (60, 3600)
