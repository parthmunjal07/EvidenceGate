"""Incremental, read-only replay adapter and runtime orchestrator."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import perf_counter
from typing import AsyncIterator, Awaitable, Callable

from evidencegate.domain.enums import ControlType, ObservationType
from evidencegate.domain.events import RuntimeControlEvent
from evidencegate.ingest.builders import (
    DNSCanonicalBuilder, PacketCanonicalBuilder, QUICCanonicalBuilder,
    TLSCanonicalBuilder,
)
from evidencegate.ingest.canonicalizer import CanonicalizationResult, FlowCanonicalizer
from evidencegate.ingest.replay_schema import (
    ReplayManifest, ReplaySourceRecord, ReplayValidationError, parse_manifest,
    parse_record_line,
)
from evidencegate.ingest.source import RawSourceRecord, SourceManifest
from evidencegate.runtime.supervisor import RuntimeSupervisor


def utc_now() -> datetime:
    """Return the replay process's current timezone-aware UTC wall time."""
    return datetime.now(timezone.utc)


class NdjsonReplaySource:
    """Read one typed record at a time from an immutable finite bundle."""

    def __init__(self, bundle: str | Path):
        self.bundle = Path(bundle)
        self.source_id = "<unopened>"
        self.source_kind = None
        self.replay_manifest: ReplayManifest | None = None
        self._file = None
        self._paused = asyncio.Event()
        self._paused.set()
        self._opened = False
        self._consumed = False

    async def open(self) -> SourceManifest:
        if self._opened:
            raise RuntimeError("replay source is already open")
        self.replay_manifest = parse_manifest(self.bundle / "manifest.json")
        manifest = self.replay_manifest.source_manifest
        self.source_id, self.source_kind = manifest.source_id, manifest.source_kind
        try:
            self._file = (self.bundle / "records.ndjson").open("r", encoding="utf-8")
        except OSError as exc:
            raise ReplayValidationError(self.source_id, "records.ndjson", type(exc).__name__, str(exc)) from exc
        self._opened = True
        return manifest

    async def records(self) -> AsyncIterator[RawSourceRecord]:
        if not self._opened or self._file is None or self.replay_manifest is None:
            raise RuntimeError("open() must be called before records()")
        if self._consumed:
            raise RuntimeError("records() may be consumed only once per source")
        self._consumed = True
        previous = None
        count = 0
        for line_number, text in enumerate(self._file, 1):
            await self._paused.wait()
            if not text.strip():
                raise ReplayValidationError(self.source_id, f"line {line_number}", "SchemaError", "blank NDJSON lines are not allowed")
            record = parse_record_line(text, source_id=self.source_id, line_number=line_number)
            if previous is not None and record.timestamp < previous:
                raise ReplayValidationError(
                    self.source_id, f"line {line_number}", "EventTimeOrderError",
                    "timestamp decreases under NONDECREASING contract",
                )
            previous = record.timestamp
            count += 1
            yield record
        expected = self.replay_manifest.record_count
        if expected is not None and count != expected:
            raise ReplayValidationError(self.source_id, "EOF", "RecordCountError", f"manifest declares {expected}, read {count}")

    async def pause(self) -> None:
        self._paused.clear()

    async def resume(self) -> None:
        self._paused.set()

    async def close(self) -> None:
        if self._file is not None:
            self._file.close()
        self._file = None
        self._opened = False


class ReplayCanonicalizer:
    """Dispatch replay facts through the existing canonical builders."""

    def __init__(self) -> None:
        self._flow = FlowCanonicalizer()
        self._builders = {
            ObservationType.PACKET: PacketCanonicalBuilder(),
            ObservationType.DNS: DNSCanonicalBuilder(),
            ObservationType.TLS: TLSCanonicalBuilder(),
            ObservationType.QUIC: QUICCanonicalBuilder(),
        }

    def canonicalize(
        self, record: RawSourceRecord, manifest: SourceManifest, quality_ref: str,
        ingest_time: datetime,
    ) -> CanonicalizationResult:
        if not isinstance(record, ReplaySourceRecord):
            raise TypeError("ReplayCanonicalizer requires ReplaySourceRecord")
        common = dict(
            record=record, manifest=manifest, quality_ref=quality_ref,
            ingest_time=ingest_time,
            declared_observed_fields=record.declared_observed_fields,
            role_assignments=record.role_assignments,
        )
        if record.observation_type is ObservationType.FLOW:
            return self._flow.canonicalize(**common)
        envelope = self._builders[record.observation_type].canonicalize(
            **common, **record.canonicalization_options,
        )
        return CanonicalizationResult((envelope,), ())


@dataclass(frozen=True, slots=True)
class ReplaySummary:
    """Replay counts; ``control_events`` counts replay and canonicalizer events forwarded by replay, not supervisor-generated events."""

    records_read: int
    observations_emitted: int
    control_events: int
    elapsed_wall_seconds: float


class ReplayRunner:
    """Feed a finite source incrementally into the existing runtime."""

    def __init__(
        self, source: NdjsonReplaySource, supervisor: RuntimeSupervisor, *,
        speed: float = 0,
        control_sink: Callable[[RuntimeControlEvent], Awaitable[None]] | None = None,
        canonicalizer: ReplayCanonicalizer | None = None,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        if isinstance(speed, bool) or not isinstance(speed, (int, float)) or speed < 0:
            raise ValueError("speed must be a non-negative number")
        if not callable(clock):
            raise TypeError("clock must be callable")
        self.source, self.supervisor, self.speed = source, supervisor, float(speed)
        self.control_sink = control_sink
        self.canonicalizer = canonicalizer or ReplayCanonicalizer()
        self.clock = clock
        self._control_count = 0

    def _clock_now(self) -> datetime:
        """Acquire and validate one replay-arrival timestamp."""
        value = self.clock()
        if not isinstance(value, datetime):
            raise TypeError("clock must return a datetime")
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware datetime")
        return value

    async def _control(self, control_type: ControlType, *, event_time=None, payload=None) -> None:
        event = RuntimeControlEvent(
            control_event_id=f"replay:{self.source.source_id}:{control_type.value}:{self._control_count + 1}",
            schema_version="1.1", control_type=control_type,
            ingest_time=self._clock_now(), event_time=event_time,
            source_id=self.source.source_id,
            typed_payload=payload or {"component": "replay"},
        )
        self._control_count += 1
        if self.control_sink is not None:
            await self.control_sink(event)

    def _stateful_targets(self):
        return tuple(
            target for target, plugin in self.supervisor.plugins.items()
            if plugin.manifest().state_resource_policy is not None
        )

    async def _watermark(self, value: datetime) -> None:
        for target in self._stateful_targets():
            await self.supervisor.advance_watermark(target, value)

    async def _drain(self) -> None:
        if self.supervisor.dispatchers:
            await asyncio.gather(*(item.queue.join() for item in self.supervisor.dispatchers.values()))
        queues = [shard.queue.join() for shards in self.supervisor.shards.values() for shard in shards]
        if queues:
            await asyncio.gather(*queues)

    async def run(self) -> ReplaySummary:
        started = perf_counter()
        records_read = observations_emitted = 0
        manifest = await self.source.open()
        self.supervisor.start_all()
        previous = maximum = None
        try:
            await self._control(ControlType.SOURCE_STARTED, payload={
                "component": "replay", "bundle": str(self.source.bundle),
                "event_time_order": "NONDECREASING",
            })
            async for raw in self.source.records():
                record = raw
                if previous is not None and record.timestamp > previous:
                    if self.speed:
                        await asyncio.sleep((record.timestamp - previous).total_seconds() / self.speed)
                    await self._watermark(record.timestamp)
                result = self.canonicalizer.canonicalize(
                    record, manifest, f"quality:{manifest.source_id}:{record.position}",
                    self._clock_now(),
                )
                for event in result.control_events:
                    self._control_count += 1
                    if self.control_sink is not None:
                        await self.control_sink(event)
                for observation in result.observations:
                    await self.supervisor.ingest_observation(observation)
                    observations_emitted += 1
                records_read += 1
                previous = maximum = record.timestamp
            if maximum is not None and self._stateful_targets():
                if maximum == datetime.max.replace(tzinfo=maximum.tzinfo):
                    raise ReplayValidationError(manifest.source_id, "EOF", "TerminalWatermarkError", "datetime.max cannot be advanced by one microsecond")
                await self._watermark(maximum + timedelta(microseconds=1))
            await self._drain()
            await self._control(ControlType.SOURCE_ENDED, event_time=maximum, payload={
                "component": "replay", "records_read": records_read,
                "observations_emitted": observations_emitted,
                "terminal_boundary": "finite-source EOF",
            })
            return ReplaySummary(records_read, observations_emitted, self._control_count, perf_counter() - started)
        except Exception as exc:
            await self._control(ControlType.ERROR, event_time=maximum, payload={
                "component": "replay", "exception_type": type(exc).__name__,
                "error": str(exc)[:500],
            })
            raise
        finally:
            await self._drain()
            await self.supervisor.stop_all()
            await self.source.close()


async def validate_bundle(bundle: str | Path) -> int:
    """Validate every manifest/record fact without invoking analytics."""
    source = NdjsonReplaySource(bundle)
    count = 0
    manifest = await source.open()
    canonicalizer = ReplayCanonicalizer()
    try:
        async for record in source.records():
            # Builder validation is part of the replay contract (declared
            # presence and factual visibility options), but no runtime/plugin
            # code is invoked in validation-only mode.
            canonicalizer.canonicalize(
                record, manifest,
                f"quality:{manifest.source_id}:{record.position}", record.timestamp,
            )
            count += 1
    finally:
        await source.close()
    return count
