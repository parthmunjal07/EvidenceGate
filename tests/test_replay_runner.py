"""Replay-to-runtime integration, persistence, and event-time boundary tests."""
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from evidencegate.domain.enums import ControlType, ResultType, ScientificStatus
from evidencegate.domain.governance import LaneGovernance
from evidencegate.ingest.replay import NdjsonReplaySource, ReplayRunner
from evidencegate.persistence.sqlite import SqliteWriter
from evidencegate.plugins.providers.c2 import C2R1Plugin
from evidencegate.plugins.providers.c2_config import C2R1Config
from evidencegate.plugins.providers.registry import build_mvp_provider_registry
from evidencegate.routing.router import LaneTarget
from evidencegate.runtime.dispatcher import EventTimeReorderPolicy
from evidencegate.runtime.supervisor import RuntimeSupervisor


FIXTURES = Path("tests/fixtures/replay")
NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
SCHEMA = Path("evidencegate/persistence/schema.sql")


async def run_default(bundle, database):
    sqlite = SqliteWriter(database, SCHEMA)
    sqlite.connect()
    results, controls = [], []

    async def writer(result, target):
        results.append(result)
        await sqlite.write_result(result)

    async def control(event):
        controls.append(event)

    plugins, governances = build_mvp_provider_registry(NOW)
    supervisor = RuntimeSupervisor(
        plugins, governances, writer, shard_count=1, control_sink=control,
    )
    summary = await ReplayRunner(
        NdjsonReplaySource(bundle), supervisor, control_sink=control,
    ).run()
    persisted = await sqlite.list_results(limit=100)
    sqlite.close()
    return summary, results, controls, persisted


@pytest.mark.parametrize("fixture,mechanism", [
    ("dns_forward", "DNS-T1"),
    ("tls_handshake", "ENC-A"),
    ("flow_transfer", "CAT6-EX-M1"),
])
async def test_real_mechanism_end_to_end_through_sqlite(tmp_path, fixture, mechanism):
    summary, results, controls, persisted = await run_default(
        FIXTURES / fixture, tmp_path / f"{fixture}.sqlite",
    )
    assert summary.records_read == summary.observations_emitted == 1
    assert len(results) == len(persisted) == 1
    assert results[0].result_type is ResultType.REVIEW_FINDING
    assert results[0].mechanism_id == mechanism
    assert [event.control_type for event in controls if event.source_id] == [
        ControlType.SOURCE_STARTED, ControlType.SOURCE_ENDED,
    ]


async def test_repeated_replay_has_deterministic_scientific_ids(tmp_path):
    first = await run_default(FIXTURES / "dns_forward", tmp_path / "one.sqlite")
    second = await run_default(FIXTURES / "dns_forward", tmp_path / "two.sqlite")
    assert first[1][0].result_id == second[1][0].result_id
    assert first[1][0].evidence == second[1][0].evidence


def c2_governance():
    lane = "c2.r1"
    return LaneGovernance(
        analytic_lane=lane, scientific_status=ScientificStatus.EVIDENCE_CONSTRUCTION,
        scientific_phase="TEST CONFIGURATION ONLY", scientific_blockers=(),
        claim_ceiling="RECURRENCE MEASUREMENT ONLY", governance_version="test-replay-v1",
        effective_at=NOW,
        allowed_result_types=(ResultType.REVIEW_FINDING, ResultType.INSUFFICIENT_EVIDENCE),
        ingest_permitted=True,
    )


async def run_c2(bundle):
    # TEST CONFIGURATION ONLY: these are not production capacity defaults.
    lane = LaneTarget("c2.r1")
    plugin = C2R1Plugin(C2R1Config.reference_engine_v1(), max_state_entries=20)
    results, controls = [], []

    async def writer(result, target):
        results.append(result)

    async def control(event):
        controls.append(event)

    supervisor = RuntimeSupervisor(
        {lane: plugin}, {lane: c2_governance()}, writer, shard_count=1,
        control_sink=control,
        reorder_policies={lane: EventTimeReorderPolicy(10)},
    )
    summary = await ReplayRunner(
        NdjsonReplaySource(bundle), supervisor, control_sink=control,
    ).run()
    return summary, results, controls, supervisor, lane


async def test_c2_stateful_replay_watermarks_and_eof_flush():
    summary, results, controls, supervisor, lane = await run_c2(FIXTURES / "c2_r1")
    assert summary.records_read == 3
    assert len(results) == 3
    assert results[-1].status_snapshot.readiness.value == "READY"
    watermark_events = [event for event in controls if event.control_type is ControlType.WATERMARK_ADVANCED]
    assert [event.event_time.isoformat() for event in watermark_events] == [
        "2026-01-01T00:01:00+00:00", "2026-01-01T00:02:00+00:00",
        "2026-01-01T00:02:00.000001+00:00",
    ]
    assert supervisor.dispatchers[lane].pending_reorder_count == 0


async def test_same_time_records_are_admitted_before_next_boundary(tmp_path):
    original = FIXTURES / "c2_r1"
    bundle = tmp_path / "same-time"
    bundle.mkdir()
    manifest = json.loads((original / "manifest.json").read_text(encoding="utf-8"))
    records = [json.loads(line) for line in (original / "records.ndjson").read_text(encoding="utf-8").splitlines()]
    records[1]["timestamp"] = records[0]["timestamp"]
    records[1]["payload"]["start_time"] = records[0]["payload"]["start_time"]
    records[1]["payload"]["end_time"] = records[0]["payload"]["end_time"]
    records[1]["payload"]["export_time"] = records[0]["payload"]["export_time"]
    (bundle / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (bundle / "records.ndjson").write_text(
        "\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8"
    )
    _, results, controls, _, _ = await run_c2(bundle)
    assert len(results) == 3
    assert not any(event.control_type is ControlType.LATE_EVENT_OBSERVED for event in controls)
    watermark_events = [event for event in controls if event.control_type is ControlType.WATERMARK_ADVANCED]
    assert len(watermark_events) == 2


def test_default_registry_keeps_c2_r1_gated():
    plugins, _ = build_mvp_provider_registry(NOW)
    assert LaneTarget("c2") in plugins
    assert LaneTarget("c2.r1") not in plugins
