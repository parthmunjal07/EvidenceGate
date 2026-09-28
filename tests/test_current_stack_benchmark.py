"""Real current-stack benchmark harness contract tests."""

from pathlib import Path

import pytest

from scripts.benchmark_current_stack import (
    CLASSIFICATION,
    WATERMARK,
    markdown_report,
    run_characterization,
)


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.asyncio
async def test_real_benchmark_uses_both_sources_disk_sqlite_and_default_registry() -> None:
    payload = await run_characterization(ROOT)
    assert payload["classification"] == CLASSIFICATION
    assert payload["watermark"] == WATERMARK
    assert payload["production_throughput_claim"] is False
    assert payload["default_target_count"] == 16
    assert {item["source_type"] for item in payload["runs"]} == {"NDJSON", "PCAP"}
    for run in payload["runs"]:
        assert run["speed"] == 0
        assert run["database"]["type"] == "disk-backed SQLite"
        assert run["active_target_count"] == 16
        assert run["counters"]["records_or_packets_read"] == 11
        assert run["counters"]["canonical_observations_emitted"] == 11
        assert run["counters"]["routed_mechanism_updates"] > 11
        assert run["counters"]["results_finalized"] == run["counters"]["results_persisted"]
        assert run["zero_drop"] is True
        assert run["timing"]["persist_latency"]["p99_ms"] is not None
    report = markdown_report(payload)
    assert "NOT PRODUCTION THROUGHPUT" in report
    assert "DGA model inference is not active" in report
