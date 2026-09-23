"""Contract tests for the sustained offered-rate harness."""
from __future__ import annotations

import pytest

from scripts.benchmark_sustained_final_mvp import (
    MIX_COUNTS, backlog_assessment, choose_candidate, load_workload_templates,
    latency_stability, percentiles_seconds, repeated_observation,
)


@pytest.mark.asyncio
async def test_repeated_mixed_workload_is_deterministic_causal_and_all_family_eligible():
    templates = await load_workload_templates()
    assert len(templates) == 9
    assert {item.observation_type.value for item in templates} == set(MIX_COUNTS)
    first = repeated_observation(templates, 0, "test")
    next_episode = repeated_observation(templates, 9, "test")
    assert first.observation_id != next_episode.observation_id
    assert first.source_id != next_episode.source_id
    assert next_episode.event_time > first.event_time
    assert first.causal_available_time >= first.event_time
    c2_one = repeated_observation(templates, 2, "test")
    c2_two = repeated_observation(templates, 3, "test")
    assert c2_one.typed_payload.start_time == c2_one.event_time
    assert c2_two.event_time > c2_one.event_time


def test_metrics_and_candidate_rule_require_repetition_and_margin():
    assert percentiles_seconds([0.001, 0.002, 0.003])["p95_ms"] == 3.0
    samples = [
        {"elapsed_seconds": 0.0, "total": 2},
        {"elapsed_seconds": 1.0, "total": 3},
        {"elapsed_seconds": 2.0, "total": 2},
        {"elapsed_seconds": 3.0, "total": 2},
    ]
    assert backlog_assessment(samples, 0)["stable"] is True
    assert latency_stability([0.1] * 4 + [0.12] * 4)["stable"] is True
    runs = [
        {"rate_requested_obs_s": rate, "sustainable": True}
        for rate in (100, 200, 200, 200)
    ]
    assert choose_candidate(runs) == (200, 100)
    runs[-1]["sustainable"] = False
    assert choose_candidate(runs) == (None, None)
