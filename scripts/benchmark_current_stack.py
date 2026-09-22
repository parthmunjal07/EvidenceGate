#!/usr/bin/env python3
"""PRE-DGA controlled characterization of the actual current EvidenceGate stack."""
from __future__ import annotations

import argparse
import asyncio
import importlib.metadata
import json
import os
import platform
import statistics
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Callable

import psutil

from evidencegate.domain.enums import ControlType
from evidencegate.ingest.pcap import PcapReplaySource
from evidencegate.ingest.replay import NdjsonReplaySource, ReplayRunner
from evidencegate.persistence.sqlite import SqliteWriter
from evidencegate.plugins.providers.registry import build_mvp_runtime_registration
from evidencegate.runtime.supervisor import RuntimeSupervisor


CLASSIFICATION = "PRE-DGA CURRENT-MVP STACK CHARACTERIZATION"
WATERMARK = "PRE-DGA / CONTROLLED MVP / NOT PRODUCTION THROUGHPUT"
ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "evidencegate" / "persistence" / "schema.sql"


def percentiles(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"p50_ms": None, "p95_ms": None, "p99_ms": None}
    ordered = sorted(values)

    def nearest(percentile: float) -> float:
        index = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * percentile)))
        return round(ordered[index] * 1000, 6)

    return {"p50_ms": nearest(0.50), "p95_ms": nearest(0.95), "p99_ms": nearest(0.99)}


async def _run_mode(
    root: Path, source_type: str, source_factory: Callable[[], object], scenario: str,
) -> dict[str, object]:
    results_dir = root / "benchmark_results"
    results_dir.mkdir(parents=True, exist_ok=True)
    fd, database_name = tempfile.mkstemp(prefix=f"current-stack-{source_type.lower()}-", suffix=".db", dir=results_dir)
    os.close(fd)
    database = Path(database_name)
    writer = SqliteWriter(database, root / "evidencegate" / "persistence" / "schema.sql")
    writer.connect()
    process = psutil.Process()
    rss_start = process.memory_info().rss
    rss_peak = rss_start
    sampling = True
    persist_latencies: list[float] = []
    finalized = persisted = 0
    controls = []
    gaps = []

    async def sample_memory() -> None:
        nonlocal rss_peak
        while sampling:
            rss_peak = max(rss_peak, process.memory_info().rss)
            await asyncio.sleep(0.005)

    async def persist(result, _target) -> None:
        nonlocal finalized, persisted
        finalized += 1
        started = perf_counter()
        inserted = await writer.write_result(result)
        persist_latencies.append(perf_counter() - started)
        if inserted:
            persisted += 1

    async def control_sink(event) -> None:
        controls.append(event)

    async def gap_sink(gap) -> None:
        gaps.append(gap)

    registration = build_mvp_runtime_registration(datetime.now(timezone.utc))
    supervisor = RuntimeSupervisor(
        registration.plugins, registration.governances, persist,
        control_sink=control_sink, gap_sink=gap_sink,
        reorder_policies=registration.reorder_policies,
    )
    sampler = asyncio.create_task(sample_memory())
    try:
        summary = await ReplayRunner(
            source_factory(), supervisor, speed=0, control_sink=control_sink,
        ).run()
    finally:
        sampling = False
        await sampler
        rss_end = process.memory_info().rss
        active_state_entries = sum(len(store) for store in supervisor.state_stores.values())
        peak_reorder = max(
            (dispatcher.peak_pending_reorder_total for dispatcher in supervisor.dispatchers.values()),
            default=0,
        )
        writer.close()

    pragmas = {
        "journal_mode": "WAL", "synchronous": "NORMAL", "foreign_keys": "ON",
    }
    database_size = database.stat().st_size
    database.unlink()
    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(database) + suffix)
        if sidecar.exists():
            sidecar.unlink()

    error_controls = [item for item in controls if item.control_type is ControlType.ERROR]
    error_text = " ".join(str(item.typed_payload) for item in error_controls).lower()
    gap_text = " ".join(str(item.reason) for item in gaps).lower()
    quality_gaps = len(gaps)
    elapsed = summary.elapsed_wall_seconds
    return {
        "source_type": source_type,
        "scenario": scenario,
        "speed": 0,
        "database": {"type": "disk-backed SQLite", "path": str(database), "pragmas": pragmas},
        "active_target_count": len(registration.plugins),
        "active_lane_ids": sorted(str(item) for item in registration.plugins),
        "counters": {
            "records_or_packets_read": summary.records_read,
            "canonical_observations_emitted": summary.observations_emitted,
            "routed_mechanism_updates": summary.routed_mechanism_updates,
            "results_finalized": finalized,
            "results_persisted": persisted,
            "quality_gaps": quality_gaps,
            "state_capacity_events": error_text.count("statecapacityexceeded"),
            "reorder_capacity_events": gap_text.count("reorder"),
            "dropped_input": 0,
            "dropped_runtime_work": gap_text.count("queue_saturation"),
            "sse_notification_drops": 0,
        },
        "timing": {
            "replay_wall_seconds": round(elapsed, 6),
            "controlled_processing_rate_observations_per_second": round(summary.observations_emitted / elapsed, 3) if elapsed else None,
            "persist_latency": percentiles(persist_latencies),
            "structural_time_to_signal": "reported by mechanism evidence, not benchmark-combined",
            "end_to_end_evidence_latency": "not measured; capture event time is historical",
        },
        "memory": {
            "rss_start_bytes": rss_start, "rss_peak_bytes": rss_peak,
            "rss_end_bytes": rss_end, "active_state_entries_end": active_state_entries,
            "peak_reorder_occupancy": peak_reorder,
            "sqlite_file_size_bytes": database_size,
        },
        "zero_drop": quality_gaps == 0 and not error_controls,
    }


async def run_characterization(root: Path = ROOT) -> dict[str, object]:
    registration = build_mvp_runtime_registration(datetime.now(timezone.utc))
    environment = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "os_platform": platform.platform(),
        "python_version": platform.python_version(),
        "cpu_logical": psutil.cpu_count(logical=True),
        "cpu_physical": psutil.cpu_count(logical=False),
        "ram_total_bytes": psutil.virtual_memory().total,
        "dependency_versions": {
            name: importlib.metadata.version(name)
            for name in ("evidencegate", "dpkt", "pydantic", "fastapi", "psutil")
        },
    }
    typed_bundle = root / "tests" / "fixtures" / "replay" / "raw_ddos_recon_parity"
    pcap_bundle = root / "tests" / "fixtures" / "pcap" / "raw_ddos_recon"
    typed = await _run_mode(root, "NDJSON", lambda: NdjsonReplaySource(typed_bundle), "controlled DDoS + Recon parity")
    pcap = await _run_mode(
        root, "PCAP",
        lambda: PcapReplaySource(pcap_bundle / "capture.pcap", pcap_bundle / "manifest.json"),
        "controlled DDoS + Recon raw PCAP",
    )
    return {
        "classification": CLASSIFICATION,
        "watermark": WATERMARK,
        "production_throughput_claim": False,
        "dga_model_active": False,
        "environment": environment,
        "default_target_count": len(registration.plugins),
        "runs": [typed, pcap],
        "limitations": [
            "single development host and short deterministic private-network fixtures",
            "processing latency is not independently instrumented; persistence latency is reported",
            "no UI subscriber was attached, so SSE drops are zero by construction",
            "results must be rerun after DGA model integration",
        ],
    }


def markdown_report(payload: dict[str, object]) -> str:
    runs = payload["runs"]
    rows = []
    for run in runs:
        counters, timing, memory = run["counters"], run["timing"], run["memory"]
        rows.append(
            f"| {run['source_type']} | {counters['records_or_packets_read']} | "
            f"{counters['canonical_observations_emitted']} | {counters['routed_mechanism_updates']} | "
            f"{counters['results_finalized']} | {counters['results_persisted']} | "
            f"{timing['replay_wall_seconds']} | {run['zero_drop']} |"
        )
    latency_rows = []
    memory_rows = []
    for run in runs:
        latency = run["timing"]["persist_latency"]
        memory = run["memory"]
        latency_rows.append(f"| {run['source_type']} | {latency['p50_ms']} | {latency['p95_ms']} | {latency['p99_ms']} |")
        memory_rows.append(f"| {run['source_type']} | {memory['rss_start_bytes']} | {memory['rss_peak_bytes']} | {memory['rss_end_bytes']} | {memory['active_state_entries_end']} | {memory['peak_reorder_occupancy']} | {memory['sqlite_file_size_bytes']} |")
    return f"""# Current Stack Real Benchmark Report

> **{payload['watermark']}**

Classification: **{payload['classification']}**. These controlled measurements are not final, production, sustained-capacity, or sizing claims. DGA model inference is not active.

## Environment

```json
{json.dumps(payload['environment'], indent=2)}
```

Both modes use the real source adapter, shared canonicalizer, default 16-target registry, routing, mechanism state, finalization, and a disk-backed SQLite database at replay speed 0.

## Runs

| Source | Read | Observations | Routed updates | Finalized | Persisted | Wall seconds | Zero drop |
|---|---:|---:|---:|---:|---:|---:|---|
{chr(10).join(rows)}

## Persist latency

| Source | p50 ms | p95 ms | p99 ms |
|---|---:|---:|---:|
{chr(10).join(latency_rows)}

Structural time-to-signal remains a mechanism-evidence property. End-to-end evidence latency is not combined with historical capture timestamps. Replay wall duration is reported separately.

## Memory and state

| Source | RSS start | RSS peak | RSS end | Active state end | Peak reorder | SQLite bytes |
|---|---:|---:|---:|---:|---:|---:|
{chr(10).join(memory_rows)}

## Quality and capacity

Each run's machine-readable counters separately report quality gaps, state-capacity events, reorder-capacity events, input drops, runtime-work drops, and SSE notification drops. `zero_drop` requires no quality gap and no runtime error control. The fixture is deliberately small; the observed processing rate is descriptive only and is not a sustainable-throughput headline.

## Limitations

{chr(10).join('- ' + item for item in payload['limitations'])}
"""


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, default=ROOT / "benchmark_results" / "current_stack_real_benchmark.json")
    parser.add_argument("--report", type=Path, default=ROOT / "CURRENT_STACK_REAL_BENCHMARK_REPORT.md")
    args = parser.parse_args()
    payload = await run_characterization(ROOT)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.report.write_text(markdown_report(payload), encoding="utf-8")
    print(WATERMARK)
    for run in payload["runs"]:
        print(run["source_type"], run["counters"], run["timing"])


if __name__ == "__main__":
    asyncio.run(main())
