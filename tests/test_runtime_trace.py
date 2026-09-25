from datetime import datetime, timezone
from dataclasses import replace

import pytest
import httpx

from evidencegate.api.app import create_app
from evidencegate.api.runtime_trace import RuntimeTraceBuffer
from evidencegate.domain.enums import (
    AvailabilityBasis, DirectionBasis, Finality, ObservationType, ResultType,
    ScientificStatus, SourceKind, WireDirection,
)
from evidencegate.domain.events import NetworkObservationEnvelope
from evidencegate.domain.governance import LaneGovernance
from evidencegate.domain.payloads import PacketObservation
from evidencegate.plugins.scaffolds.basic_scaffold import BasicScaffoldPlugin
from evidencegate.routing.router import LaneTarget
from evidencegate.runtime.supervisor import RuntimeSupervisor
from evidencegate.runtime.trace import emit_trace


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def observation():
    return NetworkObservationEnvelope(
        observation_id="trace-obs-1", schema_version="1.1",
        observation_type=ObservationType.PACKET, event_time=NOW,
        causal_available_time=NOW, ingest_time=NOW, source_id="trace-source",
        source_kind=SourceKind.PCAP, source_position="1",
        observation_contract="packet_v1", wire_direction=WireDirection.UNKNOWN,
        direction_basis=DirectionBasis.UNKNOWN, finality=Finality.CURRENT,
        availability_basis=AvailabilityBasis.IMMEDIATE,
        provenance_ref="prov:trace", quality_ref="quality:trace",
        present_fields=frozenset(),
        typed_payload=PacketObservation({}, {}, {}, {}, None, None, None, None, None, None, None, None),
    )


def governance(lane):
    return LaneGovernance(
        analytic_lane=lane, scientific_status=ScientificStatus.EVIDENCE_CONSTRUCTION,
        scientific_phase="trace-test", scientific_blockers=(),
        claim_ceiling="REVIEW_FINDING_ONLY", governance_version="trace-test-v1",
        effective_at=NOW, allowed_result_types=(ResultType.REVIEW_FINDING,),
        ingest_permitted=True,
    )


def test_trace_buffer_is_bounded_and_keeps_monotonic_cursor():
    buffer = RuntimeTraceBuffer(capacity=3)
    for index in range(5):
        buffer.emit("SOURCE_RECORD_ACCEPTED", reason=str(index))
    events = buffer.snapshot(after=2, limit=10)
    assert [event.sequence for event in events] == [3, 4, 5]
    assert buffer.latest_sequence == 5


@pytest.mark.asyncio
async def test_trace_api_exposes_bounded_typed_events(tmp_path):
    app = create_app(tmp_path / "trace-api.sqlite")
    async with app.router.lifespan_context(app):
        app.state.service.runtime_trace.emit("OBSERVATION_CREATED", observation_id="obs-api")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test",
        ) as client:
            response = await client.get("/runtime/trace?after=0&limit=1")
    assert response.status_code == 200
    payload = response.json()
    assert payload["latest_sequence"] == 1
    assert payload["events"][0]["kind"] == "OBSERVATION_CREATED"
    assert payload["events"][0]["observation_id"] == "obs-api"


@pytest.mark.asyncio
async def test_telemetry_reports_real_zero_to_many_routes_and_sink_failure_isolated():
    plugins = {
        LaneTarget("first"): BasicScaffoldPlugin(),
        LaneTarget("second"): BasicScaffoldPlugin(),
    }
    # The two plugins need unique registration identities while retaining the
    # same default packet routing behavior.
    for lane, plugin in plugins.items():
        original = plugin.manifest
        plugin.manifest = lambda original=original, lane=lane: replace(
            original(), plugin_id=str(lane), accepted_observation_types=(ObservationType.PACKET,),
        )
    trace = RuntimeTraceBuffer()
    supervisor = RuntimeSupervisor(
        plugins, {lane: governance(str(lane)) for lane in plugins},
        lambda _result, _target: None, shard_count=1,
        trace_sink=trace.emit,
    )
    plan = await supervisor.ingest_observation(observation())
    selected = {str(target) for target in plan.selected_targets}
    routed = {event.lane_id for event in trace.snapshot() if event.kind == "ROUTED"}
    assert selected == routed == {"first", "second"}

    def disconnected(*_args, **_kwargs):
        raise RuntimeError("UI disconnected")

    isolated = RuntimeSupervisor(
        plugins, {lane: governance(str(lane)) for lane in plugins},
        lambda _result, _target: None, shard_count=1,
        trace_sink=disconnected,
    )
    disconnected_plan = await isolated.ingest_observation(observation())
    assert disconnected_plan.selected_targets == plan.selected_targets
    emit_trace(disconnected, "ANALYTIC_EVALUATED")
