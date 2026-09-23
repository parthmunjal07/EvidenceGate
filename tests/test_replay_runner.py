"""Replay-to-runtime integration, persistence, and event-time boundary tests."""
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from evidencegate.domain.enums import ControlType, ResultType, ScientificStatus
from evidencegate.domain.governance import LaneGovernance
from evidencegate.ingest.replay import NdjsonReplaySource, ReplayCanonicalizer, ReplayRunner
from evidencegate.persistence.sqlite import SqliteWriter
from evidencegate.plugins.providers.c2 import C2R1Plugin
from evidencegate.plugins.providers.c2_config import C2R1Config
from evidencegate.plugins.providers.registry import (
    build_mvp_provider_registry, build_mvp_runtime_registration,
)
from evidencegate.routing.router import LaneTarget
from evidencegate.runtime.dispatcher import EventTimeReorderPolicy
from evidencegate.runtime.supervisor import RuntimeSupervisor


FIXTURES = Path("tests/fixtures/replay")
NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
SCHEMA = Path("evidencegate/persistence/schema.sql")


async def run_default(bundle, database, *, clock=None, canonicalizer=None):
    sqlite = SqliteWriter(database, SCHEMA)
    sqlite.connect()
    results, controls = [], []

    async def writer(result, target):
        results.append(result)
        await sqlite.write_result(result)

    async def control(event):
        controls.append(event)

    registration = build_mvp_runtime_registration(NOW)
    plugins, governances = registration.plugins, registration.governances
    supervisor = RuntimeSupervisor(
        plugins, governances, writer, shard_count=1, control_sink=control,
        reorder_policies=registration.reorder_policies,
    )
    summary = await ReplayRunner(
        NdjsonReplaySource(bundle), supervisor, control_sink=control,
        clock=clock or (lambda: NOW), canonicalizer=canonicalizer,
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
    expected_count = 2 if fixture == "dns_forward" else 1
    assert len(results) == len(persisted) == expected_count
    result = next(item for item in results if item.mechanism_id == mechanism)
    assert result.result_type is ResultType.REVIEW_FINDING
    assert [event.control_type for event in controls if event.source_id] == [
        ControlType.SOURCE_STARTED, ControlType.SOURCE_ENDED,
    ]


async def test_repeated_replay_has_deterministic_scientific_ids(tmp_path):
    first = await run_default(
        FIXTURES / "dns_forward", tmp_path / "one.sqlite",
        clock=lambda: datetime(2026, 9, 21, 12, tzinfo=timezone.utc),
    )
    second = await run_default(
        FIXTURES / "dns_forward", tmp_path / "two.sqlite",
        clock=lambda: datetime(2026, 9, 22, 12, tzinfo=timezone.utc),
    )
    assert first[1][0].result_id == second[1][0].result_id
    assert first[1][0].evidence == second[1][0].evidence


async def test_mixed_direction_replay_is_deterministic_and_keeps_event_time(tmp_path):
    first_canonicalizer = RecordingCanonicalizer()
    second_canonicalizer = RecordingCanonicalizer()
    first = await run_default(
        FIXTURES / "mixed_direction", tmp_path / "mixed-one.sqlite",
        canonicalizer=first_canonicalizer,
    )
    second = await run_default(
        FIXTURES / "mixed_direction", tmp_path / "mixed-two.sqlite",
        canonicalizer=second_canonicalizer,
    )
    assert first[0].records_read == second[0].records_read == 3
    assert first_canonicalizer.observations == second_canonicalizer.observations
    assert [item.event_time.isoformat() for item in first_canonicalizer.observations] == [
        "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:01+00:00",
        "2026-01-01T00:00:02+00:00",
    ]


class RecordingCanonicalizer(ReplayCanonicalizer):
    def __init__(self):
        super().__init__()
        self.observations = []

    def canonicalize(self, *args, **kwargs):
        result = super().canonicalize(*args, **kwargs)
        self.observations.extend(result.observations)
        return result


async def test_replay_ingest_clock_does_not_change_observation_identity(tmp_path):
    first_canonicalizer = RecordingCanonicalizer()
    second_canonicalizer = RecordingCanonicalizer()
    await run_default(
        FIXTURES / "dns_forward", tmp_path / "first.sqlite",
        clock=lambda: datetime(2026, 9, 21, 12, tzinfo=timezone.utc),
        canonicalizer=first_canonicalizer,
    )
    await run_default(
        FIXTURES / "dns_forward", tmp_path / "second.sqlite",
        clock=lambda: datetime(2026, 9, 22, 12, tzinfo=timezone.utc),
        canonicalizer=second_canonicalizer,
    )
    assert first_canonicalizer.observations[0].observation_id == second_canonicalizer.observations[0].observation_id


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


async def run_c2(bundle, *, clock=None, canonicalizer=None, speed=0):
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
        reorder_policies={lane: EventTimeReorderPolicy(10, 100)},
    )
    summary = await ReplayRunner(
        NdjsonReplaySource(bundle), supervisor, control_sink=control,
        clock=clock or (lambda: NOW), canonicalizer=canonicalizer, speed=speed,
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


async def test_replay_separates_per_record_ingest_clock_from_source_event_time():
    arrivals = iter([
        datetime(2026, 9, 21, 12, 0, 0, tzinfo=timezone.utc),  # SOURCE_STARTED
        datetime(2026, 9, 21, 12, 0, 0, 5000, tzinfo=timezone.utc),
        datetime(2026, 9, 21, 12, 0, 0, 9000, tzinfo=timezone.utc),
        datetime(2026, 9, 21, 12, 0, 0, 12000, tzinfo=timezone.utc),
        datetime(2026, 9, 21, 12, 0, 1, tzinfo=timezone.utc),  # SOURCE_ENDED
    ])
    canonicalizer = RecordingCanonicalizer()
    _, _, controls, _, _ = await run_c2(
        FIXTURES / "c2_r1", clock=lambda: next(arrivals), canonicalizer=canonicalizer,
    )
    assert [item.ingest_time for item in canonicalizer.observations] == [
        datetime(2026, 9, 21, 12, 0, 0, 5000, tzinfo=timezone.utc),
        datetime(2026, 9, 21, 12, 0, 0, 9000, tzinfo=timezone.utc),
        datetime(2026, 9, 21, 12, 0, 0, 12000, tzinfo=timezone.utc),
    ]
    assert [item.event_time for item in canonicalizer.observations] == [
        datetime(2026, 1, 1, 0, minute, tzinfo=timezone.utc) for minute in range(3)
    ]
    source_controls = [item for item in controls if item.control_type in {
        ControlType.SOURCE_STARTED, ControlType.SOURCE_ENDED,
    }]
    assert [item.ingest_time for item in source_controls] == [
        datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc),
        datetime(2026, 9, 21, 12, 0, 1, tzinfo=timezone.utc),
    ]
    assert source_controls[1].event_time == datetime(2026, 1, 1, 0, 2, tzinfo=timezone.utc)


@pytest.mark.parametrize("clock,exception", [
    (lambda: datetime(2026, 9, 21, 12), ValueError),
    (lambda: "2026-09-21T12:00:00Z", TypeError),
])
async def test_replay_rejects_invalid_clock_output(clock, exception):
    with pytest.raises(exception, match="clock must return"):
        await run_c2(FIXTURES / "c2_r1", clock=clock)


async def test_replay_pacing_remains_based_on_source_event_time(monkeypatch):
    sleeps = []

    async def record_sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr("evidencegate.ingest.replay.asyncio.sleep", record_sleep)
    await run_c2(
        FIXTURES / "c2_r1", speed=60,
        clock=lambda: datetime(2026, 9, 21, 12, tzinfo=timezone.utc),
    )
    assert sleeps == [1.0, 1.0]


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


def test_default_registration_activates_c2_r1_with_approved_capacity():
    plugins, _ = build_mvp_provider_registry(NOW)
    registration = build_mvp_runtime_registration(NOW)
    assert LaneTarget("c2.r1") in plugins
    assert LaneTarget("c2") not in plugins
    assert plugins[LaneTarget("c2.r1")].manifest().mechanism_id == "C2-M1"
    assert registration.reorder_policies[LaneTarget("c2.r1")] == EventTimeReorderPolicy(16, 2048)


def test_default_plugins_remain_fail_closed_without_their_registration_policy():
    async def writer(result, target):
        pass

    registration = build_mvp_runtime_registration(NOW)
    with pytest.raises(ValueError, match="requires an explicit event-time reorder policy"):
        RuntimeSupervisor(registration.plugins, registration.governances, writer)


async def test_default_c2_replay_persists_ready_measurement_and_decision_provenance(tmp_path):
    summary, results, _, persisted = await run_default(
        FIXTURES / "c2_r1", tmp_path / "c2-default.sqlite",
    )
    assert summary.records_read == 3
    c2_results = [result for result in results if result.mechanism_id == "C2-M1"]
    c2_persisted = [result for result in persisted if result.mechanism_id == "C2-M1"]
    assert len(c2_results) == len(c2_persisted) == 3
    assert [result.result_type for result in c2_results] == [
        ResultType.INSUFFICIENT_EVIDENCE, ResultType.INSUFFICIENT_EVIDENCE,
        ResultType.REVIEW_FINDING,
    ]
    assert c2_results[-1].status_snapshot.readiness.value == "READY"
    assert c2_results[-1].evidence.to_value()["measurements"] == {
        "event_count": 3, "history_span_seconds": 120.0, "interval_count": 2,
        "iat_median_seconds": 60.0, "iat_mad_seconds": 0.0,
    }
    assert all("C2-DEC-MVP-CAPACITY-V1" in result.governing_ids for result in c2_results)
