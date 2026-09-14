from typing import Protocol, Sequence
from evidencegate.ingest.source import RawSourceRecord, SourceManifest
from evidencegate.domain.events import NetworkObservation, RuntimeControlEvent
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class CanonicalizationResult:
    observations: Sequence[NetworkObservation]
    control_events: Sequence[RuntimeControlEvent]

class Canonicalizer(Protocol):
    """
    Canonicalizer is factual, deterministic, and side-effect-free except for 
    emitting parser/quality control events via the result. It must not publish
    or write to DB directly.
    """
    def canonicalize(self, record: RawSourceRecord, manifest: SourceManifest, quality_ref: str) -> CanonicalizationResult: ...
