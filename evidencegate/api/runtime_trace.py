"""Bounded, presentation-only runtime trace events."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import Any


@dataclass(frozen=True, slots=True)
class RuntimeTraceEvent:
    sequence: int
    kind: str
    occurred_at: datetime
    observation_id: str | None = None
    observation_type: str | None = None
    lane_id: str | None = None
    mechanism: str | None = None
    readiness: str | None = None
    reason: str | None = None
    result_id: str | None = None
    source_observation_ids: list[str] = field(default_factory=list)


class RuntimeTraceBuffer:
    """Thread-safe ring buffer. Appending is synchronous, bounded, and best effort."""

    def __init__(self, capacity: int = 5000):
        if capacity < 1:
            raise ValueError("capacity must be positive")
        self._events: deque[RuntimeTraceEvent] = deque(maxlen=capacity)
        self._lock = Lock()
        self._sequence = 0

    def emit(self, kind: str, **fields: Any) -> None:
        try:
            with self._lock:
                self._sequence += 1
                self._events.append(RuntimeTraceEvent(
                    sequence=self._sequence,
                    kind=kind,
                    occurred_at=datetime.now(timezone.utc),
                    **fields,
                ))
        except Exception:
            # Presentation telemetry must never affect source/runtime processing.
            return

    def snapshot(self, after: int = 0, limit: int = 100) -> tuple[RuntimeTraceEvent, ...]:
        with self._lock:
            return tuple(event for event in self._events if event.sequence > after)[-limit:]

    @property
    def latest_sequence(self) -> int:
        with self._lock:
            return self._sequence
