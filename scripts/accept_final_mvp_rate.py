#!/usr/bin/env python3
"""One post-activation acceptance point at the approved controlled demo rate."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from scripts.benchmark_sustained_final_mvp import (
    ARTIFACT_SHA256,
    ELIGIBLE_FAMILIES,
    MIX_COUNTS,
    MODEL_PATH,
    ROOT,
    build_mvp_runtime_registration,
    environment_snapshot,
    load_workload_templates,
    run_rate_point,
)
from evidencegate.plugins.providers.dga_m1 import DgaM1Readiness


async def main() -> None:
    registration = build_mvp_runtime_registration(
        datetime.now(timezone.utc),
        dga_model_path=str(MODEL_PATH),
    )
    dga = registration.plugins["dga.m1"]
    if dga.readiness is not DgaM1Readiness.VERIFIED_READY:
        raise RuntimeError(dga.readiness_failure_reason or "DGA artifact unavailable")
    templates = await load_workload_templates()
    warmup = await run_rate_point(
        registration,
        templates,
        rate=25,
        duration_seconds=3.0,
        replicate=0,
    )
    measured = await run_rate_point(
        registration,
        templates,
        rate=50,
        duration_seconds=30.0,
        replicate=1,
        probe_alerts=True,
    )
    payload = {
        "classification": "POST-ACTIVATION CONTROLLED MVP ACCEPTANCE",
        "environment": environment_snapshot(),
        "policy_version": "SIH_ALERT_POLICY_V1",
        "model_sha256": ARTIFACT_SHA256,
        "default_targets": list(registration.plugins),
        "workload": {
            "fixture": "tests/fixtures/replay/final_mvp_mixed",
            "typed_mix_counts": MIX_COUNTS,
            "eligible_families": ELIGIBLE_FAMILIES,
            "warmup_seconds": 3.0,
            "warmup_excluded": True,
        },
        "warmup": warmup,
        "measured": measured,
    }
    output = ROOT / "benchmark_results" / "final_mvp_acceptance.json"
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "sustainable": measured["sustainable"],
                "offered_obs_s": measured["rates"]["offered_obs_s"],
                "drops": measured["drops"],
                "peak_backlog": measured["backlog"]["peak"],
                "api_probes": len(measured["api_probe"]["samples"]),
                "artifact": str(output),
            },
            indent=2,
        )
    )
    if not measured["sustainable"]:
        raise SystemExit("post-activation acceptance failed")


if __name__ == "__main__":
    asyncio.run(main())
