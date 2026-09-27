"""Application-owned persistence, runtime replay, and notification services."""
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Mapping

from evidencegate.api.broadcast import ResultBroadcaster
from evidencegate.api.runtime_trace import RuntimeTraceBuffer
from evidencegate.api.models import (
    FamilyStatusDto, ReplayStatusResponse, ResultNotification, ScenarioDto,
    TargetStatusDto,
)
from evidencegate.ingest.replay import NdjsonReplaySource, ReplayRunner
from evidencegate.ingest.pcap import PcapReplaySource
from evidencegate.persistence.sqlite import SqliteWriter
from evidencegate.plugins.providers.dga_m1 import DgaM1Plugin, DgaM1Readiness
from evidencegate.plugins.providers.registry import build_mvp_runtime_registration
from evidencegate.results.types import Result
from evidencegate.runtime.supervisor import RuntimeSupervisor

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ReplayScenario:
    scenario_id: str
    label: str
    family: str
    bundle: Path
    source_type: str = "NDJSON"
    manifest: Path | None = None


@dataclass(slots=True)
class _ReplayState:
    state: str = "IDLE"
    scenario: str | None = None
    source_type: str | None = None
    records_read: int = 0
    observations_emitted: int = 0
    results_persisted: int = 0
    elapsed_wall_seconds: float = 0.0
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None


BASE_FAMILY_STATUS = (
    FamilyStatusDto(family="DDoS", status="ACTIVE FACTUAL MECHANISMS"),
    FamilyStatusDto(family="C2 / Beaconing", status="ACTIVE R1 RECURRENCE MEASUREMENT"),
    FamilyStatusDto(family="DNS Tunnelling", status="ACTIVE T1 STRUCTURAL OBSERVATION"),
    FamilyStatusDto(family="Encrypted Sessions", status="ACTIVE ENC-A HANDSHAKE EVIDENCE"),
    FamilyStatusDto(family="Reconnaissance", status="ACTIVE H/V/2D/TCP MEASUREMENTS"),
    FamilyStatusDto(family="Data Exfiltration", status="ACTIVE M1 TRANSFER MAGNITUDE"),
)


def default_scenarios(root: Path) -> dict[str, ReplayScenario]:
    demos = root / "evidencegate" / "demo_data"
    definitions = (
        ("mixed_ddos_recon", "DDoS + Recon fan-out", "DDoS / Reconnaissance", "mixed_ddos_recon_v2"),
        ("ddos_one_way", "One-way SYN visibility", "DDoS", "ddos_one_way_v2"),
        ("c2_recurrence", "C2 recurrence", "C2 / Beaconing", "c2_recurrence_v2"),
        ("dga_lexical", "DGA + DNS", "DGA / DNS", "dga_dns_v2"),
    )
    scenarios = {
        scenario_id: ReplayScenario(scenario_id, label, family, demos / bundle)
        for scenario_id, label, family, bundle in definitions
    }
    pcap_bundle = demos / "raw_pcap_ddos_recon_v2"
    scenarios["raw_pcap_ddos_recon"] = ReplayScenario(
        "raw_pcap_ddos_recon", "Raw PCAP — DDoS + Recon",
        "DDoS / Reconnaissance", pcap_bundle / "capture.pcap", "PCAP",
        pcap_bundle / "manifest.json",
    )
    if os.environ.get("EVIDENCEGATE_DEV_SCENARIOS", "").strip().lower() in {"1", "true", "yes"}:
        fixtures = root / "tests" / "fixtures" / "replay"
        internal = (
            ("mixed_ddos_recon_internal", "Internal TCP fan-out fixture", "DDoS / Reconnaissance", "default_activation_tcp"),
            ("ddos_one_way_internal", "Internal one-way SYN fixture", "DDoS", "ddos_syn_forward_only"),
            ("ddos_udp", "UDP demand context", "DDoS", "default_activation_udp"),
            ("c2_recurrence_internal", "Internal C2 fixture", "C2 / Beaconing", "c2_r1"),
            ("dga_lexical_internal", "Internal DGA fixture", "DGA", "dga_lexical"),
            ("dns_observation", "DNS structural observation", "DNS Tunnelling", "dns_forward"),
            ("encrypted_session", "TLS handshake evidence", "Encrypted Sessions", "tls_handshake"),
            ("transfer_magnitude", "Transfer magnitude", "Data Exfiltration", "flow_transfer"),
        )
        scenarios.update({
            scenario_id: ReplayScenario(scenario_id, label, family, fixtures / bundle)
            for scenario_id, label, family, bundle in internal
        })
        pcap_fixture = root / "tests" / "fixtures" / "pcap" / "raw_ddos_recon"
        scenarios["raw_pcap_internal"] = ReplayScenario(
            "raw_pcap_internal", "Internal PCAP fixture", "DDoS / Reconnaissance",
            pcap_fixture / "capture.pcap", "PCAP", pcap_fixture / "manifest.json",
        )
    return scenarios


class ReplayBusyError(RuntimeError):
    pass


class EvidenceGateService:
    def __init__(
        self, database: Path, schema: Path, repository_root: Path,
        *, scenarios: Mapping[str, ReplayScenario] | None = None,
        subscriber_queue_size: int = 100,
    ):
        self.writer = SqliteWriter(database, schema)
        self.broadcaster = ResultBroadcaster(subscriber_queue_size)
        self.runtime_trace = RuntimeTraceBuffer()
        self.scenarios = dict(scenarios or default_scenarios(repository_root))
        # The verified immutable model is owned by one application service
        # lifecycle and reused by every replay.
        self.registration = build_mvp_runtime_registration(datetime.now(timezone.utc))
        self._replay = _ReplayState()
        self._task: asyncio.Task[None] | None = None
        self._started_monotonic: float | None = None
        self._connected = False

    def start(self) -> None:
        self.writer.connect()
        self._connected = True

    async def close(self) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self.writer.close()
        self._connected = False

    async def persist_and_publish(self, result: Result) -> bool:
        inserted = await self.writer.write_result(result)
        if inserted:
            self.runtime_trace.emit(
                "RESULT_PERSISTED",
                lane_id=result.lane_id,
                mechanism=result.mechanism_id,
                result_id=result.result_id,
                source_observation_ids=list(result.source_observation_ids),
            )
            self.broadcaster.publish(ResultNotification(
                result_id=result.result_id,
                created_time=result.created_time,
                lane_id=result.lane_id,
                mechanism_id=result.mechanism_id,
                result_type=result.result_type.value,
                cursor=f"after.{self.writer.cursor_for(result)}",
            ))
        return inserted

    def replay_status(self) -> ReplayStatusResponse:
        elapsed = self._replay.elapsed_wall_seconds
        if self._replay.state == "RUNNING" and self._started_monotonic is not None:
            elapsed = perf_counter() - self._started_monotonic
        return ReplayStatusResponse(
            state=self._replay.state, scenario=self._replay.scenario,
            source_type=self._replay.source_type,
            records_read=self._replay.records_read,
            observations_emitted=self._replay.observations_emitted,
            results_persisted=self._replay.results_persisted,
            elapsed_wall_seconds=elapsed,
            started_at=self._replay.started_at,
            finished_at=self._replay.finished_at,
            error=self._replay.error,
        )

    async def begin_replay(self, scenario_id: str, speed: float) -> ReplayStatusResponse:
        if scenario_id not in self.scenarios:
            raise KeyError(scenario_id)
        if self._task is not None and not self._task.done():
            raise ReplayBusyError("a replay is already running")
        now = datetime.now(timezone.utc)
        self._replay = _ReplayState(
            state="RUNNING", scenario=scenario_id,
            source_type=self.scenarios[scenario_id].source_type, started_at=now,
        )
        self._started_monotonic = perf_counter()
        self._task = asyncio.create_task(
            self._run_replay(self.scenarios[scenario_id], speed),
            name=f"replay:{scenario_id}",
        )
        await asyncio.sleep(0)
        return self.replay_status()

    async def wait_for_replay(self) -> ReplayStatusResponse:
        if self._task is not None:
            await self._task
        return self.replay_status()

    async def _run_replay(self, scenario: ReplayScenario, speed: float) -> None:
        registration = self.registration

        async def writer(result: Result, _target: object) -> None:
            if await self.persist_and_publish(result):
                self._replay.results_persisted += 1

        supervisor = RuntimeSupervisor(
            registration.plugins, registration.governances, writer,
            reorder_policies=registration.reorder_policies,
            trace_sink=self.runtime_trace.emit,
        )
        try:
            source = (
                PcapReplaySource(scenario.bundle, scenario.manifest)
                if scenario.source_type == "PCAP" and scenario.manifest is not None
                else NdjsonReplaySource(scenario.bundle)
            )
            summary = await ReplayRunner(
                source, supervisor, speed=speed,
                trace_sink=self.runtime_trace.emit,
                progress_sink=self._update_replay_progress,
            ).run()
            self._replay.records_read = summary.records_read
            self._replay.observations_emitted = summary.observations_emitted
            self._replay.elapsed_wall_seconds = summary.elapsed_wall_seconds
            self._replay.state = "COMPLETED"
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Allowlisted replay %s failed", scenario.scenario_id)
            self._replay.state = "FAILED"
            self._replay.error = f"{type(exc).__name__}: replay did not complete"
            if self._started_monotonic is not None:
                self._replay.elapsed_wall_seconds = perf_counter() - self._started_monotonic
        finally:
            self._replay.finished_at = datetime.now(timezone.utc)
            self._started_monotonic = None

    def _update_replay_progress(self, records_read: int, observations_emitted: int) -> None:
        self._replay.records_read = records_read
        self._replay.observations_emitted = observations_emitted

    def targets(self) -> list[TargetStatusDto]:
        return [
            TargetStatusDto(
                lane_id=str(lane), mechanism_id=plugin.manifest().mechanism_id,
                implementation=(
                    "REGISTERED_SHELL" if plugin.manifest().mechanism_id is None
                    else "ACTIVE_LEXICAL_MODEL_LANE" if str(lane) == "dga.m1"
                    else "ACTIVE_FACTUAL_MECHANISM"
                ),
            )
            for lane, plugin in self.registration.plugins.items()
        ]

    @property
    def dga_plugin(self) -> DgaM1Plugin:
        plugin = self.registration.plugins.get("dga.m1")
        if not isinstance(plugin, DgaM1Plugin):
            raise RuntimeError("default dga.m1 registration is missing")
        return plugin

    def family_status(self) -> list[FamilyStatusDto]:
        readiness = self.dga_plugin.readiness
        dga_status = (
            "ACTIVE M1 LEXICAL MODEL EVIDENCE"
            if readiness is DgaM1Readiness.VERIFIED_READY
            else "ACTIVE LANE — MODEL UNAVAILABLE"
        )
        values = list(BASE_FAMILY_STATUS)
        values.insert(2, FamilyStatusDto(family="DGA", status=dga_status))
        return values

    def scenario_dtos(self) -> list[ScenarioDto]:
        return [
            ScenarioDto(
                id=item.scenario_id, label=item.label, family=item.family,
                source_type=item.source_type,
            )
            for item in self.scenarios.values()
        ]

    @property
    def connected(self) -> bool:
        return self._connected
