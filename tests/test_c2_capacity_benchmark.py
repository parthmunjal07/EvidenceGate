"""Small deterministic tests for the C2-R1 capacity characterization harness."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from evidencegate.domain.enums import IdentityBasis
from evidencegate.ingest.replay import NdjsonReplaySource, ReplayCanonicalizer
from evidencegate.plugins.providers.registry import build_mvp_provider_registry
from evidencegate.routing.router import LaneTarget
from scripts.benchmark_c2_capacity import (
    C2CapacityExperimentConfig,
    classify_status,
    iter_workload_records,
    render_report,
    run_experiment,
    run_id,
    write_bundle,
)


def config(**changes) -> C2CapacityExperimentConfig:
    values = dict(
        workload="key_cardinality",
        active_key_count=3,
        events_per_key=3,
        same_timestamp_burst=1,
        max_state_entries=4,
        reorder_capacity=8,
        reorder_total_capacity=100,
        shard_count=1,
        repetition=1,
        database_mode="none",
    )
    values.update(changes)
    return C2CapacityExperimentConfig(**values)


def test_workload_generates_exact_key_cardinality_and_deterministic_records():
    value = config(active_key_count=5)
    first = list(iter_workload_records(value))
    second = list(iter_workload_records(value))
    clients = {item["role_assignments"][0]["identifier"] for item in first}
    assert first == second
    assert len(first) == 15
    assert len(clients) == 5
    assert run_id(value) == run_id(value)


def test_many_key_same_time_generator_has_exact_cardinality_and_boundary():
    value = config(
        workload="many_keys_same_time",
        active_key_count=5,
        events_per_key=2,
        same_timestamp_burst=2,
    )
    records = list(iter_workload_records(value))
    assert len(records) == 11
    assert len({item["role_assignments"][0]["identifier"] for item in records[:-1]}) == 5
    assert {item["timestamp"] for item in records[:-1]} == {"2026-01-01T00:00:00Z"}
    assert records[-1]["timestamp"] == "2026-01-01T00:00:01Z"


@pytest.mark.asyncio
async def test_bundle_preserves_trusted_source_declared_roles(tmp_path):
    bundle = tmp_path / "bundle"
    write_bundle(
        bundle,
        config(active_key_count=1),
    )
    source = NdjsonReplaySource(bundle)
    manifest = await source.open()
    records = source.records()
    try:
        record = await anext(records)
        observation = (
            ReplayCanonicalizer()
            .canonicalize(record, manifest, "quality:test", record.timestamp)
            .observations[0]
        )
    finally:
        await records.aclose()
        await source.close()
    assignments = observation.identity.role_assignments
    assert [item.role for item in assignments] == ["client_id", "peer_id", "peer_port"]
    assert all(item.basis is IdentityBasis.SOURCE_DECLARED_ROLE for item in assignments)


@pytest.mark.asyncio
async def test_max_entries_boundary_is_visible_without_arbitrary_eviction():
    result = await run_experiment(config(active_key_count=3, max_state_entries=2))
    assert result["peak_state_entries"] == 2
    assert result["counts"]["state_capacity_exceeded"] == 3
    assert result["counts"]["processing_errors"] == 0
    assert result["results"] == 6
    assert result["status"] == ["STATE_CAPACITY_EXCEEDED"]


@pytest.mark.asyncio
async def test_equal_state_capacity_is_accepted_cleanly():
    result = await run_experiment(config(active_key_count=3, max_state_entries=3))
    assert result["peak_state_entries"] == 3
    assert result["state_cardinality_matches_expected"] is True
    assert result["counts"]["state_capacity_exceeded"] == 0
    assert result["results"] == 9


@pytest.mark.asyncio
async def test_reorder_occupancy_and_saturation_are_exact():
    clean = await run_experiment(
        config(
            workload="same_time_burst",
            active_key_count=1,
            events_per_key=5,
            same_timestamp_burst=4,
            reorder_capacity=4,
        )
    )
    saturated = await run_experiment(
        config(
            workload="same_time_burst",
            active_key_count=1,
            events_per_key=5,
            same_timestamp_burst=4,
            reorder_capacity=2,
        )
    )
    assert clean["peak_reorder_per_key"] == 4
    assert clean["counts"]["reorder_saturation"] == 0
    assert saturated["peak_reorder_per_key"] == 2
    assert saturated["counts"]["reorder_saturation"] == 2
    assert saturated["status"] == ["SATURATED_REORDER"]


@pytest.mark.asyncio
async def test_many_keys_hit_total_bound_without_hitting_per_key_bound():
    clean = await run_experiment(
        config(
            workload="many_keys_same_time",
            active_key_count=4,
            events_per_key=2,
            same_timestamp_burst=2,
            reorder_capacity=4,
            reorder_total_capacity=8,
        )
    )
    saturated = await run_experiment(
        config(
            workload="many_keys_same_time",
            active_key_count=5,
            events_per_key=2,
            same_timestamp_burst=2,
            reorder_capacity=4,
            reorder_total_capacity=8,
        )
    )
    assert clean["peak_reorder_total"] == 8
    assert clean["peak_reorder_per_key"] == 2
    assert clean["counts"]["reorder_total_saturation"] == 0
    assert saturated["peak_reorder_total"] == 8
    assert saturated["peak_reorder_per_key"] == 2
    assert saturated["counts"]["reorder_saturation"] == 0
    assert saturated["counts"]["reorder_total_saturation"] == 2
    assert saturated["results"] == 9
    assert saturated["status"] == ["SATURATED_REORDER_TOTAL"]
    assert saturated["memory"]["reorder_at_peak"]["pending_observations"] == 8


def test_failure_categories_remain_separate():
    counts = {
        "reorder_saturation": 1,
        "ingress_queue_saturation": 2,
        "shard_queue_saturation": 0,
        "state_capacity_exceeded": 3,
        "processing_errors": 4,
    }
    assert classify_status(counts) == [
        "SATURATED_REORDER",
        "SATURATED_QUEUE",
        "STATE_CAPACITY_EXCEEDED",
        "PROCESSING_ERROR",
    ]


@pytest.mark.asyncio
async def test_clean_workload_has_zero_gaps_errors_and_real_results():
    result = await run_experiment(config())
    assert result["status"] == ["CLEAN"]
    assert result["counts"]["quality_gaps"] == 0
    assert result["counts"]["processing_errors"] == 0
    assert result["results"] == result["observations"]
    assert result["result_types"] == {
        "INSUFFICIENT_EVIDENCE": 6,
        "REVIEW_FINDING": 3,
    }


@pytest.mark.asyncio
async def test_real_sqlite_persists_every_finalized_result(tmp_path):
    result = await run_experiment(config(database_mode="sqlite"), working_directory=tmp_path)
    assert result["sqlite_results"] == result["results"] == 9
    assert (tmp_path / "results.sqlite3").is_file()


def test_report_and_config_serialization_are_deterministic():
    run = {
        "run_id": "run-1",
        "config": {
            "workload": "key_cardinality",
            "active_key_count": 1,
            "events_per_key": 3,
            "same_timestamp_burst": 1,
            "max_state_entries": 1,
            "reorder_capacity": 1,
            "reorder_total_capacity": 1,
        },
        "status": ["CLEAN"],
        "peak_state_entries": 1,
        "peak_reorder_total": 1,
        "peak_reorder_per_key": 1,
        "observations": 3,
        "results": 3,
        "elapsed_seconds": 1.0,
        "successfully_processed_observations_per_second": 3.0,
        "memory": {"tracemalloc_peak_bytes": 10},
        "counts": {"quality_gaps": 0, "state_capacity_exceeded": 0, "processing_errors": 0},
    }
    payload = {
        "runs": [run],
        "environment": {
            "captured_at": "time",
            "os": "os",
            "python": "py",
            "cpu_model": "cpu",
            "logical_cpu_count": 1,
            "available_memory_bytes": "unavailable",
            "git_commit": "sha",
        },
        "scientific_config": {
            "minimum_history_events": 3,
            "max_retained_events_per_pair": 32,
            "state_ttl_seconds": 3600,
            "event_basis": "FLOW_START",
        },
    }
    assert render_report(payload) == render_report(json.loads(json.dumps(payload)))


def test_benchmark_default_registry_activates_c2_r1():
    plugins, _ = build_mvp_provider_registry(datetime.now(timezone.utc))
    assert LaneTarget("c2.r1") in plugins
    assert LaneTarget("c2") not in plugins


def test_safety_ceiling_requires_explicit_override():
    value = config(active_key_count=100_001, events_per_key=1)
    with pytest.raises(ValueError, match="allow-large"):
        value.validate_safety()
    value.validate_safety(allow_large=True)


def test_benchmark_total_reorder_capacity_must_cover_per_key_capacity():
    with pytest.raises(ValueError, match="cannot be less"):
        config(reorder_capacity=8, reorder_total_capacity=7)
