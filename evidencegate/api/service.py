"""Application-owned persistence, runtime replay, and notification services."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Mapping

from evidencegate.api.broadcast import ResultBroadcaster
from evidencegate.api.models import (
    FamilyStatusDto, ReplayStatusResponse, ResultNotification, ScenarioDto,
    TargetStatusDto,
)
from evidencegate.ingest.replay import NdjsonReplaySource, ReplayRunner
from evidencegate.ingest.pcap import PcapReplaySource
from evidencegate.persistence.sqlite import SqliteWriter
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


FAMILY_STATUS = (
    FamilyStatusDto(family="DDoS", status="ACTIVE FACTUAL MECHANISMS"),
    FamilyStatusDto(family="C2 / Beaconing", status="ACTIVE R1 RECURRENCE MEASUREMENT"),
    FamilyStatusDto(family="DGA", status="SHELL / MODEL PENDING"),
    FamilyStatusDto(family="DNS Tunnelling", status="ACTIVE T1 STRUCTURAL OBSERVATION"),
    FamilyStatusDto(family="Encrypted Sessions", status="ACTIVE ENC-A HANDSHAKE EVIDENCE"),
    FamilyStatusDto(family="Reconnaissance", status="ACTIVE H/V/2D/TCP MEASUREMENTS"),
    FamilyStatusDto(family="Data Exfiltration", status="ACTIVE M1 TRANSFER MAGNITUDE"),
)


def default_scenarios(root: Path) -> dict[str, ReplayScenario]:
    fixtures = root / "tests" / "fixtures" / "replay"
    definitions = (
        ("mixed_ddos_recon", "DDoS + Recon TCP", "DDoS / Reconnaissance", "default_activation_tcp"),
        ("ddos_one_way", "One-way SYN visibility", "DDoS", "ddos_syn_forward_only"),
        ("ddos_udp", "UDP demand context", "DDoS", "default_activation_udp"),
        ("c2_recurrence", "C2 recurrence measurement", "C2 / Beaconing", "c2_r1"),
        ("dns_observation", "DNS structural observation", "DNS Tunnelling", "dns_forward"),
        ("encrypted_session", "TLS handshake evidence", "Encrypted Sessions", "tls_handshake"),
        ("transfer_magnitude", "Transfer magnitude", "Data Exfiltration", "flow_transfer"),
    )
    scenarios = {
        scenario_id: ReplayScenario(scenario_id, label, family, fixtures / bundle)
        for scenario_id, label, family, bundle in definitions
    }
    pcap_bundle = root / "tests" / "fixtures" / "pcap" / "raw_ddos_recon"
    scenarios["raw_pcap_ddos_recon"] = ReplayScenario(
        "raw_pcap_ddos_recon", "Raw PCAP — DDoS + Recon",
        "DDoS / Reconnaissance", pcap_bundle / "capture.pcap", "PCAP",
        pcap_bundle / "manifest.json",
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
        self.scenarios = dict(scenarios or default_scenarios(repository_root))
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
        registration = build_mvp_runtime_registration(datetime.now(timezone.utc))

        async def writer(result: Result, _target: object) -> None:
            if await self.persist_and_publish(result):
                self._replay.results_persisted += 1

        supervisor = RuntimeSupervisor(
            registration.plugins, registration.governances, writer,
            reorder_policies=registration.reorder_policies,
        )
        try:
            source = (
                PcapReplaySource(scenario.bundle, scenario.manifest)
                if scenario.source_type == "PCAP" and scenario.manifest is not None
                else NdjsonReplaySource(scenario.bundle)
            )
            summary = await ReplayRunner(
                source, supervisor, speed=speed,
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

    def targets(self) -> list[TargetStatusDto]:
        registration = build_mvp_runtime_registration(datetime.now(timezone.utc))
        return [
            TargetStatusDto(
                lane_id=str(lane), mechanism_id=plugin.manifest().mechanism_id,
                implementation=(
                    "REGISTERED_SHELL" if plugin.manifest().mechanism_id is None
                    else "ACTIVE_FACTUAL_MECHANISM"
                ),
            )
            for lane, plugin in registration.plugins.items()
        ]

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
