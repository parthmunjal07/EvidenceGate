"""Deterministic, test-only Category-5 Recon resource characterization."""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import pickle
import platform
from time import perf_counter
import tracemalloc

from evidencegate.domain.enums import (
    AvailabilityBasis, DirectionBasis, Finality, IdentityBasis, ObservationType,
    QualityState, ResultType, ScientificStatus, SourceKind,
    VisibilityCapability, WireDirection,
)
from evidencegate.domain.events import (
    NetworkObservationEnvelope, ObservationIdentity, RoleAssignment,
    VisibilityProfile,
)
from evidencegate.domain.governance import LaneGovernance
from evidencegate.domain.payloads import PacketObservation
from evidencegate.domain.quality import EvidenceQuality
from evidencegate.plugins.providers.recon import (
    CLAIM_CEILING, Recon2DPlugin, ReconHPlugin, ReconTcpPlugin, ReconVPlugin,
)
from evidencegate.plugins.providers.recon_config import ReconConfig
from evidencegate.routing.router import LaneTarget
from evidencegate.runtime.dispatcher import EventTimeReorderPolicy
from evidencegate.runtime.supervisor import RuntimeSupervisor


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


@dataclass(frozen=True, slots=True)
class ExperimentConfig:
    source_count: int = 64
    hosts_per_source: int = 4
    ports_per_source: int = 4
    max_state_entries_per_lane: int = 2048
    max_events_per_key: int = 32
    reorder_per_key: int = 32
    reorder_total_per_lane: int = 2048
    shard_count: int = 2

    @property
    def observation_count(self) -> int:
        return self.source_count * self.hosts_per_source * self.ports_per_source


def mechanism_config(value: ExperimentConfig) -> ReconConfig:
    return ReconConfig(
        config_id="recon-capacity-characterization-test-only",
        horizons=(timedelta(seconds=60), timedelta(seconds=3600)),
        max_events_per_key=value.max_events_per_key,
        state_ttl=timedelta(seconds=3600),
        initiator_role_label="initiator_id",
        target_role_label="target_id",
    )


def observation(index: int, source: int, host: int, port: int) -> NetworkObservationEnvelope:
    initiator = f"198.18.{source // 256}.{source % 256}"
    target = f"192.0.{host // 256}.{host % 256 + 1}"
    target_port = (22, 80, 443, 8443)[port]
    event_time = NOW + timedelta(microseconds=index)
    payload = PacketObservation(
        lengths={"ip": 40}, observed_l2_facts={}, observed_l3_facts={},
        observed_l4_facts={}, src_address=initiator,
        dst_address=target, src_port=10000 + host * 16 + port,
        dst_port=target_port, flags=["SYN"], sequence_facts=None,
        fragmentation=None, raw_reference=f"capacity:{index}", protocol=6,
    )
    return NetworkObservationEnvelope(
        observation_id=f"recon-capacity-{index}", schema_version="1.1",
        observation_type=ObservationType.PACKET, event_time=event_time,
        causal_available_time=event_time, ingest_time=event_time,
        source_id="recon-capacity-fixture", source_kind=SourceKind.DERIVED,
        source_position=str(index), observation_contract="REPLAY_TYPED_V1",
        wire_direction=WireDirection.FORWARD,
        direction_basis=DirectionBasis.CAPTURE_INTERFACE,
        finality=Finality.CURRENT, availability_basis=AvailabilityBasis.IMMEDIATE,
        provenance_ref=f"prov:capacity:{index}", quality_ref="quality:clear",
        present_fields=frozenset({
            "lengths", "protocol", "observed_l4_facts", "src_address", "dst_address",
            "src_port", "dst_port", "flags", "raw_reference",
        }),
        typed_payload=payload,
        visibility=VisibilityProfile(available=frozenset({
            VisibilityCapability.PACKET_FACTS, VisibilityCapability.FORWARD_FACTS,
        }), unavailable=frozenset({VisibilityCapability.REVERSE_FACTS})),
        identity=ObservationIdentity(
            observed_identifiers=(initiator, target),
            identifier_basis=IdentityBasis.OBSERVED_IDENTIFIER,
            role_assignments=(
                RoleAssignment(initiator, "initiator_id", IdentityBasis.SOURCE_DECLARED_ROLE),
                RoleAssignment(target, "target_id", IdentityBasis.SOURCE_DECLARED_ROLE),
            ),
        ),
        quality=EvidenceQuality(
            packet_loss=QualityState.CLEAR, sampling=QualityState.CLEAR,
            parser=QualityState.CLEAR, capture_gap=QualityState.CLEAR,
        ),
    )


def workload(value: ExperimentConfig):
    index = 0
    for source in range(value.source_count):
        for host in range(value.hosts_per_source):
            for port in range(value.ports_per_source):
                yield observation(index, source, host, port)
                index += 1


def governance(lane: LaneTarget) -> LaneGovernance:
    return LaneGovernance(
        analytic_lane=str(lane), scientific_status=ScientificStatus.EVIDENCE_CONSTRUCTION,
        scientific_phase="test-only resource characterization", scientific_blockers=(),
        claim_ceiling=CLAIM_CEILING, governance_version="recon-capacity-test-v1",
        effective_at=NOW,
        allowed_result_types=(
            ResultType.REVIEW_FINDING, ResultType.INSUFFICIENT_EVIDENCE,
            ResultType.QUALITY_DEGRADED,
        ), ingest_permitted=True,
    )


async def run(value: ExperimentConfig) -> dict[str, object]:
    configuration = mechanism_config(value)
    lanes = {
        LaneTarget("recon.h"): ReconHPlugin(configuration, max_state_entries=value.max_state_entries_per_lane),
        LaneTarget("recon.v"): ReconVPlugin(configuration, max_state_entries=value.max_state_entries_per_lane),
        LaneTarget("recon.2d"): Recon2DPlugin(configuration, max_state_entries=value.max_state_entries_per_lane),
        LaneTarget("recon.tcp"): ReconTcpPlugin(configuration, max_state_entries=value.max_state_entries_per_lane),
    }
    result_types: Counter[str] = Counter()

    async def writer(result, target):
        result_types[result.result_type.value] += 1

    supervisor = RuntimeSupervisor(
        lanes, {lane: governance(lane) for lane in lanes}, writer,
        shard_count=value.shard_count,
        reorder_policies={
            lane: EventTimeReorderPolicy(value.reorder_per_key, value.reorder_total_per_lane)
            for lane in lanes
        },
    )
    controls, gaps = [], []
    for dispatcher in supervisor.dispatchers.values():
        dispatcher._control_sink = lambda item: _append(controls, item)
        dispatcher._gap_sink = lambda item: _append(gaps, item)
    tracemalloc.start()
    started = perf_counter()
    supervisor.start_all()
    try:
        for item in workload(value):
            await supervisor.ingest_observation(item)
        for dispatcher in supervisor.dispatchers.values():
            await dispatcher.queue.join()
        reorder = {
            str(lane): {
                "pending_before_watermark": dispatcher.pending_reorder_count,
                "peak_total": dispatcher.peak_pending_reorder_total,
                "peak_per_key": dispatcher.peak_pending_reorder_per_key,
            }
            for lane, dispatcher in supervisor.dispatchers.items()
        }
        watermark = NOW + timedelta(seconds=1)
        for lane in lanes:
            await supervisor.advance_watermark(lane, watermark)
        elapsed = perf_counter() - started
        current, peak = tracemalloc.get_traced_memory()
        state = {}
        total_serialized = 0
        set_cardinality = {
            "h_distinct_host_memberships": 0,
            "v_distinct_port_memberships": 0,
            "two_d_distinct_pair_memberships": 0,
        }
        for lane, store in supervisor.state_stores.items():
            entries = tuple(store._state.values())
            serialized = sum(len(pickle.dumps(entry.payload, protocol=5)) for entry in entries)
            total_serialized += serialized
            event_count = sum(len(entry.payload.events) for entry in entries)
            state[str(lane)] = {
                "entries": len(entries),
                "retained_events": event_count,
                "serialized_payload_bytes": serialized,
            }
            if str(lane) == "recon.h":
                set_cardinality["h_distinct_host_memberships"] = sum(
                    len({event.target_host for event in entry.payload.events})
                    for entry in entries
                )
            elif str(lane) == "recon.v":
                set_cardinality["v_distinct_port_memberships"] = sum(
                    len({event.target_port for event in entry.payload.events})
                    for entry in entries
                )
            elif str(lane) == "recon.2d":
                set_cardinality["two_d_distinct_pair_memberships"] = sum(
                    len({(event.target_host, event.target_port)
                         for event in entry.payload.events})
                    for entry in entries
                )
        result_count = sum(result_types.values())
        return {
            "experiment_scope": "CONTROLLED_SYNTHETIC_TEST_ONLY",
            "production_throughput_claim": False,
            "config": asdict(value),
            "mechanism_config_hash": configuration.canonical_hash,
            "observations": value.observation_count,
            "mechanism_results": result_count,
            "result_types": dict(sorted(result_types.items())),
            "elapsed_seconds": elapsed,
            "observations_per_second": value.observation_count / elapsed,
            "mechanism_updates_per_second": result_count / elapsed,
            "state": state,
            "total_state_entries": sum(item["entries"] for item in state.values()),
            "total_retained_events": sum(item["retained_events"] for item in state.values()),
            "total_serialized_payload_bytes": total_serialized,
            "measured_exact_set_cardinality": set_cardinality,
            "tracemalloc_current_bytes": current,
            "tracemalloc_peak_bytes": peak,
            "reorder": reorder,
            "quality_gap_types": dict(sorted(Counter(
                gap_type for gap in gaps for gap_type in gap.gap_types
            ).items())),
            "runtime_error_controls": sum(
                item.control_type.value == "ERROR" for item in controls
            ),
            "expected_cardinality": {
                "h_state_keys": value.source_count * value.ports_per_source,
                "v_state_keys": value.source_count * value.hosts_per_source,
                "two_d_state_keys": value.source_count,
                "tcp_state_keys": value.observation_count,
                "h_distinct_host_memberships": value.observation_count,
                "v_distinct_port_memberships": value.observation_count,
                "two_d_distinct_pair_memberships": value.observation_count,
            },
        }
    finally:
        await supervisor.stop_all()
        tracemalloc.stop()


async def _append(collection, item):
    collection.append(item)


def report(payload: dict[str, object]) -> str:
    state = payload["state"]
    reorder = payload["reorder"]
    return f"""# Recon Controlled Resource Characterization

This is a deterministic synthetic mechanics run. It is not production traffic,
does not establish production throughput, and does not activate runtime defaults.

Reproduce from the repository root with
`python -m scripts.benchmark_recon_capacity`.

## Workload

- Observations: {payload['observations']}
- Independent mechanism results: {payload['mechanism_results']}
- Elapsed seconds: {payload['elapsed_seconds']:.6f}
- Observations/second (this run only): {payload['observations_per_second']:.2f}
- Mechanism updates/second (this run only): {payload['mechanism_updates_per_second']:.2f}

## Bounded state

- Total state entries: {payload['total_state_entries']}
- Total retained events: {payload['total_retained_events']}
- Serialized state payload bytes (engineering proxy): {payload['total_serialized_payload_bytes']}
- Measured exact-set memberships: `{json.dumps(payload['measured_exact_set_cardinality'], sort_keys=True)}`
- Tracemalloc current/peak bytes: {payload['tracemalloc_current_bytes']} / {payload['tracemalloc_peak_bytes']}
- Per lane: `{json.dumps(state, sort_keys=True)}`

## Reorder occupancy

`{json.dumps(reorder, sort_keys=True)}`

Quality gaps: `{json.dumps(payload['quality_gap_types'], sort_keys=True)}`
Runtime error controls: {payload['runtime_error_controls']}

## Engineering interpretation

The run supplies a measured point, not a final capacity decision. A follow-up
capacity gate should test at least 2x this key/event cardinality under the target
deployment memory limit before selecting any candidate range. No production
capacity, horizon, or reorder value is introduced by this report.
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", type=Path, default=Path("benchmark_results/recon_capacity_characterization.json"))
    parser.add_argument("--report", type=Path, default=Path("RECON_CAPACITY_CHARACTERIZATION_REPORT.md"))
    args = parser.parse_args()
    payload = asyncio.run(run(ExperimentConfig()))
    payload["environment"] = {
        "python": platform.python_version(), "platform": platform.platform(),
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.report.write_text(report(payload), encoding="utf-8")
    print(json.dumps({
        "json": str(args.json), "report": str(args.report),
        "observations": payload["observations"],
        "results": payload["mechanism_results"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
