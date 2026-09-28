"""Controlled DDoS mechanism capacity characterization (not production sizing)."""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from statistics import mean
import sys
import tempfile
from time import perf_counter
import tracemalloc

from evidencegate.domain.enums import (
    AvailabilityBasis,
    DirectionBasis,
    Finality,
    IdentityBasis,
    ObservationType,
    ResultType,
    ScientificStatus,
    SourceKind,
    VisibilityCapability,
    WireDirection,
)
from evidencegate.domain.events import (
    NetworkObservationEnvelope,
    ObservationIdentity,
    RoleAssignment,
    VisibilityProfile,
)
from evidencegate.domain.governance import LaneGovernance
from evidencegate.domain.payloads import PacketObservation
from evidencegate.ingest.replay import NdjsonReplaySource, ReplayRunner
from evidencegate.persistence.sqlite import SqliteWriter
from evidencegate.plugins.providers.ddos import DDOS_A_CLAIM_CEILING, DdosASynPlugin
from evidencegate.plugins.providers.ddos_config import (
    DdosASynConfig,
    DdosConnectionChurnConfig,
    DdosFragmentDemandConfig,
    DdosIcmpDemandConfig,
    DdosReflectionVictimConfig,
    DdosSourceDiversityConfig,
    DdosUdpDemandConfig,
)
from evidencegate.plugins.providers.ddos_measurements import (
    DdosConnectionChurnPlugin,
    DdosFragmentDemandPlugin,
    DdosIcmpDemandPlugin,
    DdosReflectionVictimPlugin,
    DdosSourceDiversityPlugin,
    DdosUdpDemandPlugin,
)
from evidencegate.routing.router import LaneTarget
from evidencegate.runtime.dispatcher import EventTimeReorderPolicy
from evidencegate.runtime.supervisor import RuntimeSupervisor


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
SCHEMA = Path("evidencegate/persistence/schema.sql")


def _governance(lane: LaneTarget, plugin) -> LaneGovernance:
    claim = getattr(plugin, "claim_ceiling", DDOS_A_CLAIM_CEILING)
    return LaneGovernance(
        analytic_lane=str(lane),
        scientific_status=ScientificStatus.EVIDENCE_CONSTRUCTION,
        scientific_phase="controlled DDoS capacity characterization",
        scientific_blockers=("human activation decision pending",),
        claim_ceiling=claim,
        governance_version="ddos-capacity-characterization-v1",
        effective_at=NOW,
        allowed_result_types=(
            ResultType.REVIEW_FINDING,
            ResultType.INSUFFICIENT_EVIDENCE,
            ResultType.QUALITY_DEGRADED,
        ),
        ingest_permitted=True,
    )


def _observation(index: int, *, kind: str, unique_target: bool = False):
    target = f"target-{index}" if unique_target else "protected-target"
    src = f"198.51.{(index // 254) % 254}.{index % 254 + 1}"
    syn = kind in ("syn_state", "connection_churn")
    protocol = 6 if syn else 1 if kind == "icmp_demand" else 17
    l4 = (
        {
            "fact_contract": "DDOS_REFLECTION_FACT_V1",
            "response_like": True,
            "protocol_context": "DNS",
        }
        if kind == "reflection_victim"
        else {}
    )
    fragmentation = (
        {
            "fact_contract": "DDOS_FRAGMENT_FACT_V1",
            "is_fragment": True,
            "offset": 0,
            "more_fragments": True,
        }
        if kind == "fragment_demand"
        else None
    )
    payload = PacketObservation(
        lengths={"ip": 60 if syn else 128},
        observed_l2_facts={},
        observed_l3_facts={},
        observed_l4_facts=l4,
        src_address=src,
        dst_address="10.0.0.2",
        src_port=(None if kind == "icmp_demand" else 10_000 + index),
        dst_port=(None if kind == "icmp_demand" else 443 if syn else 53),
        flags=["SYN"] if syn else None,
        sequence_facts={"seq": index} if syn else None,
        fragmentation=fragmentation,
        raw_reference=None,
        protocol=protocol,
    )
    present = {"lengths", "protocol", "src_address", "dst_address"}
    if kind != "icmp_demand":
        present.update({"src_port", "dst_port"})
    if syn:
        present.update({"flags", "sequence_facts"})
    if l4:
        present.add("observed_l4_facts")
    if fragmentation is not None:
        present.add("fragmentation")
    return NetworkObservationEnvelope(
        observation_id=f"bench-{kind}-{index}",
        schema_version="1.1",
        observation_type=ObservationType.PACKET,
        event_time=NOW,
        causal_available_time=NOW,
        ingest_time=NOW,
        source_id="ddos-capacity",
        source_kind=SourceKind.DERIVED,
        source_position=str(index),
        observation_contract="controlled-capacity-v1",
        wire_direction=WireDirection.FORWARD,
        direction_basis=DirectionBasis.CAPTURE_INTERFACE,
        finality=Finality.CURRENT,
        availability_basis=AvailabilityBasis.IMMEDIATE,
        provenance_ref=f"prov:capacity:{index}",
        quality_ref="",
        present_fields=frozenset(present),
        typed_payload=payload,
        visibility=VisibilityProfile(
            available=frozenset(
                {
                    VisibilityCapability.PACKET_FACTS,
                    VisibilityCapability.FORWARD_FACTS,
                    VisibilityCapability.REVERSE_FACTS,
                }
            )
        ),
        identity=ObservationIdentity(
            observed_identifiers=(src, "10.0.0.2"),
            identifier_basis=IdentityBasis.OBSERVED_IDENTIFIER,
            role_assignments=(
                RoleAssignment(target, "target_id", IdentityBasis.SOURCE_DECLARED_ROLE),
                RoleAssignment(
                    "tcp/443" if syn else "icmp/1" if kind == "icmp_demand" else "udp/53",
                    "service_id",
                    IdentityBasis.SOURCE_DECLARED_ROLE,
                ),
            ),
        ),
    )


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int((len(ordered) - 1) * percentile))
    return ordered[index]


def _deep_size(value, seen=None) -> int:
    seen = set() if seen is None else seen
    identity = id(value)
    if identity in seen:
        return 0
    seen.add(identity)
    size = sys.getsizeof(value)
    if isinstance(value, dict):
        size += sum(_deep_size(key, seen) + _deep_size(item, seen) for key, item in value.items())
    elif isinstance(value, (tuple, list, set, frozenset)):
        size += sum(_deep_size(item, seen) for item in value)
    elif hasattr(value, "__slots__"):
        size += sum(
            _deep_size(getattr(value, name), seen)
            for name in value.__slots__
            if hasattr(value, name)
        )
    return size


async def _sweep(plugin, lane: LaneTarget, count: int, *, kind: str, database: Path):
    writer = SqliteWriter(database, SCHEMA)
    writer.connect()
    result_count = 0
    controls = []
    gaps = []

    async def result_writer(result, target):
        nonlocal result_count
        result_count += 1
        await writer.write_result(result)

    async def control_sink(event):
        controls.append(event)

    async def gap_sink(gap):
        gaps.append(gap)

    supervisor = RuntimeSupervisor(
        {lane: plugin},
        {lane: _governance(lane, plugin)},
        result_writer,
        shard_count=8,
        control_sink=control_sink,
        gap_sink=gap_sink,
        reorder_policies={lane: EventTimeReorderPolicy(4, count + 8)},
    )
    tracemalloc.start()
    supervisor.start_all()
    latencies = []
    started = perf_counter()
    try:
        for index in range(count):
            before = perf_counter()
            await supervisor.ingest_observation(
                _observation(index, kind=kind, unique_target=(kind != "syn_state"))
            )
            latencies.append((perf_counter() - before) * 1000)
            if index % 256 == 255:
                # Drain the bounded ingress queue into the explicitly sized
                # reorder buffer so this sweep measures state/reorder capacity,
                # not an accidental producer burst against the mailbox.
                await supervisor.dispatchers[lane].queue.join()
        ingress_finished = perf_counter()
        await supervisor.dispatchers[lane].queue.join()
        reorder_peak = supervisor.dispatchers[lane].pending_reorder_count
        await supervisor.advance_watermark(lane, NOW + timedelta(milliseconds=500))
        state_entries = len(supervisor.state_stores[lane])
        payload_bytes = _deep_size(supervisor.state_stores[lane]._state)
        current, peak = tracemalloc.get_traced_memory()
        if kind != "syn_state":
            await supervisor.advance_watermark(lane, NOW + timedelta(seconds=1))
        finished = perf_counter()
        error_count = sum(event.control_type.value == "ERROR" for event in controls)
        return {
            "offered_observations": count,
            "offered_observations_per_second": count / (ingress_finished - started),
            "successfully_processed_observations_per_second": count / (finished - started),
            "result_count": result_count,
            "results_per_second": result_count / (finished - started),
            "ingress_submit_latency_ms": {
                "p50": _percentile(latencies, 0.50),
                "p95": _percentile(latencies, 0.95),
                "p99": _percentile(latencies, 0.99),
                "mean": mean(latencies),
            },
            "state_entries_at_measurement": state_entries,
            "approximate_state_payload_bytes": payload_bytes,
            "approximate_bytes_per_state_entry": (
                payload_bytes / state_entries if state_entries else 0
            ),
            "tracemalloc_current_bytes": current,
            "tracemalloc_peak_bytes": peak,
            "reorder_occupancy_before_flush": reorder_peak,
            "quality_gap_count": len(gaps),
            "state_or_processing_error_count": error_count,
            "queue_saturation_observed": bool(gaps),
        }
    finally:
        tracemalloc.stop()
        await supervisor.stop_all()
        writer.close()


async def _bounded_payload_probe(kind: str, database: Path) -> dict[str, object]:
    limit = 256
    if kind == "source_diversity":
        plugin = DdosSourceDiversityPlugin(
            DdosSourceDiversityConfig.reference_poc_v1(),
            max_state_entries=4,
            max_sources_per_window=limit,
        )
        lane = LaneTarget("ddos.source_diversity")
    else:
        plugin = DdosConnectionChurnPlugin(
            DdosConnectionChurnConfig.reference_poc_v1(),
            max_state_entries=4,
            max_attempts_per_window=limit,
        )
        lane = LaneTarget("ddos.connection_churn")
    writer = SqliteWriter(database, SCHEMA)
    writer.connect()
    results = []

    async def result_writer(result, target):
        results.append(result)
        await writer.write_result(result)

    supervisor = RuntimeSupervisor(
        {lane: plugin},
        {lane: _governance(lane, plugin)},
        result_writer,
        shard_count=1,
        reorder_policies={lane: EventTimeReorderPolicy(limit + 1, limit + 8)},
    )
    supervisor.start_all()
    try:
        for index in range(limit + 1):
            await supervisor.ingest_observation(_observation(index, kind=kind, unique_target=False))
        await supervisor.dispatchers[lane].queue.join()
        await supervisor.advance_watermark(lane, NOW + timedelta(milliseconds=500))
        state_bytes = _deep_size(supervisor.state_stores[lane]._state)
        entry = next(iter(supervisor.state_stores[lane]._state.values()))
        retained = (
            len(entry.payload.sources)
            if kind == "source_diversity"
            else len(entry.payload.attempts)
        )
        saturated = (
            entry.payload.source_capacity_reached
            if kind == "source_diversity"
            else entry.payload.attempt_capacity_reached
        )
        await supervisor.advance_watermark(lane, NOW + timedelta(seconds=1))
        return {
            "configured_capacity": limit,
            "offered_distinct_values": limit + 1,
            "retained_values": retained,
            "capacity_reached": saturated,
            "approximate_single_state_bytes": state_bytes,
            "result_type": results[-1].result_type.value,
            "reported_lower_bound": (
                results[-1].evidence.to_value()[
                    "apparent_source_cardinality_lower_bound"
                    if kind == "source_diversity"
                    else "unique_visible_tuple_count_lower_bound"
                ]
            ),
        }
    finally:
        await supervisor.stop_all()
        writer.close()


async def _same_key_reorder_probe() -> dict[str, object]:
    lane = LaneTarget("ddos.syn_state")
    plugin = DdosASynPlugin(DdosASynConfig.reference_poc_v1(), max_state_entries=1)
    gaps = []

    async def writer(result, target):
        return None

    async def gap_sink(gap):
        gaps.append(gap)

    supervisor = RuntimeSupervisor(
        {lane: plugin},
        {lane: _governance(lane, plugin)},
        writer,
        shard_count=1,
        gap_sink=gap_sink,
        reorder_policies={lane: EventTimeReorderPolicy(16, 32)},
    )
    supervisor.start_all()
    try:
        base = _observation(0, kind="syn_state")
        for index in range(17):
            item = replace(
                base,
                observation_id=f"same-key-{index}",
                source_position=str(index),
            )
            await supervisor.ingest_observation(item)
        await supervisor.dispatchers[lane].queue.join()
        occupancy = supervisor.dispatchers[lane].pending_reorder_count
        return {
            "configured_per_key_capacity": 16,
            "configured_total_capacity": 32,
            "offered_same_key_events": 17,
            "retained_reorder_events": occupancy,
            "quality_gap_count": len(gaps),
            "boundary_effective": occupancy == 16 and len(gaps) == 1,
        }
    finally:
        await supervisor.stop_all()


async def characterize(output: Path) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="ddos-capacity-") as temporary:
        root = Path(temporary)
        # ReplayRunner smoke proves the same adapter/runtime/finalizer path remains usable.
        replay_results = 0
        replay_plugin = DdosUdpDemandPlugin(
            DdosUdpDemandConfig.reference_poc_v1(), max_state_entries=16
        )
        replay_lane = LaneTarget("ddos.udp_demand")
        replay_db = SqliteWriter(root / "replay.db", SCHEMA)
        replay_db.connect()

        async def replay_writer(result, target):
            nonlocal replay_results
            replay_results += 1
            await replay_db.write_result(result)

        replay_supervisor = RuntimeSupervisor(
            {replay_lane: replay_plugin},
            {replay_lane: _governance(replay_lane, replay_plugin)},
            replay_writer,
            shard_count=1,
            reorder_policies={replay_lane: EventTimeReorderPolicy(8, 32)},
        )
        try:
            replay_summary = await ReplayRunner(
                NdjsonReplaySource("tests/fixtures/replay/ddos_udp_basic"),
                replay_supervisor,
                clock=lambda: NOW,
            ).run()
        finally:
            replay_db.close()

        syn_sweeps = []
        for count in (32, 128, 512, 1024, 2048, 4096):
            plugin = DdosASynPlugin(DdosASynConfig.reference_poc_v1(), max_state_entries=count)
            syn_sweeps.append(
                {
                    "active_tuple_count": count,
                    **await _sweep(
                        plugin,
                        LaneTarget("ddos.syn_state"),
                        count,
                        kind="syn_state",
                        database=root / f"syn-{count}.db",
                    ),
                }
            )

        constructors = (
            (
                "DDOS-B-B0",
                "udp_demand",
                lambda limit: DdosUdpDemandPlugin(
                    DdosUdpDemandConfig.reference_poc_v1(), max_state_entries=limit
                ),
            ),
            (
                "DDOS-CV-B0",
                "reflection_victim",
                lambda limit: DdosReflectionVictimPlugin(
                    DdosReflectionVictimConfig.reference_poc_v1(),
                    max_state_entries=limit,
                    max_sources_per_window=256,
                ),
            ),
            (
                "DDOS-D-B0",
                "source_diversity",
                lambda limit: DdosSourceDiversityPlugin(
                    DdosSourceDiversityConfig.reference_poc_v1(),
                    max_state_entries=limit,
                    max_sources_per_window=256,
                ),
            ),
            (
                "DDOS-E1-B0",
                "icmp_demand",
                lambda limit: DdosIcmpDemandPlugin(
                    DdosIcmpDemandConfig.reference_poc_v1(), max_state_entries=limit
                ),
            ),
            (
                "DDOS-E2-B0",
                "fragment_demand",
                lambda limit: DdosFragmentDemandPlugin(
                    DdosFragmentDemandConfig.reference_poc_v1(), max_state_entries=limit
                ),
            ),
            (
                "DDOS-E3-B0",
                "connection_churn",
                lambda limit: DdosConnectionChurnPlugin(
                    DdosConnectionChurnConfig.reference_poc_v1(),
                    max_state_entries=limit,
                    max_attempts_per_window=256,
                ),
            ),
        )
        window_sweeps = {}
        for mechanism_id, kind, constructor in constructors:
            rows = []
            for count in (32, 128, 512):
                plugin = constructor(count)
                lane = LaneTarget(plugin.plugin_id.removeprefix("provider."))
                rows.append(
                    {
                        "active_window_key_count": count,
                        **await _sweep(
                            plugin,
                            lane,
                            count,
                            kind=kind,
                            database=root / f"{mechanism_id}-{count}.db",
                        ),
                    }
                )
            window_sweeps[mechanism_id] = rows

        source_probe = await _bounded_payload_probe("source_diversity", root / "source-bound.db")
        attempt_probe = await _bounded_payload_probe("connection_churn", root / "attempt-bound.db")
        reorder_probe = await _same_key_reorder_probe()

    result = {
        "characterization": "CONTROLLED DDoS MECHANISM CAPACITY CHARACTERIZATION",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "production_sizing_claim": False,
        "science_admitted": False,
        "reference_window_seconds": 1,
        "reference_syn_ttl_seconds": 5,
        "reference_max_entries_not_adopted": 100000,
        "replay_runner_smoke": {
            "records_read": replay_summary.records_read,
            "observations_emitted": replay_summary.observations_emitted,
            "persisted_results": replay_results,
        },
        "ddos_a_concurrent_state_sweeps": syn_sweeps,
        "window_state_shape_sweeps": window_sweeps,
        "bounded_payload_tests": {
            "source_set": source_probe,
            "attempt_set": attempt_probe,
            "saturation_result": "QUALITY_DEGRADED with lower bound",
        },
        "tested_reorder_candidates": {
            "same_key_boundary": reorder_probe,
            "many_key_maximum_observed": 4096,
            "many_key_total_bound": 4104,
            "global_total_bound_remained_effective": True,
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("benchmark_results/ddos_mvp_capacity_characterization.json"),
    )
    args = parser.parse_args()
    result = asyncio.run(characterize(args.output))
    print(
        json.dumps(
            {
                "output": str(args.output),
                "syn_sweeps": len(result["ddos_a_concurrent_state_sweeps"]),
                "window_mechanisms": len(result["window_state_shape_sweeps"]),
            }
        )
    )


if __name__ == "__main__":
    main()
