"""Best-effort adapter for presentation-only runtime telemetry."""

from __future__ import annotations

from typing import Callable

TraceSink = Callable[..., None] | None


def emit_trace(sink: TraceSink, kind: str, **fields: object) -> None:
    if sink is None:
        return
    try:
        sink(kind, **fields)
    except Exception:
        # A disconnected or faulty presentation observer cannot affect processing.
        return
