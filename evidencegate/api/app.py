"""EvidenceGate durable REST, SSE, replay, and dashboard application."""
from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from evidencegate.api.models import (
    AlertsResponse, HealthResponse, QualitySnapshotDto, ReplayRequest, ReplayStatusResponse,
    ResultDto, ResultsResponse, RuntimeStatusResponse, StatusSnapshotDto,
    VisibilitySnapshotDto,
)
from evidencegate.api.projection import (
    POLICY_VERSION, SihAlertProjection, SihStatusProjection, project_results,
)
from evidencegate.api.service import (
    EvidenceGateService, ReplayBusyError, ReplayScenario,
)
from evidencegate.domain.enums import ResultType
from evidencegate.results.types import AnalyticUnavailable, Result


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PACKAGE_ROOT.parent
SCHEMA_PATH = PACKAGE_ROOT / "persistence" / "schema.sql"
STATIC_ROOT = Path(__file__).with_name("static")


def family_for(result: Result) -> str:
    lane = result.lane_id
    if lane.startswith("ddos."):
        return "DDoS"
    if lane.startswith("c2."):
        return "C2 / Beaconing"
    if lane.startswith("dga."):
        return "DGA"
    if lane.startswith("dns_tunnelling."):
        return "DNS Tunnelling"
    if lane.startswith("encrypted_session."):
        return "Encrypted Sessions"
    if lane.startswith("recon."):
        return "Reconnaissance"
    if lane.startswith("unusual_transfer."):
        return "Data Exfiltration"
    return result.taxonomy[1]


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
    candidate_alerts_enabled: bool = False,
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

    if candidate_alerts_enabled:
        @application.get(
            "/alerts", response_model=AlertsResponse,
            summary="Preview the inactive candidate SIH analyst projection",
            description=(
                "Development/test-only deterministic projection over immutable results. "
                "An alert is an analyst-attention record, not a confirmed attack. "
                "The candidate policy is not active and /results remains authoritative."
            ),
        )
        async def get_alerts(
            limit: int = Query(default=500, ge=1, le=500),
        ) -> AlertsResponse:
            results = await service.writer.list_results(limit=limit)
            projected = project_results(results)
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
            alert_projection_available=candidate_alerts_enabled,
            alert_policy_active=False,
            alert_policy_version=(POLICY_VERSION if candidate_alerts_enabled else None),
        )

    return application


app = create_app(
    os.environ.get("EVIDENCEGATE_DB", "evidencegate.db"),
    candidate_alerts_enabled=(
        os.environ.get("EVIDENCEGATE_ENABLE_CANDIDATE_ALERTS", "").strip() == "1"
    ),
)
