"""Final model-inclusive benchmark harness contract tests."""
from pathlib import Path

import pytest

from scripts.benchmark_final_mvp import (
    CLASSIFICATION, WATERMARK, markdown_report, run_characterization,
)


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.asyncio
async def test_final_benchmark_is_model_inclusive_no_drop_and_pcap_truthful():
    payload = await run_characterization(ROOT)
    assert payload["classification"] == CLASSIFICATION
    assert payload["watermark"] == WATERMARK
    assert payload["production_sizing_claim"] is False
    assert payload["default_target_count"] == 16
    assert payload["model"]["readiness"] == "VERIFIED_READY"
    assert payload["model"]["model_input"] == "ajdkskqweoiuzx.com"
    assert payload["model"]["observed_score"] == pytest.approx(0.9851716132182514, abs=1e-12)
    runs = {item["source_type"]: item for item in payload["runs"]}
    assert runs["TYPED_NDJSON"]["dga_exercised"] is True
    assert runs["RAW_PCAP"]["dga_exercised"] is False
    assert all(item["zero_drop"] is True for item in runs.values())
    assert all(item["active_target_count"] == 16 for item in runs.values())
    assert all(item["database"]["type"] == "disk-backed SQLite" for item in runs.values())
    assert runs["TYPED_NDJSON"]["mechanism_result_counts"]["DGA-A1-M1"] == 1
    report = markdown_report(payload)
    assert "NOT PRODUCTION SIZING" in report
    assert "raw-PCAP run does **not** exercise DGA" in report
