"""EvidenceGate durable REST, SSE, replay, and dashboard application."""
from __future__ import annotations

import asyncio
import json
import os
from dataclasses import asdict
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from evidencegate.api.models import (
    AlertsResponse, FamilyEvidenceResponse, FamilyEvidenceViewDto,
    HealthResponse, InvestigationLinkDto, InvestigationsResponse,
    QualitySnapshotDto, ReplayRequest, ReplayStatusResponse,
    ResultDto, ResultsResponse, RuntimeStatusResponse, RuntimeTraceEventDto,
    RuntimeTraceResponse, StatusSnapshotDto,
    VisibilitySnapshotDto,
)
from evidencegate.api.projection import (
    POLICY_VERSION, SihAlertProjection, SihStatusProjection, project_results,
)
from evidencegate.api.service import (
    EvidenceGateService, ReplayBusyError, ReplayScenario,
)
from evidencegate.domain.enums import ResultType
from evidencegate.family.composer import FAMILY_BY_LANE, compose_family_evidence, index_investigations
from evidencegate.results.types import AnalyticUnavailable, Result


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PACKAGE_ROOT.parent
SCHEMA_PATH = PACKAGE_ROOT / "persistence" / "schema.sql"
STATIC_ROOT = Path(__file__).with_name("static")


def family_for(result: Result) -> str:
    return FAMILY_BY_LANE.get(result.lane_id, result.taxonomy[1])


def _family_view_dto(view) -> FamilyEvidenceViewDto:
    return FamilyEvidenceViewDto(
        family_view_id=view.family_view_id, family=view.family,
        time_start=view.time_start, time_end=view.time_end,
        entity_references=list(view.entity_references),
        source_result_ids=list(view.source_result_ids),
        source_observation_ids=list(view.source_observation_ids),
        findings=[{
            "source_result_id": finding.source_result_id, "title": finding.title,
            "statements": list(finding.statements), "result_type": finding.result_type,
        } for finding in view.findings],
        limitations=list(view.limitations), missing_evidence=list(view.missing_evidence),
        visibility_summary=list(view.visibility_summary), quality_summary=list(view.quality_summary),
    )


def result_dto(result: Result) -> ResultDto:
    quality = result.quality_snapshot
    visibility = result.visibility_snapshot
    status = result.status_snapshot
    return ResultDto(
        result_id=result.result_id, schema_version=result.schema_version,
        result_type=result.result_type.value, created_time=result.created_time,
        lane_id=result.lane_id, family=family_for(result),
        plugin_id=result.plugin_id, plugin_version=result.plugin_version,
        analytic_version=result.analytic_version,
        governance_version=result.governance_version,
        entity_reference=result.entity_reference, taxonomy=result.taxonomy,
        mechanism_id=result.mechanism_id,
        status_snapshot=StatusSnapshotDto(
            scientific_status=status.scientific_status.value,
            integration_status=status.integration_status.value,
            governance_version=status.governance_version,
            readiness=status.readiness.value,
            quality_degraded=status.quality_degraded,
        ),
        claim_ceiling=result.claim_ceiling,
        evidence=result.evidence.to_value(),
        evidence_items=list(result.evidence_items),
        missing_prerequisites=list(result.missing_prerequisites),
        source_observation_ids=list(result.source_observation_ids),
        source_ids=list(result.source_ids),
        quality_snapshot=QualitySnapshotDto(
            packet_loss=quality.packet_loss.value, sampling=quality.sampling.value,
            parser=quality.parser.value, capture_gap=quality.capture_gap.value,
        ),
        visibility_snapshot=VisibilitySnapshotDto(
            available=sorted(item.value for item in visibility.available),
            unavailable=sorted(item.value for item in visibility.unavailable),
            degraded=sorted(item.value for item in visibility.degraded),
        ),
        state_version=result.state_version, config_hash=result.config_hash,
        parser_refs=list(result.parser_refs), model_refs=list(result.model_refs),
        governing_ids=list(result.governing_ids), quality_refs=list(result.quality_refs),
        provenance_refs=list(result.provenance_refs),
        evidence_interval=result.evidence_interval,
        reason_code=(result.reason_code.value if isinstance(result, AnalyticUnavailable) else None),
    )


def _after_cursor(cursor: str) -> str:
    return f"after.{cursor}"


def _split_cursor(cursor: str | None) -> tuple[str | None, str]:
    if cursor and cursor.startswith("after."):
        return cursor.removeprefix("after."), "after"
    return cursor, "before"


def sse_encode(message: object) -> str:
    payload = message.model_dump(mode="json")  # type: ignore[attr-defined]
    return f"event: {payload['event']}\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n"


def create_app(
    database: str | Path = "evidencegate.db", *,
    scenarios: dict[str, ReplayScenario] | None = None,
    subscriber_queue_size: int = 100,
    alerts_enabled: bool = True,
) -> FastAPI:
    service = EvidenceGateService(
        Path(database), SCHEMA_PATH, REPOSITORY_ROOT,
        scenarios=scenarios, subscriber_queue_size=subscriber_queue_size,
    )

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        service.start()
        application.state.service = service
        try:
            yield
        finally:
            await service.close()

    application = FastAPI(
        title="SIH26145 EvidenceGate", version="0.2.0",
        description=(
            "Durable passive evidence results, bounded live notifications, and "
            "allowlisted controlled replay. Current results retain their factual semantics."
        ),
        lifespan=lifespan,
    )
    application.state.service = service
    application.mount(
        "/assets", StaticFiles(directory=STATIC_ROOT / "assets"), name="assets",
    )
    application.mount("/static", StaticFiles(directory=STATIC_ROOT), name="static")

    @application.get("/", include_in_schema=False)
    async def dashboard() -> FileResponse:
        return FileResponse(STATIC_ROOT / "index.html")

    @application.get(
        "/health", response_model=HealthResponse,
        summary="Application and database health",
    )
    async def health_check() -> HealthResponse:
        if not service.connected:
            raise HTTPException(status_code=503, detail="database is not connected")
        return HealthResponse(status="ok", database="connected")

    @application.get(
        "/results", response_model=ResultsResponse,
        summary="Query immutable results from SQLite",
        description=(
            "Returns deterministic created_time/result_id cursor pages. Normal pages "
            "are newest-first; sync cursors continue forward for reconnect recovery."
        ),
    )
    async def get_results(
        cursor: str | None = None,
        limit: int = Query(default=100, ge=1, le=500),
        lane: str | None = None,
        mechanism_id: str | None = None,
        result_type: ResultType | None = None,
        source_id: str | None = None,
        created_after: datetime | None = Query(default=None, alias="created-after"),
        created_before: datetime | None = Query(default=None, alias="created-before"),
    ) -> ResultsResponse:
        lanes = {target.lane_id for target in service.targets()}
        if lane is not None and lane not in lanes:
            raise HTTPException(status_code=422, detail="lane is not a registered target")
        raw_cursor, direction = _split_cursor(cursor)
        try:
            page = await service.writer.list_results(
                limit=limit + 1, cursor=raw_cursor, lane_id=lane,
                mechanism_id=mechanism_id, result_type=result_type,
                source_id=source_id, created_after=created_after,
                created_before=created_before, direction=direction,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
        visible = page[:limit]
        if direction == "after":
            next_cursor = (
                _after_cursor(service.writer.cursor_for(visible[-1]))
                if visible else cursor
            )
            sync_cursor = next_cursor
        else:
            next_cursor = (
                service.writer.cursor_for(visible[-1]) if len(page) > limit else None
            )
            sync_cursor = (
                _after_cursor(service.writer.cursor_for(visible[0])) if visible else None
            )
        return ResultsResponse(
            results=[result_dto(item) for item in visible],
            next_cursor=next_cursor, sync_cursor=sync_cursor,
        )

    @application.get(
        "/results/{result_id}", response_model=ResultDto,
        summary="Fetch one authoritative immutable result",
    )
    async def get_result(result_id: str) -> ResultDto:
        result = await service.writer.get_result(result_id)
        if result is None:
            raise HTTPException(status_code=404, detail="result not found")
        return result_dto(result)

    @application.get(
        "/family-evidence", response_model=FamilyEvidenceResponse,
        summary="Derive read-only family evidence views from immutable Results",
    )
    async def get_family_evidence(
        limit: int = Query(default=500, ge=1, le=500),
        source_result_id: list[str] | None = Query(default=None),
    ) -> FamilyEvidenceResponse:
        results = await service.writer.list_results(limit=limit)
        if source_result_id:
            selected = set(source_result_id)
            results = tuple(result for result in results if result.result_id in selected)
        views = await asyncio.to_thread(compose_family_evidence, results)
        return FamilyEvidenceResponse(family_views=[_family_view_dto(view) for view in views])

    @application.get(
        "/investigations", response_model=InvestigationsResponse,
        summary="Derive factual cross-family investigation links",
    )
    async def get_investigations(
        limit: int = Query(default=500, ge=1, le=500),
    ) -> InvestigationsResponse:
        results = await service.writer.list_results(limit=limit)
        views = await asyncio.to_thread(compose_family_evidence, results)
        links = await asyncio.to_thread(index_investigations, views)
        return InvestigationsResponse(
            family_views=[_family_view_dto(view) for view in views],
            links=[InvestigationLinkDto(
                link_id=item.link_id,
                left_family_view_id=item.left_family_view_id,
                right_family_view_id=item.right_family_view_id,
                relation_types=list(item.relation_types),
                shared_source_observation_ids=list(item.shared_source_observation_ids),
                source_result_ids=list(item.source_result_ids),
                claim_guard=list(item.claim_guard),
            ) for item in links],
        )

    if alerts_enabled:
        @application.get(
            "/alerts", response_model=AlertsResponse,
            summary="Query active SIH analyst alerts and separate status records",
            description=(
                "Deterministic, versioned presentation over the newest 500 or fewer "
                "immutable results. An alert is an analyst-attention record, not a "
                "confirmed attack. /results remains the scientific authority."
            ),
        )
        async def get_alerts(
            limit: int = Query(default=500, ge=1, le=500),
        ) -> AlertsResponse:
            results = await service.writer.list_results(limit=limit)
            projected = await asyncio.to_thread(project_results, results)
            return AlertsResponse(
                policy_version=POLICY_VERSION,
                alerts=[item for item in projected if isinstance(item, SihAlertProjection)],
                status_items=[item for item in projected if isinstance(item, SihStatusProjection)],
            )

    @application.get(
        "/events", summary="Stream persisted-result notifications",
        description=(
            "SSE emits lightweight hints only after SQLite persistence. A stream_gap "
            "event requires durable REST resynchronization using the last sync cursor."
        ),
    )
    async def events(request: Request) -> StreamingResponse:
        subscription = service.broadcaster.subscribe()

        async def stream() -> AsyncIterator[str]:
            try:
                yield "event: ready\ndata: {}\n\n"
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        message = await asyncio.wait_for(subscription.get(), timeout=15)
                        yield sse_encode(message)
                    except TimeoutError:
                        yield ": keep-alive\n\n"
            finally:
                service.broadcaster.unsubscribe(subscription)

        return StreamingResponse(
            stream(), media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @application.post(
        "/replay", response_model=ReplayStatusResponse, status_code=202,
        summary="Start one allowlisted controlled replay",
    )
    async def replay(request: ReplayRequest) -> ReplayStatusResponse:
        try:
            return await service.begin_replay(request.scenario, request.speed)
        except KeyError:
            raise HTTPException(status_code=422, detail="unknown replay scenario") from None
        except ReplayBusyError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None

    @application.get(
        "/replay/status", response_model=ReplayStatusResponse,
        summary="Read measured replay lifecycle status",
    )
    async def replay_status() -> ReplayStatusResponse:
        return service.replay_status()

    @application.get(
        "/runtime/trace", response_model=RuntimeTraceResponse,
        summary="Read bounded presentation-only runtime trace events",
    )
    async def runtime_trace(
        after: int = Query(default=0, ge=0),
        limit: int = Query(default=100, ge=1, le=500),
    ) -> RuntimeTraceResponse:
        events = service.runtime_trace.snapshot(after=after, limit=limit)
        return RuntimeTraceResponse(
            events=[RuntimeTraceEventDto.model_validate(asdict(event)) for event in events],
            latest_sequence=service.runtime_trace.latest_sequence,
        )

    @application.get(
        "/runtime", response_model=RuntimeStatusResponse,
        summary="Inspect current runtime registration and service state",
    )
    async def runtime_status() -> RuntimeStatusResponse:
        replay_value = service.replay_status()
        targets = service.targets()
        return RuntimeStatusResponse(
            state="REPLAYING" if replay_value.state == "RUNNING" else "ONLINE",
            default_target_count=len(targets),
            active_lane_ids=[item.lane_id for item in targets],
            targets=targets, family_status=service.family_status(),
            database_status="connected",
            durable_result_count=await service.writer.count_results(),
            live_subscriber_count=service.broadcaster.subscriber_count,
            replay=replay_value, scenarios=service.scenario_dtos(),
            supported_sources=["TYPED_NDJSON_REPLAY", "RAW_PCAP_REPLAY"],
            dga_model_readiness=service.dga_plugin.readiness.value,
            dga_model_failure_reason=service.dga_plugin.readiness_failure_reason,
            alert_projection_available=alerts_enabled,
            alert_policy_active=alerts_enabled,
            alert_policy_version=(POLICY_VERSION if alerts_enabled else None),
        )

    return application


app = create_app(
    os.environ.get("EVIDENCEGATE_DB", "evidencegate.db"),
    alerts_enabled=os.environ.get("EVIDENCEGATE_DISABLE_ALERTS", "").strip() != "1",
)
