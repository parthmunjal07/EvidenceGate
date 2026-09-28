#!/usr/bin/env python3
"""Final controlled model-inclusive EvidenceGate stack characterization."""

from __future__ import annotations

import argparse
import asyncio
import importlib.metadata
import json
import os
import platform
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Callable

import psutil

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evidencegate.domain.enums import ControlType
from evidencegate.ingest.pcap import PcapReplaySource
from evidencegate.ingest.replay import NdjsonReplaySource, ReplayRunner
from evidencegate.persistence.sqlite import SqliteWriter
from evidencegate.plugins.providers.dga_m1 import (
    ARTIFACT_SHA256,
    DgaM1Plugin,
    DgaM1Readiness,
)
from evidencegate.plugins.providers.registry import (
    MvpRuntimeRegistration,
    build_mvp_runtime_registration,
)
from evidencegate.runtime.supervisor import RuntimeSupervisor


CLASSIFICATION = "CONTROLLED FINAL-MVP MODEL-INCLUSIVE STACK CHARACTERIZATION"
WATERMARK = "CONTROLLED MVP CHARACTERIZATION — NOT PRODUCTION SIZING"
MODEL_PATH = ROOT / "artifacts" / "dga" / "local" / "DGA_M1_R1_SERIALIZED_MODEL.joblib"


def percentiles(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"p50_ms": None, "p95_ms": None, "p99_ms": None}
    ordered = sorted(values)

    def nearest(fraction: float) -> float:
        index = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * fraction)))
        return round(ordered[index] * 1000, 6)

    return {"p50_ms": nearest(0.50), "p95_ms": nearest(0.95), "p99_ms": nearest(0.99)}


def dga_component_latencies(plugin: DgaM1Plugin, iterations: int = 30) -> dict[str, object]:
    """Measure the admitted components after startup, separate from model load."""
    from evidencegate.ingest.replay import NdjsonReplaySource, ReplayCanonicalizer

    async def canonical_observation():
        source = NdjsonReplaySource(ROOT / "tests" / "fixtures" / "replay" / "dga_lexical")
        manifest = await source.open()
        records = source.records()
        try:
            record = await anext(records)
            return (
                ReplayCanonicalizer()
                .canonicalize(
                    record,
                    manifest,
                    "quality:benchmark:dga",
                    record.timestamp,
                )
                .observations[0]
            )
        finally:
            await records.aclose()
            await source.close()

    observation = asyncio.run(canonical_observation())
    representation_times: list[float] = []
    inference_times: list[float] = []
    observed_score = None
    model_input = None
    for _ in range(iterations):
        started = perf_counter()
        representation = plugin.adapter.adapt(observation)
        representation_times.append(perf_counter() - started)
        model_input = representation.model_input
        if model_input is None:
            raise RuntimeError("controlled DGA benchmark input was not admitted")
        started = perf_counter()
        observed_score = plugin.service.score(model_input)
        inference_times.append(perf_counter() - started)
    return {
        "iterations": iterations,
        "model_input": model_input,
        "artifact_sha256": ARTIFACT_SHA256,
        "observed_score": observed_score,
        "score_regression_tolerance": 1e-12,
        "representation_latency": percentiles(representation_times),
        "transform_inference_latency": percentiles(inference_times),
    }


async def _run_mode(
    registration: MvpRuntimeRegistration,
    source_type: str,
    source_factory: Callable[[], object],
    scenario: str,
) -> dict[str, object]:
    results_dir = ROOT / "benchmark_results"
    results_dir.mkdir(parents=True, exist_ok=True)
    fd, database_name = tempfile.mkstemp(
        prefix=f"final-mvp-{source_type.lower()}-",
        suffix=".db",
        dir=results_dir,
    )
    os.close(fd)
    database = Path(database_name)
    writer = SqliteWriter(database, ROOT / "evidencegate" / "persistence" / "schema.sql")
    writer.connect()
    process = psutil.Process()
    rss_start = process.memory_info().rss
    rss_peak = rss_start
    sampling = True
    persist_latencies: list[float] = []
    dga_persist_latencies: list[float] = []
    processing_latencies: list[float] = []
    end_to_end_latencies: list[float] = []
    observation_started: dict[str, float] = {}
    finalized = persisted = 0
    controls = []
    gaps = []
    mechanisms: dict[str, int] = {}

    async def sample_memory() -> None:
        nonlocal rss_peak
        while sampling:
            rss_peak = max(rss_peak, process.memory_info().rss)
            await asyncio.sleep(0.002)

    async def persist(result, _target) -> None:
        nonlocal finalized, persisted
        finalized += 1
        mechanisms[result.mechanism_id] = mechanisms.get(result.mechanism_id, 0) + 1
        started = perf_counter()
        inserted = await writer.write_result(result)
        duration = perf_counter() - started
        persist_latencies.append(duration)
        if result.mechanism_id == "DGA-A1-M1":
            dga_persist_latencies.append(duration)
        if inserted:
            persisted += 1
        candidates = [
            observation_started[item]
            for item in result.source_observation_ids
            if item in observation_started
        ]
        if candidates:
            end_to_end_latencies.append(perf_counter() - min(candidates))

    async def control_sink(event) -> None:
        controls.append(event)

    async def gap_sink(gap) -> None:
        gaps.append(gap)

    supervisor = RuntimeSupervisor(
        registration.plugins,
        registration.governances,
        persist,
        control_sink=control_sink,
        gap_sink=gap_sink,
        reorder_policies=registration.reorder_policies,
    )
    original_ingest = supervisor.ingest_observation

    async def measured_ingest(observation):
        started = perf_counter()
        observation_started[observation.observation_id] = started
        plan = await original_ingest(observation)
        processing_latencies.append(perf_counter() - started)
        return plan

    supervisor.ingest_observation = measured_ingest  # type: ignore[method-assign]
    sampler = asyncio.create_task(sample_memory())
    try:
        summary = await ReplayRunner(
            source_factory(),
            supervisor,
            speed=0,
            control_sink=control_sink,
        ).run()
    finally:
        sampling = False
        await sampler
        rss_end = process.memory_info().rss
        rss_peak = max(rss_peak, rss_end)
        active_state_entries = sum(len(store) for store in supervisor.state_stores.values())
        peak_reorder = max(
            (
                dispatcher.peak_pending_reorder_total
                for dispatcher in supervisor.dispatchers.values()
            ),
            default=0,
        )
        writer.close()

    database_size = database.stat().st_size
    database.unlink()
    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(database) + suffix)
        if sidecar.exists():
            sidecar.unlink()
    error_controls = [item for item in controls if item.control_type is ControlType.ERROR]
    error_text = " ".join(str(item.typed_payload) for item in error_controls).lower()
    gap_text = " ".join(str(item.reason) for item in gaps).lower()
    counters = {
        "records_or_packets_read": summary.records_read,
        "canonical_observations_emitted": summary.observations_emitted,
        "routed_mechanism_updates": summary.routed_mechanism_updates,
        "results_finalized": finalized,
        "results_persisted": persisted,
        "quality_gaps": len(gaps),
        "state_capacity_events": error_text.count("statecapacityexceeded"),
        "reorder_capacity_events": gap_text.count("reorder"),
        "dropped_input": 0,
        "dropped_runtime_work": gap_text.count("queue_saturation"),
        "sse_notification_drops": 0,
    }
    zero_drop = (
        all(
            counters[key] == 0
            for key in (
                "quality_gaps",
                "state_capacity_events",
                "reorder_capacity_events",
                "dropped_input",
                "dropped_runtime_work",
            )
        )
        and not error_controls
    )
    elapsed = summary.elapsed_wall_seconds
    return {
        "source_type": source_type,
        "scenario": scenario,
        "speed": 0,
        "database": {
            "type": "disk-backed SQLite",
            "pragmas": {
                "journal_mode": "WAL",
                "synchronous": "NORMAL",
                "foreign_keys": "ON",
            },
        },
        "active_target_count": len(registration.plugins),
        "active_lane_ids": sorted(str(item) for item in registration.plugins),
        "mechanism_result_counts": mechanisms,
        "dga_exercised": mechanisms.get("DGA-A1-M1", 0) > 0,
        "counters": counters,
        "timing": {
            "replay_wall_seconds": round(elapsed, 6),
            "observed_processing_rate_observations_per_second": round(
                summary.observations_emitted / elapsed, 3
            )
            if elapsed
            else None,
            "processing_latency": percentiles(processing_latencies),
            "persistence_latency": percentiles(persist_latencies),
            "dga_result_persistence_latency": percentiles(dga_persist_latencies),
            "end_to_end_evidence_latency": percentiles(end_to_end_latencies),
            "structural_time_to_signal": "one admitted observation for stateless DGA/DNS/ENC/Exfil; stateful mechanisms retain their governed evidence windows",
        },
        "memory": {
            "rss_start_bytes": rss_start,
            "rss_peak_bytes": rss_peak,
            "rss_end_bytes": rss_end,
            "active_state_entries_end": active_state_entries,
            "peak_reorder_occupancy": peak_reorder,
            "sqlite_file_size_bytes": database_size,
        },
        "zero_drop": zero_drop,
    }


async def run_characterization(root: Path = ROOT) -> dict[str, object]:
    model_path = root / "artifacts" / "dga" / "local" / "DGA_M1_R1_SERIALIZED_MODEL.joblib"
    process = psutil.Process()
    rss_before = process.memory_info().rss
    started = perf_counter()
    registration = build_mvp_runtime_registration(
        datetime.now(timezone.utc),
        dga_model_path=str(model_path),
    )
    model_load_seconds = perf_counter() - started
    rss_after = process.memory_info().rss
    dga_plugin = registration.plugins["dga.m1"]
    if not isinstance(dga_plugin, DgaM1Plugin):
        raise RuntimeError("default dga.m1 plugin missing")
    if dga_plugin.readiness is not DgaM1Readiness.VERIFIED_READY:
        raise RuntimeError(dga_plugin.readiness_failure_reason or "DGA model unavailable")

    typed_bundle = root / "tests" / "fixtures" / "replay" / "final_mvp_mixed"
    pcap_bundle = root / "tests" / "fixtures" / "pcap" / "raw_ddos_recon"
    typed = await _run_mode(
        registration,
        "TYPED_NDJSON",
        lambda: NdjsonReplaySource(typed_bundle),
        "controlled mixed DDoS/C2/DGA/DNS/ENC/Recon/Exfil",
    )
    pcap = await _run_mode(
        registration,
        "RAW_PCAP",
        lambda: PcapReplaySource(pcap_bundle / "capture.pcap", pcap_bundle / "manifest.json"),
        "controlled DDoS + Recon raw PCAP; DNS extraction deferred",
    )
    component = await asyncio.to_thread(dga_component_latencies, dga_plugin)
    return {
        "classification": CLASSIFICATION,
        "watermark": WATERMARK,
        "production_sizing_claim": False,
        "environment": {
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "os_platform": platform.platform(),
            "python_version": platform.python_version(),
            "cpu_logical": psutil.cpu_count(logical=True),
            "cpu_physical": psutil.cpu_count(logical=False),
            "ram_total_bytes": psutil.virtual_memory().total,
            "dependency_versions": {
                name: importlib.metadata.version(name)
                for name in (
                    "evidencegate",
                    "dpkt",
                    "pydantic",
                    "fastapi",
                    "psutil",
                    "scikit-learn",
                    "joblib",
                    "tldextract",
                )
            },
        },
        "default_target_count": len(registration.plugins),
        "model": {
            "readiness": dga_plugin.readiness.value,
            "load_seconds": round(model_load_seconds, 6),
            "rss_before_load_bytes": rss_before,
            "rss_after_load_bytes": rss_after,
            "rss_delta_bytes": rss_after - rss_before,
            **component,
        },
        "workload_mix": {
            "typed_records": {"PACKET": 3, "FLOW": 4, "DNS": 1, "TLS": 1},
            "eligible_families": ["DDoS", "C2", "DGA M1", "DNS-T1", "ENC-A", "Recon", "Exfil-M1"],
            "raw_pcap_packets": 11,
        },
        "runs": [typed, pcap],
        "no_drop_region": "demonstrated for the two bounded replay points only; no offered-rate sweep exists in this harness",
        "proposed_sih_demo_throughput_target": None,
        "target_basis": "No target proposed from short deterministic fixtures; Control Room approval remains required.",
        "limitations": [
            "single development host and short deterministic private-network fixtures",
            "raw-PCAP DNS extraction is deferred, so the PCAP run does not exercise DGA",
            "no live interface capture and no NetFlow/IPFIX/sFlow adapter",
            "no sustained offered-rate sweep; observed replay rates are descriptive only",
            "SSE notification drops are zero by construction because no UI subscriber is attached",
        ],
    }


def markdown_report(payload: dict[str, object]) -> str:
    runs = payload["runs"]
    rows = []
    latency_rows = []
    memory_rows = []
    for run in runs:
        counters = run["counters"]
        rows.append(
            f"| {run['source_type']} | {counters['records_or_packets_read']} | "
            f"{counters['canonical_observations_emitted']} | {counters['routed_mechanism_updates']} | "
            f"{counters['results_persisted']} | {run['dga_exercised']} | {run['zero_drop']} |"
        )
        latency_rows.append(
            f"| {run['source_type']} | {run['timing']['processing_latency']['p50_ms']} | "
            f"{run['timing']['processing_latency']['p95_ms']} | {run['timing']['processing_latency']['p99_ms']} | "
            f"{run['timing']['persistence_latency']['p50_ms']} | {run['timing']['persistence_latency']['p95_ms']} | "
            f"{run['timing']['persistence_latency']['p99_ms']} | {run['timing']['end_to_end_evidence_latency']['p50_ms']} | "
            f"{run['timing']['end_to_end_evidence_latency']['p95_ms']} | {run['timing']['end_to_end_evidence_latency']['p99_ms']} |"
        )
        memory = run["memory"]
        memory_rows.append(
            f"| {run['source_type']} | {memory['rss_start_bytes']} | {memory['rss_peak_bytes']} | "
            f"{memory['rss_end_bytes']} | {memory['sqlite_file_size_bytes']} | "
            f"{memory['active_state_entries_end']} | {memory['peak_reorder_occupancy']} |"
        )
    model = payload["model"]
    return f"""# Final MVP Model-Inclusive Benchmark Report

> **{payload["watermark"]}**

Classification: **{payload["classification"]}**. This is not a production capacity, enterprise sizing, or SLA claim.

## Startup and DGA model

- Readiness: `{model["readiness"]}`
- Load time: `{model["load_seconds"]}` seconds
- RSS before/after/delta: `{model["rss_before_load_bytes"]}` / `{model["rss_after_load_bytes"]}` / `{model["rss_delta_bytes"]}` bytes
- Artifact: `{model["artifact_sha256"]}`
- Frozen model input / score: `{model["model_input"]}` / `{model["observed_score"]}` (regression tolerance `{model["score_regression_tolerance"]}`)
- DGA representation p50/p95/p99 ms: `{model["representation_latency"]}`
- DGA transform + inference p50/p95/p99 ms: `{model["transform_inference_latency"]}`
- DGA result persistence p50/p95/p99 ms (typed run): `{runs[0]["timing"]["dga_result_persistence_latency"]}`

The numeric output is a **DGA-labelled lexical resemblance score**, not malware, infection, compromise, C2, tunnel, exfiltration, ownership, intent, or attack probability. No production threshold is active.

## Workload and runs

Exact controlled mix: `{json.dumps(payload["workload_mix"], sort_keys=True)}`.

| Source | Read | Observations | Routed updates | Persisted | DGA exercised | Zero drop |
|---|---:|---:|---:|---:|---|---|
{chr(10).join(rows)}

The typed run exercises real DGA representation, vectorizer, classifier, routing, finalization, and disk-backed SQLite persistence. The raw-PCAP run does **not** exercise DGA because raw-PCAP DNS extraction remains deferred.

## Latency

| Source | Proc p50 | Proc p95 | Proc p99 | Persist p50 | Persist p95 | Persist p99 | E2E p50 | E2E p95 | E2E p99 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(latency_rows)}

Processing is routing/enqueue latency. Persistence is SQLite write latency. End-to-end is in-process observation admission through persisted evidence and is not combined with historical capture timestamps. Replay wall-clock and structural time-to-signal remain separately recorded in JSON.

## Memory, state, and storage

| Source | RSS start | RSS peak | RSS end | SQLite bytes | State entries end | Peak reorder |
|---|---:|---:|---:|---:|---:|---:|
{chr(10).join(memory_rows)}

## No-drop region and target

{payload["no_drop_region"]}. Proposed SIH demo throughput target: **NONE**. {payload["target_basis"]}

## Limitations

{chr(10).join("- " + item for item in payload["limitations"])}
"""


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json",
        type=Path,
        default=ROOT / "benchmark_results" / "final_mvp_model_inclusive_benchmark.json",
    )
    parser.add_argument(
        "--report", type=Path, default=ROOT / "FINAL_MVP_MODEL_INCLUSIVE_BENCHMARK_REPORT.md"
    )
    args = parser.parse_args()
    payload = await run_characterization(ROOT)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.report.write_text(markdown_report(payload), encoding="utf-8")
    print(WATERMARK)
    print(json.dumps({"model": payload["model"], "runs": payload["runs"]}, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
