#!/usr/bin/env python3
"""Sustained offered-rate characterization for the exact controlled MVP stack.

This is infrastructure/load evidence on one development host. It is not a
production-capacity, SLA, attack-rate, or network-line-rate measurement.
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import importlib.metadata
import json
import os
import platform
import statistics
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

import psutil

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evidencegate.domain.enums import ControlType
from evidencegate.domain.events import NetworkObservation, ObservationIdentity, RoleAssignment
from evidencegate.domain.payloads import FlowObservation, TLSObservation
from evidencegate.ingest.replay import NdjsonReplaySource, ReplayCanonicalizer
from evidencegate.persistence.sqlite import SqliteWriter
from evidencegate.plugins.providers.dga_m1 import ARTIFACT_SHA256, DgaM1Plugin, DgaM1Readiness
from evidencegate.plugins.providers.registry import (
    MvpRuntimeRegistration,
    build_mvp_runtime_registration,
)
from evidencegate.runtime.supervisor import RuntimeSupervisor


CLASSIFICATION = "CONTROLLED SIH DEMO SUSTAINED OPERATING-RATE CHARACTERIZATION"
WATERMARK = "DEVELOPMENT MACHINE / CONTROLLED MVP / NOT PRODUCTION CAPACITY"
MODEL_PATH = ROOT / "artifacts" / "dga" / "local" / "DGA_M1_R1_SERIALIZED_MODEL.joblib"
DEFAULT_RATES = (25, 50, 75, 100, 150, 200, 300, 400, 500)
MIX_COUNTS = {"PACKET": 3, "FLOW": 4, "DNS": 1, "TLS": 1}
ELIGIBLE_FAMILIES = (
    "DDoS",
    "C2",
    "DGA M1-R1",
    "DNS-T1",
    "ENC-A",
    "Recon",
    "Exfil-M1",
)


def percentiles_seconds(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"p50_ms": None, "p95_ms": None, "p99_ms": None}
    ordered = sorted(values)

    def nearest(fraction: float) -> float:
        index = round((len(ordered) - 1) * fraction)
        return round(ordered[index] * 1000, 6)

    return {
        "p50_ms": nearest(0.50),
        "p95_ms": nearest(0.95),
        "p99_ms": nearest(0.99),
    }


async def load_workload_templates(root: Path = ROOT) -> tuple[NetworkObservation, ...]:
    """Canonicalize the real nine-record mixed fixture once for deterministic reuse."""
    source = NdjsonReplaySource(root / "tests" / "fixtures" / "replay" / "final_mvp_mixed")
    manifest = await source.open()
    canonicalizer = ReplayCanonicalizer()
    observations: list[NetworkObservation] = []
    records = source.records()
    try:
        async for record in records:
            result = canonicalizer.canonicalize(
                record,
                manifest,
                f"quality:sustained-template:{record.position}",
                record.timestamp,
            )
            observations.extend(result.observations)
    finally:
        await records.aclose()
        await source.close()
    return tuple(observations)


def repeated_observation(
    templates: tuple[NetworkObservation, ...],
    index: int,
    run_id: str,
) -> NetworkObservation:
    """Create one causally valid fact in a bounded, explicit benchmark episode.

    Every nine observations form an independent episode. Event-time retains the
    fixture's within-episode offsets and advances seven minutes between episodes,
    exercising recurrence, windows, expiry, and reorder handling without an
    identical-time flood. Identities are unique per episode; the runtime can
    therefore expire old scientific state instead of accumulating one misleading
    population history.
    """
    template_index = index % len(templates)
    episode = index // len(templates)
    template = templates[template_index]
    first = templates[0].event_time
    event_time = first + timedelta(minutes=7 * episode) + (template.event_time - first)
    delta = event_time - template.event_time
    episode_tag = f"{run_id}:episode:{episode:08d}"
    roles = tuple(
        RoleAssignment(
            identifier=f"{item.identifier}:{episode_tag}",
            role=item.role,
            basis=item.basis,
        )
        for item in template.identity.role_assignments
    )
    identity = ObservationIdentity(
        observed_identifiers=tuple(
            f"{value}:{episode_tag}" for value in template.identity.observed_identifiers
        ),
        identifier_basis=template.identity.identifier_basis,
        role_assignments=roles,
    )
    payload = template.typed_payload
    if isinstance(payload, FlowObservation):
        payload = dataclasses.replace(
            payload,
            start_time=payload.start_time + delta,
            end_time=payload.end_time + delta,
            export_time=payload.export_time + delta,
        )
    elif isinstance(payload, TLSObservation) and payload.prefix_time is not None:
        payload = dataclasses.replace(payload, prefix_time=payload.prefix_time + delta)
    return dataclasses.replace(
        template,
        observation_id=f"sustained:{run_id}:{index:09d}",
        event_time=event_time,
        causal_available_time=event_time,
        ingest_time=event_time,
        source_id=f"sustained:{run_id}:{episode:08d}",
        source_position=str(index + 1),
        provenance_ref=f"benchmark:{run_id}:{index:09d}",
        quality_ref=f"quality:benchmark:{run_id}:{index:09d}",
        identity=identity,
        typed_payload=payload,
    )


def queue_snapshot(supervisor: RuntimeSupervisor) -> dict[str, int]:
    dispatch = sum(item.queue.qsize() for item in supervisor.dispatchers.values())
    shard = sum(shard.queue.qsize() for shards in supervisor.shards.values() for shard in shards)
    reorder = sum(item.pending_reorder_count for item in supervisor.dispatchers.values())
    return {
        "dispatcher": dispatch,
        "shard": shard,
        "reorder": reorder,
        "total": dispatch + shard + reorder,
    }


def backlog_assessment(samples: list[dict[str, float | int]], final_total: int) -> dict[str, Any]:
    values = [int(item["total"]) for item in samples]
    peak = max(values, default=0)
    if not values:
        return {
            "peak": peak,
            "final": final_total,
            "trend_slope_items_per_second": 0.0,
            "stable": final_total == 0,
        }
    times = [float(item["elapsed_seconds"]) for item in samples]
    mean_time = statistics.fmean(times)
    mean_value = statistics.fmean(values)
    denominator = sum((value - mean_time) ** 2 for value in times)
    slope = (
        0.0
        if denominator == 0
        else sum((at - mean_time) * (value - mean_value) for at, value in zip(times, values))
        / denominator
    )
    width = max(1, len(values) // 4)
    first_mean = statistics.fmean(values[:width])
    last_mean = statistics.fmean(values[-width:])
    # A sustained positive least-squares trend above two queued items/second is
    # treated as growth. This is a runtime characterization guard, not threat
    # science or an SLA. Final occupancy must independently be zero.
    stable = final_total == 0 and slope <= 2.0
    return {
        "peak": peak,
        "final": final_total,
        "first_quarter_mean": round(first_mean, 3),
        "last_quarter_mean": round(last_mean, 3),
        "trend_slope_items_per_second": round(slope, 3),
        "stable": stable,
    }


def latency_stability(values: list[float]) -> dict[str, Any]:
    """Compare early and late tails; this detects divergence, not a fixed SLA."""
    if len(values) < 8:
        return {"early_p95_ms": None, "late_p95_ms": None, "stable": True}
    width = max(1, len(values) // 4)
    early = percentiles_seconds(values[:width])["p95_ms"]
    late = percentiles_seconds(values[-width:])["p95_ms"]
    assert early is not None and late is not None
    # A 250 ms sampling/jitter allowance plus a twofold tail guard is an
    # infrastructure trend check, not a mechanism threshold or latency SLA.
    return {
        "early_p95_ms": early,
        "late_p95_ms": late,
        "stable": late <= early * 2 + 250.0,
    }


async def run_rate_point(
    registration: MvpRuntimeRegistration,
    templates: tuple[NetworkObservation, ...],
    *,
    rate: int,
    duration_seconds: float,
    replicate: int,
    root: Path = ROOT,
    keep_database: bool = False,
    probe_alerts: bool = False,
) -> dict[str, Any]:
    """Offer observations at a clocked rate, then drain and measure exact work."""
    run_id = f"r{rate}-rep{replicate}"
    results_dir = root / "benchmark_results"
    results_dir.mkdir(parents=True, exist_ok=True)
    fd, database_name = tempfile.mkstemp(
        prefix=f"sustained-{run_id}-", suffix=".db", dir=results_dir
    )
    os.close(fd)
    database = Path(database_name)
    api_context = None
    api_client = None
    api_probe_results: list[dict[str, Any]] = []
    if probe_alerts:
        import httpx
        from evidencegate.api.app import create_app

        application = create_app(database)
        application.state.service.registration = registration
        api_context = application.router.lifespan_context(application)
        await api_context.__aenter__()
        # Measure the live application's SQLite writer with the warmed registry.
        writer = application.state.service.writer
        api_client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application),
            base_url="http://acceptance",
        )
        runtime_response = await api_client.get("/runtime")
        runtime_response.raise_for_status()
        runtime_status = runtime_response.json()
        if (
            not runtime_status["alert_policy_active"]
            or runtime_status["alert_policy_version"] != "SIH_ALERT_POLICY_V1"
        ):
            raise RuntimeError("active SIH alert policy unavailable during acceptance")
        dashboard_response = await api_client.get("/")
        dashboard_response.raise_for_status()
        if "Analyst Alerts" not in dashboard_response.text:
            raise RuntimeError("analyst dashboard unavailable during acceptance")
        before_alerts = await api_client.get("/alerts?limit=500")
        before_alerts.raise_for_status()
        api_probe_results.append(
            {
                "phase": "before_measured_load",
                "http_status": before_alerts.status_code,
                "policy_version": runtime_status["alert_policy_version"],
                "dashboard_http_status": dashboard_response.status_code,
            }
        )
    else:
        writer = SqliteWriter(database, root / "evidencegate" / "persistence" / "schema.sql")
        writer.connect()
    process = psutil.Process()
    rss_start = process.memory_info().rss
    rss_peak = rss_start
    state_entry_peak = 0
    controls = []
    gaps = []
    offered_at: dict[str, float] = {}
    offered_index: dict[str, int] = {}
    expected_updates: dict[str, int] = {}
    completed_updates: defaultdict[str, int] = defaultdict(int)
    completed_observations: set[str] = set()
    processing_latencies: list[float] = []
    processing_latency_by_index: dict[int, float] = {}
    persistence_latencies: list[float] = []
    end_to_end_latencies: list[float] = []
    queue_samples: list[dict[str, float | int]] = []
    mechanism_updates = Counter()
    mechanism_results = Counter()
    persistence_failures = 0
    persisted = 0
    sampling = True

    async def control_sink(event) -> None:
        controls.append(event)

    async def gap_sink(gap) -> None:
        gaps.append(gap)

    async def persist(result, _target) -> None:
        nonlocal persisted, persistence_failures
        mechanism_results[result.mechanism_id or result.lane_id] += 1
        started = perf_counter()
        try:
            inserted = await writer.write_result(result)
        except Exception:
            persistence_failures += 1
            raise
        finally:
            persistence_latencies.append(perf_counter() - started)
        if inserted:
            persisted += 1
        arrivals = [
            offered_at[item] for item in result.source_observation_ids if item in offered_at
        ]
        if arrivals:
            end_to_end_latencies.append(perf_counter() - max(arrivals))

    supervisor = RuntimeSupervisor(
        registration.plugins,
        registration.governances,
        persist,
        control_sink=control_sink,
        gap_sink=gap_sink,
        reorder_policies=registration.reorder_policies,
    )

    # Observe completion after the real plugin call. This does not replace or
    # short-circuit any processing, state transition, finalization, or write.
    originals = {}
    for target, plugin in registration.plugins.items():
        original = plugin.process
        originals[target] = original

        async def measured(observation, context, state, *, _original=original, _target=target):
            outcome = await _original(observation, context, state)
            mechanism_updates[str(_target)] += 1
            observation_id = observation.observation_id
            completed_updates[observation_id] += 1
            expected = expected_updates.get(observation_id)
            if expected is not None and completed_updates[observation_id] >= expected:
                if observation_id not in completed_observations:
                    completed_observations.add(observation_id)
                    latency = perf_counter() - offered_at[observation_id]
                    processing_latencies.append(latency)
                    processing_latency_by_index[offered_index[observation_id]] = latency
            return outcome

        plugin.process = measured  # type: ignore[method-assign]

    started = perf_counter()

    async def sampler() -> None:
        nonlocal rss_peak, state_entry_peak
        while sampling:
            rss_peak = max(rss_peak, process.memory_info().rss)
            state_entry_peak = max(
                state_entry_peak,
                sum(len(store) for store in supervisor.state_stores.values()),
            )
            queue_samples.append(
                {"elapsed_seconds": perf_counter() - started, **queue_snapshot(supervisor)}
            )
            await asyncio.sleep(0.05)

    supervisor.start_all()
    sampler_task = asyncio.create_task(sampler())
    watermark_tasks: list[asyncio.Task] = []
    count = max(len(templates), round(rate * duration_seconds))
    interval = 1.0 / rate
    last_event_time = templates[0].event_time
    accepted = 0
    offer_started = perf_counter()
    try:
        for index in range(count):
            deadline = offer_started + index * interval
            delay = deadline - perf_counter()
            if delay > 0:
                await asyncio.sleep(delay)
            observation = repeated_observation(templates, index, run_id)
            offered_at[observation.observation_id] = perf_counter()
            offered_index[observation.observation_id] = index
            plan = await supervisor.ingest_observation(observation)
            expected_updates[observation.observation_id] = len(plan.selected_targets)
            if not plan.selected_targets:
                completed_observations.add(observation.observation_id)
                latency = perf_counter() - offered_at[observation.observation_id]
                processing_latencies.append(latency)
                processing_latency_by_index[index] = latency
            accepted += 1
            last_event_time = observation.event_time
            # Once per wall-clock second, insert serialized event-time markers.
            # Tasks run independently so watermark work does not redefine the
            # offered-rate clock or silently backpressure the source.
            if index and index % rate == 0:
                for target, plugin in registration.plugins.items():
                    if plugin.manifest().state_resource_policy is not None:
                        watermark_tasks.append(
                            asyncio.create_task(
                                supervisor.advance_watermark(target, observation.event_time)
                            )
                        )
        offer_finished = perf_counter()
        # Drain begins the instant offered load stops. It deliberately includes
        # outstanding periodic watermarks, the terminal watermark, queued
        # mechanism work, finalization, and SQLite writes.
        drain_started = perf_counter()
        terminal = last_event_time + timedelta(microseconds=1)
        for target, plugin in registration.plugins.items():
            if plugin.manifest().state_resource_policy is not None:
                watermark_tasks.append(
                    asyncio.create_task(supervisor.advance_watermark(target, terminal))
                )
        if watermark_tasks:
            await asyncio.gather(*watermark_tasks)
        await asyncio.gather(*(item.queue.join() for item in supervisor.dispatchers.values()))
        await asyncio.gather(
            *(shard.queue.join() for shards in supervisor.shards.values() for shard in shards)
        )
        drain_seconds = perf_counter() - drain_started
    finally:
        sampling = False
        await sampler_task
        await supervisor.stop_all()
        for target, plugin in registration.plugins.items():
            plugin.process = originals[target]  # type: ignore[method-assign]
        rss_final = process.memory_info().rss
        rss_peak = max(rss_peak, rss_final)
        final_queue = queue_snapshot(supervisor)
        state_entries = sum(len(store) for store in supervisor.state_stores.values())
        state_entry_peak = max(state_entry_peak, state_entries)
        reorder_peak = max(
            (item.peak_pending_reorder_total for item in supervisor.dispatchers.values()), default=0
        )
        if api_client is not None:
            try:
                response = await api_client.get("/alerts?limit=500")
                response.raise_for_status()
                body = response.json()
                api_probe_results.append(
                    {
                        "phase": "after_measured_load_and_drain",
                        "http_status": response.status_code,
                        "policy_version": body["policy_version"],
                        "alert_count": len(body["alerts"]),
                        "status_count": len(body["status_items"]),
                    }
                )
            except Exception as exc:
                api_probe_results.append({"error": f"{type(exc).__name__}: {exc}"})
        if api_client is not None:
            await api_client.aclose()
        if api_context is not None:
            await api_context.__aexit__(None, None, None)
        else:
            writer.close()

    sqlite_size = database.stat().st_size
    if not keep_database:
        database.unlink(missing_ok=True)
        for suffix in ("-wal", "-shm"):
            Path(str(database) + suffix).unlink(missing_ok=True)
    error_controls = [item for item in controls if item.control_type is ControlType.ERROR]
    state_capacity_events = sum(
        "StateCapacityExceeded" in str(item.typed_payload) for item in error_controls
    )
    reorder_capacity_events = sum(
        any("REORDER_BUFFER" in value for value in item.gap_types) for item in gaps
    )
    queue_overflow = sum(
        any(value == "QUEUE_SATURATION" for value in item.gap_types) for item in gaps
    )
    dropped_runtime = reorder_capacity_events + queue_overflow
    offered_elapsed = max(offer_finished - offer_started, interval)
    completed = len(completed_observations)
    backlog = backlog_assessment(queue_samples, final_queue["total"])
    latency_trend = latency_stability(
        [processing_latency_by_index[index] for index in sorted(processing_latency_by_index)]
    )
    zero_drop = (
        accepted == count
        and dropped_runtime == 0
        and queue_overflow == 0
        and state_capacity_events == 0
        and reorder_capacity_events == 0
        and persistence_failures == 0
        and not error_controls
    )
    sustainable = (
        zero_drop
        and backlog["stable"]
        and final_queue["total"] == 0
        and drain_seconds <= max(5.0, duration_seconds * 0.25)
        and completed == accepted
        and latency_trend["stable"]
        and (
            not probe_alerts
            or (
                len(api_probe_results) == 2
                and all(
                    item.get("policy_version") == "SIH_ALERT_POLICY_V1"
                    for item in api_probe_results
                )
            )
        )
    )
    return {
        "rate_requested_obs_s": rate,
        "duration_requested_seconds": duration_seconds,
        "replicate": replicate,
        "offered_observations": count,
        "accepted_observations": accepted,
        "processed_observations": completed,
        "routed_mechanism_updates": sum(expected_updates.values()),
        "processed_mechanism_updates": sum(mechanism_updates.values()),
        "persisted_results": persisted,
        "rates": {
            "offered_obs_s": round(count / offered_elapsed, 3),
            "accepted_obs_s": round(accepted / offered_elapsed, 3),
            "processed_obs_s": round(
                completed / (offer_finished - offer_started + drain_seconds), 3
            ),
            "routed_updates_s": round(sum(expected_updates.values()) / offered_elapsed, 3),
            "persisted_results_s": round(
                persisted / (offer_finished - offer_started + drain_seconds), 3
            ),
        },
        "drops": {
            "dropped_input": count - accepted,
            "dropped_runtime_work": dropped_runtime,
            "queue_overflow": queue_overflow,
            "state_capacity_events": state_capacity_events,
            "reorder_capacity_events": reorder_capacity_events,
            "persistence_failures": persistence_failures,
            "sse_notification_loss": None,
        },
        "backlog": backlog,
        "drain_seconds": round(drain_seconds, 6),
        "latency": {
            "processing": percentiles_seconds(processing_latencies),
            "persistence": percentiles_seconds(persistence_latencies),
            "end_to_end_evidence": percentiles_seconds(end_to_end_latencies),
            "processing_stability": latency_trend,
        },
        "memory": {
            "rss_start_bytes": rss_start,
            "rss_peak_bytes": rss_peak,
            "rss_final_bytes": rss_final,
            "rss_growth_bytes": rss_final - rss_start,
            "state_entries_end": state_entries,
            "state_entry_peak": state_entry_peak,
            "reorder_peak": reorder_peak,
            "sqlite_final_size_bytes": sqlite_size,
        },
        "mechanism_updates": dict(sorted(mechanism_updates.items())),
        "mechanism_results": dict(sorted(mechanism_results.items())),
        "control_error_count": len(error_controls),
        "zero_drop": zero_drop,
        "sustainable": sustainable,
        "api_probe": {
            "enabled": probe_alerts,
            "query_path": "/alerts?limit=500" if probe_alerts else None,
            "during_measured_load": False,
            "application_started_during_load": probe_alerts,
            "samples": api_probe_results,
        },
    }


def choose_candidate(rate_results: list[dict[str, Any]]) -> tuple[int | None, int | None]:
    """Choose one step below the highest rate with three sustainable replicates."""
    grouped: defaultdict[int, list[dict[str, Any]]] = defaultdict(list)
    for result in rate_results:
        grouped[int(result["rate_requested_obs_s"])].append(result)
    repeated = sorted(
        rate
        for rate, runs in grouped.items()
        if len(runs) >= 3 and all(bool(item["sustainable"]) for item in runs)
    )
    if not repeated:
        return None, None
    highest = repeated[-1]
    lower = sorted(
        rate
        for rate in grouped
        if rate < highest and all(bool(item["sustainable"]) for item in grouped[rate])
    )
    return highest, (lower[-1] if lower else None)


def environment_snapshot() -> dict[str, Any]:
    cpu_model = platform.processor() or os.environ.get("PROCESSOR_IDENTIFIER") or "unavailable"
    dependencies = {}
    for name in ("evidencegate", "dpkt", "scikit-learn", "joblib", "tldextract", "fastapi"):
        try:
            dependencies[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            dependencies[name] = "not-installed"
    return {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "cpu_model": cpu_model,
        "cpu_logical": psutil.cpu_count(logical=True),
        "cpu_physical": psutil.cpu_count(logical=False),
        "ram_total_bytes": psutil.virtual_memory().total,
        "os": platform.platform(),
        "python": platform.python_version(),
        "dependencies": dependencies,
        "sqlite": {"journal_mode": "WAL", "synchronous": "NORMAL", "foreign_keys": "ON"},
    }


async def run_characterization(
    *,
    rates: tuple[int, ...] = DEFAULT_RATES,
    duration_seconds: float = 30.0,
    warmup_seconds: float = 3.0,
    root: Path = ROOT,
) -> dict[str, Any]:
    process = psutil.Process()
    rss_before = process.memory_info().rss
    load_started = perf_counter()
    registration = build_mvp_runtime_registration(
        datetime.now(timezone.utc),
        dga_model_path=str(root / MODEL_PATH.relative_to(ROOT)),
    )
    model_load_seconds = perf_counter() - load_started
    rss_after = process.memory_info().rss
    dga = registration.plugins["dga.m1"]
    if not isinstance(dga, DgaM1Plugin) or dga.readiness is not DgaM1Readiness.VERIFIED_READY:
        raise RuntimeError(
            getattr(dga, "readiness_failure_reason", None) or "DGA model unavailable"
        )
    templates = await load_workload_templates(root)

    warmup = await run_rate_point(
        registration,
        templates,
        rate=25,
        duration_seconds=warmup_seconds,
        replicate=0,
        root=root,
    )
    results: list[dict[str, Any]] = []
    first_limit = None
    for rate in rates:
        result = await run_rate_point(
            registration,
            templates,
            rate=rate,
            duration_seconds=duration_seconds,
            replicate=1,
            root=root,
        )
        results.append(result)
        if not result["sustainable"]:
            first_limit = rate
            break

    clean_rates = [int(item["rate_requested_obs_s"]) for item in results if item["sustainable"]]
    if clean_rates:
        highest_once = max(clean_rates)
        for replicate in (2, 3):
            results.append(
                await run_rate_point(
                    registration,
                    templates,
                    rate=highest_once,
                    duration_seconds=duration_seconds,
                    replicate=replicate,
                    root=root,
                )
            )

    # Repeat the next lower clean point too, because the final target itself must
    # have three repetitions rather than inherit evidence from one lucky run.
    temporary_highest, temporary_candidate = choose_candidate(results)
    if temporary_candidate is not None:
        existing = sum(int(item["rate_requested_obs_s"]) == temporary_candidate for item in results)
        for replicate in range(existing + 1, 4):
            results.append(
                await run_rate_point(
                    registration,
                    templates,
                    rate=temporary_candidate,
                    duration_seconds=duration_seconds,
                    replicate=replicate,
                    root=root,
                )
            )
    highest_repeated, candidate = choose_candidate(results)
    candidate_runs = [item for item in results if item["rate_requested_obs_s"] == candidate]
    candidate_wording = None
    if candidate is not None:
        candidate_wording = (
            "On the measured development machine, the controlled MVP sustained a "
            f"configured offered rate of {candidate} input observations/s for "
            f"{duration_seconds:g} seconds with zero input/runtime "
            "drops under the declared mixed workload."
        )
    return {
        "classification": CLASSIFICATION,
        "watermark": WATERMARK,
        "production_capacity_claim": None,
        "environment": environment_snapshot(),
        "model": {
            "readiness": dga.readiness.value,
            "artifact_sha256": ARTIFACT_SHA256,
            "verification_and_load_seconds": round(model_load_seconds, 6),
            "rss_before_load_bytes": rss_before,
            "rss_after_load_bytes": rss_after,
            "rss_delta_bytes": rss_after - rss_before,
            "warmup_duration_seconds": warmup_seconds,
            "warmup_excluded_from_steady_state": True,
            "warmup_result": warmup,
        },
        "default_target_count": len(registration.plugins),
        "workload": {
            "cycle_observations": len(templates),
            "typed_mix_counts": MIX_COUNTS,
            "typed_mix_proportions": {
                key: value / len(templates) for key, value in MIX_COUNTS.items()
            },
            "eligible_families": ELIGIBLE_FAMILIES,
            "episode_policy": "unique source and role identities per nine-observation episode",
            "event_time_policy": "fixture-relative offsets; seven-minute monotonic episode progression",
            "interpretation_limit": "repetition is infrastructure load only, not population-level threat evidence",
        },
        "duration_basis": (
            f"{duration_seconds:g} seconds per measured point after separate warm-up; "
            "fixed offered count is rate multiplied by duration"
        ),
        "runs": results,
        "highest_repeated_sustainable_zero_drop_rate": highest_repeated,
        "first_saturation_or_limit_rate": first_limit,
        "candidate_sih_demo_input_rate": candidate,
        "candidate_margin_obs_s": (
            highest_repeated - candidate
            if highest_repeated is not None and candidate is not None
            else None
        ),
        "candidate_replicates": candidate_runs,
        "candidate_wording": candidate_wording,
        "limitations": [
            "single measured development host; results do not generalize to production sizing",
            "typed deterministic workload rather than live capture or network line-rate input",
            "repeated fixtures are load stimuli and are not population-level threat evidence",
            "SSE subscriber notification loss is out of scope and recorded separately from runtime drops",
            "raw PCAP is not used for the seven-family rate because its DNS canonical extraction is deferred",
        ],
    }


def markdown_report(payload: dict[str, Any]) -> str:
    rows = []
    for run in payload["runs"]:
        rows.append(
            f"| {run['rate_requested_obs_s']} | {run['replicate']} | {run['offered_observations']} | "
            f"{run['rates']['offered_obs_s']} | {run['rates']['accepted_obs_s']} | "
            f"{run['rates']['processed_obs_s']} | {run['rates']['routed_updates_s']} | "
            f"{run['rates']['persisted_results_s']} | {run['drops']['dropped_runtime_work']} | "
            f"{run['backlog']['peak']} | {run['drain_seconds']} | {run['zero_drop']} | {run['sustainable']} |"
        )
    candidate = payload["candidate_sih_demo_input_rate"]
    candidate_runs = payload["candidate_replicates"]
    latency_rows = []
    memory_rows = []
    for run in candidate_runs:
        latency_rows.append(
            f"| {run['replicate']} | {run['latency']['processing']['p50_ms']} | "
            f"{run['latency']['processing']['p95_ms']} | {run['latency']['processing']['p99_ms']} | "
            f"{run['latency']['persistence']['p50_ms']} | {run['latency']['persistence']['p95_ms']} | "
            f"{run['latency']['persistence']['p99_ms']} | {run['latency']['end_to_end_evidence']['p50_ms']} | "
            f"{run['latency']['end_to_end_evidence']['p95_ms']} | {run['latency']['end_to_end_evidence']['p99_ms']} |"
        )
        memory_rows.append(
            f"| {run['replicate']} | {run['memory']['rss_start_bytes']} | {run['memory']['rss_peak_bytes']} | "
            f"{run['memory']['rss_final_bytes']} | {run['memory']['rss_growth_bytes']} | "
            f"{run['memory']['state_entry_peak']} | {run['memory']['reorder_peak']} | "
            f"{run['memory']['sqlite_final_size_bytes']} |"
        )
    return f"""# Sustained Final MVP Benchmark Report

> **{payload["watermark"]}**

Classification: **{payload["classification"]}**. This measures offered typed input observations on one development machine. It is not production capacity, an SLA, network line rate, or attacks per second.

## Method

The exact stack is real canonicalization -> the real {payload["default_target_count"]}-target registry -> the verified DGA model -> real stateful mechanisms and event-time reorder -> real finalization -> disk-backed SQLite (WAL/NORMAL). The DGA model is loaded and verified once, followed by a separate {payload["model"]["warmup_duration_seconds"]}-second warm-up excluded from every steady-state point.

Workload: `{json.dumps(payload["workload"], sort_keys=True)}`

Duration basis: {payload["duration_basis"]}. Queue/reorder occupancy is sampled every 50 ms. A point is sustainable only with every declared drop counter at zero, completed routed work, empty final backlog, stable backlog, prompt drain, bounded latency, and no runtime control error.

## Environment and startup

```json
{json.dumps({"environment": payload["environment"], "model": {key: value for key, value in payload["model"].items() if key != "warmup_result"}}, indent=2, sort_keys=True)}
```

## Rate sweep and repetitions

| Requested obs/s | Rep | Offered | Actual offered/s | Accepted/s | Processed/s | Routed updates/s | Persisted/s | Runtime drops | Peak backlog | Drain s | Zero drop | Sustainable |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
{chr(10).join(rows)}

Highest repeatedly demonstrated sustainable zero-drop point: **{payload["highest_repeated_sustainable_zero_drop_rate"]} observations/s**.

First saturation/limit point: **{payload["first_saturation_or_limit_rate"] if payload["first_saturation_or_limit_rate"] is not None else "not reached in bounded sweep"}**.

Candidate controlled demo target: **{candidate if candidate is not None else "NONE"} observations/s**. Margin below the highest repeated point: **{payload["candidate_margin_obs_s"]} observations/s**.

## Candidate latency

| Rep | Processing p50 ms | p95 | p99 | Persistence p50 ms | p95 | p99 | End-to-end evidence p50 ms | p95 | p99 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(latency_rows) if latency_rows else "| - | - | - | - | - | - | - | - | - | - |"}

Processing latency runs from offered admission until every selected mechanism update completes. Persistence latency is the actual SQLite write. End-to-end evidence latency runs from the latest contributing observation admission until its immutable result is persisted.

## Candidate memory and storage

| Rep | RSS start | RSS peak | RSS final | Growth | Peak state entries | Peak reorder | SQLite bytes |
|---:|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(memory_rows) if memory_rows else "| - | - | - | - | - | - | - | - |"}

## Governed wording

{payload["candidate_wording"] or "No candidate wording is available because the repeated sustainable-rate rule was not met."}

## Limitations

{chr(10).join("- " + item for item in payload["limitations"])}
"""


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=float, default=30.0)
    parser.add_argument("--warmup", type=float, default=3.0)
    parser.add_argument("--rates", type=int, nargs="+", default=list(DEFAULT_RATES))
    parser.add_argument(
        "--json",
        type=Path,
        default=ROOT / "benchmark_results" / "sustained_final_mvp_benchmark.json",
    )
    parser.add_argument(
        "--report", type=Path, default=ROOT / "SUSTAINED_FINAL_MVP_BENCHMARK_REPORT.md"
    )
    args = parser.parse_args()
    if args.duration <= 0 or args.warmup <= 0 or any(rate <= 0 for rate in args.rates):
        parser.error("duration, warmup, and rates must be positive")
    payload = await run_characterization(
        rates=tuple(args.rates),
        duration_seconds=args.duration,
        warmup_seconds=args.warmup,
    )
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.report.write_text(markdown_report(payload), encoding="utf-8")
    print(
        json.dumps(
            {
                "highest_repeated": payload["highest_repeated_sustainable_zero_drop_rate"],
                "first_limit": payload["first_saturation_or_limit_rate"],
                "candidate": payload["candidate_sih_demo_input_rate"],
                "candidate_wording": payload["candidate_wording"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
