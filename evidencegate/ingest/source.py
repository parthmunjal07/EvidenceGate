"""
ingest/source.py — InputSource protocol and raw record types.

Contract §4: InputSource adapters are factual. Each adapter must declare
its input observation contract, direction basis, timestamp meaning,
sampling/drop visibility, and derived-record availability rules.
"""

from typing import Protocol, AsyncIterator, Any
from dataclasses import dataclass
from datetime import datetime
from evidencegate.domain.enums import (
    CapabilityState,
    DirectionBasis,
    Finality,
    SourceKind,
    TimestampSemantics,
    VisibilityCapability,
    WireDirection,
)
from evidencegate.domain.events import VisibilityProfile
from evidencegate.domain.quality import EvidenceQuality


@dataclass(frozen=True, slots=True)
class SourceManifest:
    """
    Produced by InputSource.open(). Declares the source's identity and
    capture bounds so canonicalizers can attach provenance correctly.
    """

    source_id: str
    source_kind: SourceKind
    capture_start: datetime | None
    capture_end: datetime | None
    timestamp_semantics: TimestampSemantics
    input_observation_contract: str
    direction_basis: DirectionBasis = DirectionBasis.UNKNOWN
    wire_direction: WireDirection = WireDirection.UNKNOWN
    visibility: VisibilityProfile = VisibilityProfile()
    quality: EvidenceQuality = EvidenceQuality()

    def __post_init__(self) -> None:
        if not isinstance(self.source_kind, SourceKind):
            raise TypeError("source_kind must be SourceKind")
        if not isinstance(self.timestamp_semantics, TimestampSemantics):
            raise TypeError("timestamp_semantics must be TimestampSemantics")
        if not isinstance(self.direction_basis, DirectionBasis):
            raise TypeError("direction_basis must be DirectionBasis")
        if not isinstance(self.wire_direction, WireDirection):
            raise TypeError("wire_direction must be WireDirection")
        if not isinstance(self.visibility, VisibilityProfile):
            raise TypeError("visibility must be VisibilityProfile")
        if not isinstance(self.quality, EvidenceQuality):
            raise TypeError("quality must be EvidenceQuality")
        if (
            self.wire_direction is not WireDirection.UNKNOWN
            and self.direction_basis is DirectionBasis.UNKNOWN
        ):
            raise ValueError("known source direction requires an explicit direction basis")
        if not self.timestamp_semantics:
            raise ValueError("timestamp_semantics must be declared")
        if not self.input_observation_contract:
            raise ValueError("input_observation_contract must be versioned and non-empty")
        directional_capability = {
            WireDirection.FORWARD: VisibilityCapability.FORWARD_FACTS,
            WireDirection.REVERSE: VisibilityCapability.REVERSE_FACTS,
        }.get(self.wire_direction)
        if (
            directional_capability is not None
            and self.visibility.state(directional_capability) is CapabilityState.UNAVAILABLE
        ):
            raise ValueError("known source direction contradicts unavailable directional facts")


@dataclass(frozen=True, slots=True)
class RawSourceRecord:
    """
    A single raw input record from a source adapter.
    raw_data may be bytes, a parsed payload object, or any typed adapter output.
    The canonicalizer for each source kind knows how to interpret it.
    timestamp is the adapter's best knowledge of the record's event time.
    position is a source-specific cursor (byte offset, flow index, packet number, etc.)
    """

    raw_data: Any  # typed by the adapter — bytes, dict, or typed payload
    timestamp: Any  # datetime
    position: Any  # str or int; stringified for envelope source_position
    finality: Finality = Finality.UNKNOWN

    def __post_init__(self) -> None:
        if not isinstance(self.finality, Finality):
            raise TypeError("raw record finality must be Finality")


class InputSource(Protocol):
    """
    Protocol for passive/replay input adapters. Contract §4.
    """

    source_id: str
    source_kind: SourceKind

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
