"""C2-R1 controlled synthetic engineering capacity characterization.

This harness measures runtime mechanics only.  It does not validate C2
detection accuracy and must not be used to make a production-capacity claim.
"""

from __future__ import annotations

import argparse
import asyncio
import gc
import hashlib
import json
import os
import platform
import statistics
import subprocess
import tempfile
import time
import tracemalloc
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Sequence

from evidencegate.domain.enums import ControlType, ResultType, ScientificStatus
from evidencegate.domain.governance import LaneGovernance
from evidencegate.ingest.replay import (
    NdjsonReplaySource,
    ReplayCanonicalizer,
    ReplayRunner,
)
from evidencegate.persistence.sqlite import SqliteWriter
from evidencegate.plugins.providers.c2 import C2R1Plugin
from evidencegate.plugins.providers.c2_config import C2R1Config
from evidencegate.routing.router import LaneTarget
from evidencegate.runtime.dispatcher import EventTimeReorderPolicy
from evidencegate.runtime.supervisor import RuntimeSupervisor


LANE = LaneTarget("c2.r1")
SCHEMA = Path(__file__).resolve().parents[1] / "evidencegate/persistence/schema.sql"
DEFAULT_OUTPUT = Path("benchmark_results/c2_capacity_characterization.json")
DEFAULT_REPORT = Path("C2_CAPACITY_CHARACTERIZATION_REPORT.md")
BASE_TIME = datetime(2026, 1, 1, tzinfo=timezone.utc)
MAX_SAFE_KEYS = 100_000
MAX_SAFE_RECORDS = 500_000
RECORDS_PER_TIMESTAMP = 256
CLAIM_CEILING = (
    "RECURRENT_COMMUNICATION_MEASUREMENT_ONLY; NOT_C2; NOT_MALWARE; NOT_COMPROMISE; NOT_BENIGN"
)


@dataclass(frozen=True, slots=True)
class C2CapacityExperimentConfig:
    workload: str
    active_key_count: int
    events_per_key: int
    same_timestamp_burst: int
    max_state_entries: int
    reorder_capacity: int
    reorder_total_capacity: int
    shard_count: int
    repetition: int = 1
    database_mode: str = "none"

    def __post_init__(self) -> None:
        if self.workload not in {
            "key_cardinality",
            "full_history",
            "same_time_burst",
            "mixed",
            "many_keys_same_time",
        }:
            raise ValueError(f"unknown workload: {self.workload}")
        for name in (
            "active_key_count",
            "events_per_key",
            "same_timestamp_burst",
            "max_state_entries",
            "reorder_capacity",
            "reorder_total_capacity",
            "shard_count",
            "repetition",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if self.database_mode not in {"none", "sqlite"}:
            raise ValueError("database_mode must be 'none' or 'sqlite'")
        if self.reorder_total_capacity < self.reorder_capacity:
            raise ValueError("reorder_total_capacity cannot be less than reorder_capacity")

    @property
    def expected_records(self) -> int:
        if self.workload == "same_time_burst":
            return self.same_timestamp_burst + 1
        if self.workload == "many_keys_same_time":
            return self.active_key_count * self.same_timestamp_burst + 1
        return self.active_key_count * self.events_per_key

    def validate_safety(self, allow_large: bool = False) -> None:
        if allow_large:
            return
        if self.active_key_count > MAX_SAFE_KEYS or self.expected_records > MAX_SAFE_RECORDS:
            raise ValueError(
                f"workload exceeds safety ceiling ({MAX_SAFE_KEYS} keys, "
                f"{MAX_SAFE_RECORDS} records); pass --allow-large explicitly"
            )


class TimingCanonicalizer(ReplayCanonicalizer):
    def __init__(self) -> None:
        super().__init__()
        self.latencies: list[float] = []

    def canonicalize(self, *args, **kwargs):
        started = time.perf_counter()
        try:
            return super().canonicalize(*args, **kwargs)
        finally:
            self.latencies.append(time.perf_counter() - started)


class TimingC2R1Plugin(C2R1Plugin):
    """The accepted C2-R1 implementation with read-only timing around process."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.processing_latencies: list[float] = []

    async def process(self, *args, **kwargs):
        started = time.perf_counter()
        try:
            return await super().process(*args, **kwargs)
        finally:
            self.processing_latencies.append(time.perf_counter() - started)


def _governance() -> LaneGovernance:
    return LaneGovernance(
        analytic_lane=str(LANE),
        scientific_status=ScientificStatus.EVIDENCE_CONSTRUCTION,
        scientific_phase="C2-R1 controlled runtime capacity characterization",
        scientific_blockers=(),
        claim_ceiling=CLAIM_CEILING,
        governance_version="c2-r1-0.1.0",
        effective_at=BASE_TIME,
        allowed_result_types=(
            ResultType.REVIEW_FINDING,
            ResultType.INSUFFICIENT_EVIDENCE,
            ResultType.PREREQUISITE_MISSING,
            ResultType.QUALITY_DEGRADED,
        ),
        ingest_permitted=True,
    )


def _manifest(record_count: int, source_id: str) -> dict[str, object]:
    return {
        "schema_version": "evidencegate-replay-manifest-v1",
        "source_id": source_id,
        "source_kind": "DERIVED",
        "input_observation_contract": "REPLAY_TYPED_V1",
        "timestamp_semantics": "FLOW_START",
        "direction_basis": "CLIENT_SERVER_ROLE",
        "wire_direction": "FORWARD",
        "visibility": {
            "available": ["FLOW_FACTS", "FORWARD_FACTS"],
            "unavailable": ["REVERSE_FACTS"],
            "degraded": [],
        },
        "quality": {
            "packet_loss": "UNKNOWN",
            "sampling": "UNKNOWN",
            "parser": "CLEAR",
            "capture_gap": "UNKNOWN",
        },
        "event_time_order": "NONDECREASING",
        "record_count": record_count,
    }


def _record(position: int, key_index: int, timestamp: datetime) -> dict[str, object]:
    stamp = timestamp.isoformat().replace("+00:00", "Z")
    return {
        "schema_version": "evidencegate-replay-record-v1",
        "position": position,
        "timestamp": stamp,
        "finality": "TERMINAL",
        "observation_type": "FLOW",
        "payload": {
            "flow_id_basis": "capacity-record",
            "endpoints": ["192.0.2.1", "198.51.100.8"],
            "protocol": 6,
            "start_time": stamp,
            "end_time": (timestamp + timedelta(milliseconds=1)).isoformat(),
            "export_time": (timestamp + timedelta(milliseconds=2)).isoformat(),
            "supplied_directional_counters": {"bytes_c2s": 100, "packets_c2s": 2},
            "exporter_semantics": "controlled-synthetic-engineering-load",
            "sampling": None,
            "documented_end_state": None,
        },
        "declared_observed_fields": [
            "flow_id_basis",
            "endpoints",
            "protocol",
            "start_time",
            "end_time",
            "export_time",
            "supplied_directional_counters",
            "exporter_semantics",
        ],
        "role_assignments": [
            {
                "identifier": f"client-{key_index:08d}",
                "role": "client_id",
                "basis": "SOURCE_DECLARED_ROLE",
            },
            {"identifier": "peer-capacity", "role": "peer_id", "basis": "SOURCE_DECLARED_ROLE"},
            {"identifier": "443", "role": "peer_port", "basis": "SOURCE_DECLARED_ROLE"},
        ],
        "canonicalization_options": {},
    }


def iter_workload_records(config: C2CapacityExperimentConfig) -> Iterable[dict[str, object]]:
    """Yield deterministic, nondecreasing records with all events inside the TTL."""
    position = 0
    if config.workload == "same_time_burst":
        for _ in range(config.same_timestamp_burst):
            position += 1
            yield _record(position, 0, BASE_TIME)
        yield _record(position + 1, 0, BASE_TIME + timedelta(seconds=1))
        return
    if config.workload == "many_keys_same_time":
        for key_index in range(config.active_key_count):
            for _ in range(config.same_timestamp_burst):
                position += 1
                yield _record(position, key_index, BASE_TIME)
        yield _record(position + 1, 0, BASE_TIME + timedelta(seconds=1))
        return

    burst = config.same_timestamp_burst if config.workload == "mixed" else 1
    rounds = (config.events_per_key + burst - 1) // burst
    keys_per_timestamp = max(1, RECORDS_PER_TIMESTAMP // burst)
    timestamp_index = 0
    emitted_per_key = [0] * config.active_key_count
    for _round in range(rounds):
        for first in range(0, config.active_key_count, keys_per_timestamp):
            timestamp = BASE_TIME + timedelta(milliseconds=timestamp_index)
            timestamp_index += 1
            for key_index in range(first, min(first + keys_per_timestamp, config.active_key_count)):
                remaining = config.events_per_key - emitted_per_key[key_index]
                for _ in range(min(burst, remaining)):
                    position += 1
                    emitted_per_key[key_index] += 1
                    yield _record(position, key_index, timestamp)


def write_bundle(bundle: Path, config: C2CapacityExperimentConfig) -> None:
    bundle.mkdir(parents=True, exist_ok=False)
    source_id = "c2-capacity-" + run_id(config)
    (bundle / "manifest.json").write_text(
        json.dumps(_manifest(config.expected_records, source_id), sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    with (bundle / "records.ndjson").open("w", encoding="utf-8", newline="\n") as stream:
        count = 0
        for record in iter_workload_records(config):
            stream.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
            count += 1
    if count != config.expected_records:
        raise AssertionError(f"generator produced {count}, expected {config.expected_records}")


def run_id(config: C2CapacityExperimentConfig) -> str:
    encoded = json.dumps(asdict(config), sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()[:12]


def _percentiles(samples: Sequence[float]) -> dict[str, float | None]:
    if len(samples) < 100:
        return {"sample_count": len(samples), "p50_ms": None, "p95_ms": None, "p99_ms": None}
    ordered = sorted(samples)

    def value(percent: int) -> float:
        index = round((len(ordered) - 1) * percent / 100)
        return round(ordered[index] * 1000, 6)

    return {
        "sample_count": len(samples),
        "p50_ms": value(50),
        "p95_ms": value(95),
        "p99_ms": value(99),
    }


def classify_status(counts: dict[str, int]) -> list[str]:
    status: list[str] = []
    if counts["reorder_saturation"]:
        status.append("SATURATED_REORDER")
    if counts.get("reorder_total_saturation", 0):
        status.append("SATURATED_REORDER_TOTAL")
    if counts["ingress_queue_saturation"] or counts["shard_queue_saturation"]:
        status.append("SATURATED_QUEUE")
    if counts["state_capacity_exceeded"]:
        status.append("STATE_CAPACITY_EXCEEDED")
    if counts["processing_errors"]:
        status.append("PROCESSING_ERROR")
    return status or ["CLEAN"]


async def run_experiment(
    config: C2CapacityExperimentConfig,
    *,
    allow_large: bool = False,
    working_directory: Path | None = None,
) -> dict[str, object]:
    config.validate_safety(allow_large)
    owned_temp = None
    if working_directory is None:
        owned_temp = tempfile.TemporaryDirectory(prefix="evidencegate-c2-capacity-")
        root = Path(owned_temp.name)
    else:
        root = working_directory
        root.mkdir(parents=True, exist_ok=True)
    bundle = root / "bundle"
    write_bundle(bundle, config)

    controls = []
    gaps = []
    result_counts: Counter[str] = Counter()
    persistence_latencies: list[float] = []
    end_to_end_latencies: list[float] = []
    ingest_submission_latencies: list[float] = []
    arrival_times: dict[str, float] = {}
    reorder_memory_at_peak = {
        "pending_observations": 0,
        "current_traced_bytes": 0,
        "peak_traced_bytes": 0,
    }
    sqlite_writer = None
    if config.database_mode == "sqlite":
        sqlite_writer = SqliteWriter(root / "results.sqlite3", SCHEMA)
        sqlite_writer.connect()

    async def control_sink(event) -> None:
        controls.append(event)

    async def gap_sink(gap) -> None:
        gaps.append(gap)

    async def result_writer(result, target) -> None:
        started = time.perf_counter()
        if sqlite_writer is not None:
            await sqlite_writer.write_result(result)
        completed = time.perf_counter()
        persistence_latencies.append(completed - started)
        result_counts[result.result_type.value] += 1
        trigger = result.evidence_items[-1] if result.evidence_items else None
        if trigger in arrival_times:
            end_to_end_latencies.append(completed - arrival_times.pop(trigger))

    scientific_config = C2R1Config.reference_engine_v1()
    plugin = TimingC2R1Plugin(scientific_config, max_state_entries=config.max_state_entries)
    canonicalizer = TimingCanonicalizer()
    supervisor = RuntimeSupervisor(
        {LANE: plugin},
        {LANE: _governance()},
        result_writer,
        shard_count=config.shard_count,
        control_sink=control_sink,
        gap_sink=gap_sink,
        reorder_policies={
            LANE: EventTimeReorderPolicy(config.reorder_capacity, config.reorder_total_capacity)
        },
    )
    original_ingest = supervisor.ingest_observation

    async def timed_ingest(observation):
        arrival_times[observation.observation_id] = time.perf_counter()
        started = time.perf_counter()
        try:
            plan = await original_ingest(observation)
            if config.workload == "many_keys_same_time":
                # Deterministically observe the real dispatcher buffer before
                # the later source timestamp advances the replay watermark.
                await supervisor.dispatchers[LANE].queue.join()
                pending = supervisor.dispatchers[LANE].pending_reorder_count
                if pending > reorder_memory_at_peak["pending_observations"]:
                    current, peak = tracemalloc.get_traced_memory()
                    reorder_memory_at_peak.update(
                        {
                            "pending_observations": pending,
                            "current_traced_bytes": current,
                            "peak_traced_bytes": peak,
                        }
                    )
            return plan
        finally:
            ingest_submission_latencies.append(time.perf_counter() - started)

    supervisor.ingest_observation = timed_ingest  # type: ignore[method-assign]
    # One supervisor is created per run; make the high-water reset boundary explicit.
    supervisor.dispatchers[LANE].reset_reorder_peaks()
    source = NdjsonReplaySource(bundle)
    runner = ReplayRunner(
        source,
        supervisor,
        speed=0,
        control_sink=control_sink,
        canonicalizer=canonicalizer,
    )

    tracemalloc.start()
    baseline_current, _ = tracemalloc.get_traced_memory()
    wall_started = time.perf_counter()
    summary = await runner.run()
    elapsed = time.perf_counter() - wall_started

    dispatcher = supervisor.dispatchers[LANE]
    state_entries = len(supervisor.state_stores[LANE])
    sqlite_count = 0
    if sqlite_writer is not None:
        sqlite_count = sqlite_writer._conn.execute("SELECT COUNT(*) FROM results").fetchone()[0]  # type: ignore[union-attr]
        sqlite_writer.close()
    gap_types = Counter(kind for gap in gaps for kind in gap.gap_types)
    ingress_queue = sum("ingress queue full" in gap.reason.lower() for gap in gaps)
    shard_queue = sum("shard queue full" in gap.reason.lower() for gap in gaps)
    error_events = [event for event in controls if event.control_type is ControlType.ERROR]
    state_errors = sum(
        event.typed_payload.get("exception_type") == "StateCapacityExceeded"
        for event in error_events
    )
    processing_errors = len(error_events) - state_errors
    counts = {
        "ingress_queue_saturation": ingress_queue,
        "shard_queue_saturation": shard_queue,
        "reorder_saturation": gap_types["REORDER_BUFFER_SATURATION"],
        "reorder_total_saturation": gap_types["REORDER_BUFFER_TOTAL_SATURATION"],
        "state_capacity_exceeded": state_errors,
        "processing_errors": processing_errors,
        "late_events": sum(
            event.control_type is ControlType.LATE_EVENT_OBSERVED for event in controls
        ),
        "watermarks_advanced": sum(
            event.control_type is ControlType.WATERMARK_ADVANCED for event in controls
        ),
        "quality_gaps": len(gaps),
    }
    latency = {
        "canonicalization": _percentiles(canonicalizer.latencies),
        "runtime_ingest_submission": _percentiles(ingest_submission_latencies),
        "plugin_processing": _percentiles(plugin.processing_latencies),
        "result_persistence": _percentiles(persistence_latencies),
        "end_to_end_from_runtime_submission": _percentiles(end_to_end_latencies),
    }
    # Keep the live StateStore, but release measurement-owned samples/events so
    # current/delta characterizes retained runtime state rather than the harness.
    canonicalizer.latencies.clear()
    plugin.processing_latencies.clear()
    ingest_submission_latencies.clear()
    persistence_latencies.clear()
    end_to_end_latencies.clear()
    arrival_times.clear()
    controls.clear()
    gaps.clear()
    error_events.clear()
    gc.collect()
    current_traced, peak_traced = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    if owned_temp is not None:
        owned_temp.cleanup()

    results_total = sum(result_counts.values())
    delta = current_traced - baseline_current
    expected_live = min(config.active_key_count, config.max_state_entries)
    if config.workload == "same_time_burst":
        expected_live = 1
    elif config.workload == "many_keys_same_time":
        accepted = min(
            config.active_key_count * config.same_timestamp_burst,
            config.reorder_total_capacity,
        )
        expected_live = min(
            config.active_key_count,
            (accepted + config.same_timestamp_burst - 1) // config.same_timestamp_burst,
        )
    return {
        "run_id": run_id(config),
        "config": asdict(config),
        "synthetic_workload_status": "CONTROLLED SYNTHETIC ENGINEERING LOAD",
        "status": classify_status(counts),
        "records_read": summary.records_read,
        "observations": summary.observations_emitted,
        "results": results_total,
        "result_types": dict(sorted(result_counts.items())),
        "sqlite_results": sqlite_count,
        "elapsed_seconds": round(elapsed, 6),
        "offered_records_per_second": round(summary.records_read / elapsed, 3),
        "offered_observations_per_second": round(summary.observations_emitted / elapsed, 3),
        "successfully_processed_observations_per_second": round(results_total / elapsed, 3),
        "results_per_second": round(results_total / elapsed, 3),
        "peak_state_entries": state_entries,
        "expected_live_state_entries": expected_live,
        "state_cardinality_matches_expected": state_entries == expected_live,
        "peak_reorder_total": dispatcher.peak_pending_reorder_total,
        "peak_reorder_per_key": dispatcher.peak_pending_reorder_per_key,
        "pending_reorder_at_end": dispatcher.pending_reorder_count,
        "accepted_at_peak_reorder": dispatcher.peak_pending_reorder_total,
        "rejected_total_observations": counts["reorder_total_saturation"],
        "counts": counts,
        "memory": {
            "tracemalloc_baseline_bytes": baseline_current,
            "tracemalloc_current_bytes": current_traced,
            "tracemalloc_peak_bytes": peak_traced,
            "tracemalloc_delta_bytes": delta,
            "approx_delta_bytes_per_live_key": (
                round(delta / state_entries, 3) if state_entries else None
            ),
            "scope": (
                "Live Python allocations after releasing benchmark timing/control "
                "buffers; includes runtime overhead and is not process RSS"
            ),
            "reorder_at_peak": {
                **reorder_memory_at_peak,
                "approx_bytes_per_pending_observation": (
                    round(
                        (reorder_memory_at_peak["current_traced_bytes"] - baseline_current)
                        / reorder_memory_at_peak["pending_observations"],
                        3,
                    )
                    if reorder_memory_at_peak["pending_observations"]
                    else None
                ),
                "scope": (
                    "Python traced allocation at observed pending-reorder peak; "
                    "includes runtime and benchmark instrumentation; not RSS"
                ),
            },
        },
        "latency": latency,
    }


def environment() -> dict[str, object]:
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        commit = "unavailable"
    available_memory = None
    if hasattr(os, "sysconf"):
        try:
            available_memory = os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
        except (ValueError, OSError):
            pass
    return {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "os": platform.platform(),
        "python": platform.python_version(),
        "cpu_model": platform.processor() or "unavailable",
        "logical_cpu_count": os.cpu_count(),
        "available_memory_bytes": available_memory
        if available_memory is not None
        else "unavailable",
        "git_commit": commit,
    }


def preset_configs(repetitions: int, shards: int) -> list[C2CapacityExperimentConfig]:
    configs: list[C2CapacityExperimentConfig] = []
    for repetition in range(1, repetitions + 1):
        for keys in (32, 64, 128, 256, 512, 1024, 2048):
            configs.append(
                C2CapacityExperimentConfig(
                    "key_cardinality",
                    keys,
                    3,
                    1,
                    keys + 1,
                    64,
                    8192,
                    shards,
                    repetition,
                )
            )
        for keys in (32, 128, 512, 1024):
            configs.append(
                C2CapacityExperimentConfig(
                    "full_history",
                    keys,
                    32,
                    1,
                    keys + 1,
                    64,
                    8192,
                    shards,
                    repetition,
                )
            )
        for bound in (1, 2, 4, 8, 16, 32, 64):
            for burst in (1, 2, 4, 8, 16, 32, 64):
                configs.append(
                    C2CapacityExperimentConfig(
                        "same_time_burst",
                        1,
                        burst + 1,
                        burst,
                        8,
                        bound,
                        8192,
                        shards,
                        repetition,
                    )
                )
        configs.append(
            C2CapacityExperimentConfig(
                "mixed",
                256,
                8,
                4,
                512,
                16,
                8192,
                shards,
                repetition,
                "sqlite",
            )
        )
    # Explicit boundary evidence: below, equal, and max+1 attempted.
    configs.extend(
        [
            C2CapacityExperimentConfig("key_cardinality", 31, 3, 1, 32, 64, 8192, shards),
            C2CapacityExperimentConfig("key_cardinality", 32, 3, 1, 32, 64, 8192, shards),
            C2CapacityExperimentConfig("key_cardinality", 33, 3, 1, 32, 64, 8192, shards),
            C2CapacityExperimentConfig("key_cardinality", 2047, 3, 1, 2048, 64, 8192, shards),
            C2CapacityExperimentConfig("key_cardinality", 2048, 3, 1, 2048, 64, 8192, shards),
            C2CapacityExperimentConfig("key_cardinality", 2049, 3, 1, 2048, 64, 8192, shards),
        ]
    )
    return configs


def global_reorder_preset_configs(
    repetitions: int, shards: int
) -> list[C2CapacityExperimentConfig]:
    """Controlled many-key matrix for the independent lane-wide budget."""
    points = (
        # Exact clean occupancy points used for memory characterization.
        (64, 4, 256),
        (128, 4, 512),
        (128, 8, 1024),
        (256, 8, 2048),
        # T+1 proof and sustained excess proof at the smallest tested budget.
        (257, 1, 256),
        (64, 8, 256),
    )
    return [
        C2CapacityExperimentConfig(
            "many_keys_same_time",
            keys,
            burst,
            burst,
            1024,
            16,
            total,
            shards,
            repetition,
        )
        for repetition in range(1, repetitions + 1)
        for keys, burst, total in points
    ]


def _median_runs(runs: Sequence[dict[str, object]]) -> list[dict[str, object]]:
    groups: dict[str, list[dict[str, object]]] = {}
    for run in runs:
        config = dict(run["config"])  # type: ignore[arg-type]
        config.pop("repetition", None)
        key = json.dumps(config, sort_keys=True)
        groups.setdefault(key, []).append(run)
    output = []
    for key, values in sorted(groups.items()):
        rates = [float(item["successfully_processed_observations_per_second"]) for item in values]
        memory = [int(item["memory"]["tracemalloc_delta_bytes"]) for item in values]  # type: ignore[index]
        output.append(
            {
                "config": json.loads(key),
                "run_ids": [item["run_id"] for item in values],
                "repetitions": len(values),
                "median_processed_observations_per_second": statistics.median(rates),
                "min_processed_observations_per_second": min(rates),
                "max_processed_observations_per_second": max(rates),
                "median_tracemalloc_delta_bytes": statistics.median(memory),
            }
        )
    return output


def _markdown_table(runs: Sequence[dict[str, object]]) -> str:
    columns = (
        "workload",
        "keys",
        "events/key",
        "burst",
        "state bound",
        "reorder bound",
        "state",
        "reorder total",
        "reorder/key",
        "obs",
        "results",
        "seconds",
        "processed obs/s",
        "peak traced B",
        "gaps",
        "errors",
        "status",
    )
    lines = ["| " + " | ".join(columns) + " |", "|" + "---|" * len(columns)]
    for run in runs:
        cfg, counts, memory = run["config"], run["counts"], run["memory"]
        row = (
            cfg["workload"],
            cfg["active_key_count"],
            cfg["events_per_key"],
            cfg["same_timestamp_burst"],
            cfg["max_state_entries"],
            cfg["reorder_capacity"],
            run["peak_state_entries"],
            run["peak_reorder_total"],
            run["peak_reorder_per_key"],
            run["observations"],
            run["results"],
            run["elapsed_seconds"],
            run["successfully_processed_observations_per_second"],
            memory["tracemalloc_peak_bytes"],
            counts["quality_gaps"],
            counts["state_capacity_exceeded"] + counts["processing_errors"],
            ", ".join(run["status"]),
        )
        lines.append("| " + " | ".join(map(str, row)) + " |")
    return "\n".join(lines)


def render_report(payload: dict[str, object]) -> str:
    runs = payload["runs"]
    clean_state = [
        r
        for r in runs
        if r["config"]["workload"] in {"key_cardinality", "full_history", "mixed"}
        and r["status"] == ["CLEAN"]
    ]
    clean_reorder = [
        r for r in runs if r["config"]["workload"] == "same_time_burst" and r["status"] == ["CLEAN"]
    ]
    state_values = sorted({r["config"]["max_state_entries"] for r in clean_state})
    state_boundary_values = sorted(
        {
            r["config"]["max_state_entries"]
            for r in clean_state
            if r["config"]["workload"] == "key_cardinality"
            and r["config"]["active_key_count"] == r["config"]["max_state_entries"]
        }
    )
    reorder_values = sorted({r["config"]["reorder_capacity"] for r in clean_reorder})
    reorder_map = {
        burst: min(
            r["config"]["reorder_capacity"]
            for r in clean_reorder
            if r["config"]["same_timestamp_burst"] == burst
        )
        for burst in sorted({r["config"]["same_timestamp_burst"] for r in clean_reorder})
    }
    total_counts = {
        name: sum(r["counts"].get(name, 0) for r in runs)
        for name in (
            "ingress_queue_saturation",
            "shard_queue_saturation",
            "reorder_saturation",
            "state_capacity_exceeded",
            "processing_errors",
            "late_events",
        )
    }
    sqlite_runs = [r for r in runs if r["config"].get("database_mode") == "sqlite"]
    minimal_runs = [r for r in clean_state if r["config"]["workload"] == "key_cardinality"]
    history_runs = [r for r in clean_state if r["config"]["workload"] == "full_history"]
    max_minimal = max(minimal_runs, key=lambda r: r["peak_state_entries"], default=None)
    max_history = max(history_runs, key=lambda r: r["peak_state_entries"], default=None)
    supporting = [
        r["run_id"]
        for r in runs
        if (
            r["config"]["workload"] == "key_cardinality"
            and r["config"]["max_state_entries"] in state_boundary_values
            and r["config"]["active_key_count"]
            in {
                r["config"]["max_state_entries"],
                r["config"]["max_state_entries"] + 1,
            }
        )
        or (
            r["config"]["workload"] == "same_time_burst"
            and r["config"]["same_timestamp_burst"] == 64
            and r["config"]["reorder_capacity"] in {32, 64}
            and r["config"].get("repetition") == 1
        )
    ]
    env = payload["environment"]
    scientific = payload["scientific_config"]
    state_range = (
        f"{min(state_boundary_values)}-{max(state_boundary_values)} among exact tested acceptance boundaries; see exact rows"
        if state_boundary_values
        else "No clean candidate measured"
    )
    return f"""# [EXPERIMENT]\n# CONTROLLED MVP ENGINEERING CAPACITY CHARACTERIZATION\n\nThis is **C2-R1 CAPACITY CHARACTERIZATION** using controlled synthetic engineering load. It is not a production benchmark, scientific C2 validation, FPR test, malware-truth test, or EvidenceGate production-throughput claim.\n\n## Scope and environment\n\n- Captured: {env["captured_at"]}\n- OS: {env["os"]}\n- Python: {env["python"]}\n- CPU: {env["cpu_model"]} ({env["logical_cpu_count"]} logical CPUs)\n- Available memory: {env["available_memory_bytes"]}\n- Git commit at measurement start: `{env["git_commit"]}`\n- Scientific config: minimum history `{scientific["minimum_history_events"]}`, retained history `{scientific["max_retained_events_per_pair"]}`, TTL `{scientific["state_ttl_seconds"]}` seconds, basis `{scientific["event_basis"]}`\n- Persistence: explicitly stated per run; SQLite runs use the real disk-backed schema v3 writer and persist every warm-up and ready result.\n\nThe ingress queue capacity is 2000, shard mailbox capacity is 1000, state-key capacity is the per-run `max_state_entries`, and per-key reorder capacity is the per-run `reorder_capacity`. These are four independent bounds. Scientific retained history (32) is independent of reorder capacity and does not imply a reorder limit of 32.\n\n## Runs\n\n{_markdown_table(runs)}\n\nOffered rate is records/observations submitted per wall second. Successfully processed rate is finalized results per wall second; every successfully processed C2-R1 observation produces one warm-up or ready result. A rate is clean only when ingress, shard, reorder, state-capacity, and processing error counts are all zero. `tracemalloc` reports Python allocations, not full-process RSS. Percentiles are emitted only with at least 100 samples.\n\n## Observed boundaries and timing\n\n- Aggregate ingress queue saturation: {total_counts["ingress_queue_saturation"]}; shard queue saturation: {total_counts["shard_queue_saturation"]}.\n- Intentional reorder saturation gaps: {total_counts["reorder_saturation"]}; intentional state-capacity errors: {total_counts["state_capacity_exceeded"]}.\n- Unexpected processing errors: {total_counts["processing_errors"]}; late events: {total_counts["late_events"]}.\n- Largest clean minimal-state point: {max_minimal["peak_state_entries"] if max_minimal else "none"} live keys at {max_minimal["successfully_processed_observations_per_second"] if max_minimal else "n/a"} processed observations/s.\n- Largest clean full-history point: {max_history["peak_state_entries"] if max_history else "none"} live keys at {max_history["successfully_processed_observations_per_second"] if max_history else "n/a"} processed observations/s.\n- Smallest clean reorder bound by controlled burst: {reorder_map}.\n- SQLite runs: {len(sqlite_runs)}; all have equal finalized and persisted result counts: {all(r["results"] == r["sqlite_results"] for r in sqlite_runs)}. Canonicalization, ingest-submission, plugin, persistence, and end-to-end p50/p95/p99 values are preserved in the JSON artifact.\n\n## Candidate discussion\n\nClean tested state capacities span {min(state_values) if state_values else "none"} through {max(state_values) if state_values else "none"} entries at the exact tabled workloads. Clean tested reorder capacities: {reorder_values or "none"}. Higher retained history increases memory per key; SQLite persistence reduces the observed vertical-slice rate relative to no-persistence runs. These measurements apply only to the exact environment and workloads above. No automatic headroom multiplier is selected.\n\nThe smallest tested clean state/reorder values for a workload can be read from the exact rows and machine-readable artifact. These are a **CANDIDATE RANGE FOR HUMAN GATE**, not final configuration. The default registry remains `LaneTarget(\"c2\") -> C2ShellPlugin`; C2-R1 has not been activated.\n\nHUMAN GATE REQUIRED\n\nSTATE CAPACITY CANDIDATES:\n{state_range}\n\nREORDER CAPACITY CANDIDATES:\n{reorder_map or "No clean candidate measured"}\n\nSUPPORTING RUN IDS:\n{supporting or "None"}\n\nKNOWN LIMITATIONS:\n- Single development host and synthetic typed-NDJSON replay only.\n- `tracemalloc` excludes native allocations and is not RSS.\n- C2-R1 vertical slice only; no DGA model, other threat paths, PCAP adapter, API, dashboard, or alert path.\n- Rates are machine- and workload-specific and are not production capacity.\n\nNO VALUE HAS BEEN ACTIVATED YET.\n"""


def render_global_reorder_report(payload: dict[str, object]) -> str:
    runs = payload["runs"]
    env = payload["environment"]
    rows = [
        "| run | keys | events/key | per-key | total | offered | accepted peak | rejected total | peak total | peak/key | seconds | current traced at peak | peak traced | bytes/pending | status |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for run in runs:
        cfg = run["config"]
        memory = run["memory"]["reorder_at_peak"]
        rows.append(
            "| "
            + " | ".join(
                map(
                    str,
                    (
                        run["run_id"],
                        cfg["active_key_count"],
                        cfg["same_timestamp_burst"],
                        cfg["reorder_capacity"],
                        cfg["reorder_total_capacity"],
                        run["observations"],
                        run["accepted_at_peak_reorder"],
                        run["rejected_total_observations"],
                        run["peak_reorder_total"],
                        run["peak_reorder_per_key"],
                        run["elapsed_seconds"],
                        memory["current_traced_bytes"],
                        memory["peak_traced_bytes"],
                        memory["approx_bytes_per_pending_observation"],
                        ", ".join(run["status"]),
                    ),
                )
            )
            + " |"
        )
    clean_bounds = sorted(
        {
            run["config"]["reorder_total_capacity"]
            for run in runs
            if run["status"] == ["CLEAN"]
            and run["peak_reorder_total"] == run["config"]["reorder_total_capacity"]
        }
    )
    supporting = [run["run_id"] for run in runs if run["config"].get("repetition") == 1]
    return "\n".join(
        (
            "# [EXPERIMENT]",
            "# CONTROLLED MVP GLOBAL REORDER CAPACITY CHARACTERIZATION",
            "",
            "This addendum uses controlled synthetic engineering load through the real typed-NDJSON replay, C2-R1 plugin, event-time reorder, StateStore, shards, and real result finalization. It makes no production-capacity or C2-detection claim.",
            "",
            "## Root cause and policy contract",
            "",
            "A per-key bound alone cannot bound the sum of buffers when many distinct keys share an unclosed event-time boundary. `EventTimeReorderPolicy` now requires independent positive non-boolean `max_buffered_events_per_key` and `max_buffered_events_total` values, with total greater than or equal to per-key. The dispatcher checks per-key first, then total, before insertion.",
            "",
            "Existing buffered facts are never evicted. A fact rejected by the lane-wide budget produces one `REORDER_BUFFER_TOTAL_SATURATION` QualityGap and invokes the plugin's existing GapAction. Per-key overflow remains `REORDER_BUFFER_SATURATION`. Watermark ordering and release semantics are unchanged.",
            "",
            "State capacity, per-key reorder capacity, lane-total reorder capacity, and C2 scientific retained history (32 events) remain four separate concepts. None is derived from another.",
            "",
            "## Many-key same-time workload and total sweep",
            "",
            *rows,
            "",
            "The workload assigns explicit trusted `SOURCE_DECLARED_ROLE` client, peer, and service identities. All K x B observations share one event time; a later source timestamp advances the real replay watermark. Offered observations include that later boundary record. Accepted peak counts refer to simultaneously buffered same-time observations; rejected-total counts are one visible gap per incoming excess fact.",
            "",
            "## Memory and throughput interpretation",
            "",
            "The table records Python traced current and peak allocation at the observed pending-buffer maximum plus an approximate incremental bytes/pending observation value. `tracemalloc` is not process RSS and the point-in-time value includes runtime and benchmark instrumentation. Saturated offered rates are not sustainable-throughput claims.",
            "",
            "## Environment",
            "",
            f"- Captured: {env['captured_at']}",
            f"- OS: {env['os']}",
            f"- Python: {env['python']}",
            f"- CPU: {env['cpu_model']} ({env['logical_cpu_count']} logical CPUs)",
            f"- Available memory: {env['available_memory_bytes']}",
            f"- Starting git commit: `{env['git_commit']}`",
            "",
            "## Limitations",
            "",
            "- Single development host and controlled synthetic typed replay.",
            "- Point-in-time `tracemalloc` allocation is not RSS.",
            "- C2-R1 vertical slice only; no DGA, other threats, API, dashboard, or raw-PCAP path.",
            "- Tested values are engineering candidates, not activated defaults or production claims.",
            "",
            "HUMAN GATE REQUIRED",
            "",
            "PROVISIONAL STATE CAPACITY:",
            "1024",
            "NOT YET ACTIVE",
            "",
            "PROVISIONAL PER-KEY REORDER CAPACITY:",
            "16",
            "NOT YET ACTIVE",
            "",
            "TOTAL REORDER CAPACITY CANDIDATES:",
            f"{min(clean_bounds)}-{max(clean_bounds)} among exact clean tested bounds"
            if clean_bounds
            else "No clean candidate measured",
            "",
            "SUPPORTING RUN IDS:",
            str(supporting),
            "",
            "KNOWN LIMITATIONS:",
            "- Single-host controlled synthetic replay; tracemalloc is not RSS.",
            "- Candidate values require Control Room review and are not production capacity.",
            "",
            "NO C2 CAPACITY VALUE HAS BEEN ACTIVATED.",
            "",
        )
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--preset", action="store_true", help="run the conservative characterization sweep"
    )
    parser.add_argument(
        "--global-reorder-preset",
        action="store_true",
        help="run the many-key lane-total reorder characterization",
    )
    parser.add_argument(
        "--workload",
        choices=(
            "key_cardinality",
            "full_history",
            "same_time_burst",
            "mixed",
            "many_keys_same_time",
        ),
        default="key_cardinality",
    )
    parser.add_argument("--keys", type=int, nargs="+", default=[32])
    parser.add_argument("--events-per-key", type=int, default=3)
    parser.add_argument("--same-time-burst", type=int, default=1)
    parser.add_argument("--max-state-entries", type=int, default=64)
    parser.add_argument("--reorder-capacity", type=int, default=64)
    parser.add_argument("--reorder-total-capacity", type=int, default=8192)
    parser.add_argument("--shards", type=int, default=4)
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--database-mode", choices=("none", "sqlite"), default="none")
    parser.add_argument(
        "--database-path", type=Path, help="reserved output directory for a single SQLite run"
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--allow-large", action="store_true")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="reuse matching run IDs already present in --output",
    )
    return parser


async def async_main(args: argparse.Namespace) -> dict[str, object]:
    if args.global_reorder_preset:
        configs = global_reorder_preset_configs(args.repetitions, args.shards)
    elif args.preset:
        configs = preset_configs(args.repetitions, args.shards)
    else:
        configs = [
            C2CapacityExperimentConfig(
                args.workload,
                keys,
                args.events_per_key,
                args.same_time_burst,
                args.max_state_entries,
                args.reorder_capacity,
                args.reorder_total_capacity,
                args.shards,
                repetition,
                args.database_mode,
            )
            for repetition in range(1, args.repetitions + 1)
            for keys in args.keys
        ]
    runs = []
    if args.resume and args.output.is_file():
        existing = json.loads(args.output.read_text(encoding="utf-8"))
        runs.extend(existing.get("runs", []))
    known_ids = {run["run_id"] for run in runs}
    pending = [config for config in configs if run_id(config) not in known_ids]
    for index, config in enumerate(pending, 1):
        print(f"[{index}/{len(pending)}] {config.workload} {asdict(config)}", flush=True)
        run_dir = None
        if args.database_path is not None and len(pending) == 1:
            run_dir = args.database_path
        runs.append(
            await run_experiment(config, allow_large=args.allow_large, working_directory=run_dir)
        )
    reference = C2R1Config.reference_engine_v1()
    payload = {
        "status": (
            "[EXPERIMENT] CONTROLLED MVP GLOBAL REORDER CAPACITY CHARACTERIZATION"
            if args.global_reorder_preset
            else "[EXPERIMENT] CONTROLLED MVP ENGINEERING CAPACITY CHARACTERIZATION"
        ),
        "production_claim": "NONE",
        "environment": environment(),
        "scientific_config": {
            "config_id": reference.config_id,
            "minimum_history_events": reference.minimum_history_events,
            "max_retained_events_per_pair": reference.max_retained_events_per_pair,
            "state_ttl_seconds": reference.state_ttl.total_seconds(),
            "event_basis": reference.event_basis.value,
            "config_hash": reference.canonical_hash,
        },
        "queue_capacities": {"ingress": 2000, "shard": 1000},
        "runs": runs,
        "aggregate_repetitions": _median_runs(runs),
        "default_c2_activation": "STILL GATED",
    }
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = asyncio.run(async_main(args))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    report = (
        render_global_reorder_report(payload)
        if args.global_reorder_preset
        else render_report(payload)
    )
    args.report.write_text(report, encoding="utf-8")
    print(f"wrote {args.output} and {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
