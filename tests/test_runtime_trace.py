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
from evidencegate.results.types import (
    EvidencePayload, Result, ResultStatusSnapshot,
)
from evidencegate.domain.enums import EvidenceReadiness, IntegrationStatus
from evidencegate.domain.quality import EvidenceQuality
from evidencegate.domain.events import VisibilityProfile


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
    events = buffer.snapshot(after=1, limit=10)
    assert [event.sequence for event in events] == [3, 4, 5]
    assert buffer.latest_sequence == 5


def test_trace_snapshot_pages_forward_from_cursor():
    buffer = RuntimeTraceBuffer(capacity=1000)
    for index in range(700):
        buffer.emit("OBSERVATION_CREATED", observation_id=f"packet-{index}")

    first = buffer.snapshot(after=100, limit=100)
    second = buffer.snapshot(after=200, limit=100)

    assert [event.sequence for event in first] == list(range(101, 201))
    assert [event.sequence for event in second] == list(range(201, 301))
    assert buffer.latest_sequence == 700


def test_default_trace_buffer_retains_complete_pcaps_well_over_one_page():
    buffer = RuntimeTraceBuffer()
    for index in range(700):
        buffer.emit("OBSERVATION_CREATED", observation_id=f"packet-{index}")

    events = buffer.snapshot(after=0, limit=1000)

    assert len(events) == 700
    assert events[0].sequence == 1
    assert events[-1].sequence == 700


@pytest.mark.asyncio
async def test_trace_api_exposes_bounded_typed_events(tmp_path):
    app = create_app(tmp_path / "trace-api.sqlite")
    async with app.router.lifespan_context(app):
        app.state.service.runtime_trace.emit(
            "RESULT_PERSISTED", result_id="result-api",
            source_observation_ids=["obs-a", "obs-b", "obs-c"],
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test",
        ) as client:
            response = await client.get("/runtime/trace?after=0&limit=1")
    assert response.status_code == 200
    payload = response.json()
    assert payload["latest_sequence"] == 1
    assert payload["events"][0]["kind"] == "RESULT_PERSISTED"
    assert payload["events"][0]["source_observation_ids"] == ["obs-a", "obs-b", "obs-c"]
    assert payload["events"][0]["observation_id"] is None


@pytest.mark.asyncio
async def test_trace_api_pages_forward_while_reporting_global_latest(tmp_path):
    app = create_app(tmp_path / "trace-pagination.sqlite")
    async with app.router.lifespan_context(app):
        trace = app.state.service.runtime_trace
        for index in range(700):
            trace.emit("OBSERVATION_CREATED", observation_id=f"packet-{index}")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test",
        ) as client:
            first = await client.get("/runtime/trace?after=100&limit=100")
            second = await client.get("/runtime/trace?after=200&limit=100")

    assert first.status_code == second.status_code == 200
    first_payload = first.json()
    second_payload = second.json()
    assert [event["sequence"] for event in first_payload["events"]] == list(range(101, 201))
    assert [event["sequence"] for event in second_payload["events"]] == list(range(201, 301))
    assert first_payload["latest_sequence"] == second_payload["latest_sequence"] == 700


@pytest.mark.asyncio
async def test_trace_api_head_query_returns_current_sequence_without_draining_history(tmp_path):
    app = create_app(tmp_path / "trace-head.sqlite")
    async with app.router.lifespan_context(app):
        trace = app.state.service.runtime_trace
        for index in range(4500):
            trace.emit("SOURCE_RECORD_ACCEPTED", observation_id=f"record-{index}")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test",
        ) as client:
            response = await client.get("/runtime/trace?after=0&limit=1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["latest_sequence"] == 4500
    assert len(payload["events"]) == 1


@pytest.mark.asyncio
async def test_persisted_result_trace_keeps_full_lineage_without_claiming_one_cause(tmp_path):
    app = create_app(tmp_path / "trace-lineage.sqlite")
    service = app.state.service
    async def inserted(_result): return True
    service.writer.write_result = inserted
    service.writer.cursor_for = lambda _result: "cursor-test"
    result = Result(
        result_id="result-lineage", schema_version="3.0", result_type=ResultType.REVIEW_FINDING,
        created_time=NOW, lane_id="c2.r1", plugin_id="c2", plugin_version="1",
        analytic_version="1", governance_version="g1", entity_reference="entity",
        taxonomy=("network", "c2", "recurrence"),
        status_snapshot=ResultStatusSnapshot(
            ScientificStatus.EVIDENCE_CONSTRUCTION, IntegrationStatus.BASELINE_IMPLEMENTED,
            "g1", EvidenceReadiness.READY, False,
        ),
        claim_ceiling="REVIEW", evidence_items=(), missing_prerequisites=(),
        governing_ids=(), quality_refs=(), provenance_refs=(), mechanism_id="C2-R1",
        evidence=EvidencePayload.from_value({}),
        source_observation_ids=("obs-a", "obs-b", "obs-c"),
        quality_snapshot=EvidenceQuality(), visibility_snapshot=VisibilityProfile(),
    )

    assert await service.persist_and_publish(result) is True
    event = service.runtime_trace.snapshot()[0]
    assert event.kind == "RESULT_PERSISTED"
    assert event.source_observation_ids == ["obs-a", "obs-b", "obs-c"]
    assert event.observation_id is None


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
