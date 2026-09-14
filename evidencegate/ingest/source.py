"""
ingest/source.py — InputSource protocol and raw record types.

Contract §4: InputSource adapters are factual. Each adapter must declare
its input observation contract, direction basis, timestamp meaning,
sampling/drop visibility, and derived-record availability rules.
"""
from typing import Protocol, AsyncIterator, Any
from dataclasses import dataclass
from evidencegate.domain.enums import SourceKind


@dataclass(frozen=True, slots=True)
class SourceManifest:
    """
    Produced by InputSource.open(). Declares the source's identity and
    capture bounds so canonicalizers can attach provenance correctly.
    """
    source_id: str
    source_kind: str  # SourceKind value or string for extensibility
    capture_start: Any  # datetime | None
    capture_end: Any    # datetime | None


@dataclass(frozen=True, slots=True)
class RawSourceRecord:
    """
    A single raw input record from a source adapter.
    raw_data may be bytes, a parsed payload object, or any typed adapter output.
    The canonicalizer for each source kind knows how to interpret it.
    timestamp is the adapter's best knowledge of the record's event time.
    position is a source-specific cursor (byte offset, flow index, packet number, etc.)
    """
    raw_data: Any      # typed by the adapter — bytes, dict, or typed payload
    timestamp: Any     # datetime
    position: Any      # str or int; stringified for envelope source_position


class InputSource(Protocol):
    """
    Protocol for passive/replay input adapters. Contract §4.
    """
    source_id: str
    source_kind: str

    async def open(self) -> SourceManifest:
        """Open the source and return its manifest."""
        ...

    async def records(self) -> AsyncIterator[RawSourceRecord]:
        """Yield raw records in source order."""
        ...

    async def pause(self) -> None:
        """Pause emission (only when source can pause)."""
        ...

    async def close(self) -> None:
        """Close the source and release resources."""
        ...
