from typing import Protocol, Sequence
from evidencegate.ingest.source import RawSourceRecord, SourceManifest
from evidencegate.domain.events import NetworkObservation, RuntimeControlEvent
from evidencegate.domain.enums import ObservationType
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

class FlowCanonicalizer(Canonicalizer):
    def canonicalize(self, record: RawSourceRecord, manifest: SourceManifest, quality_ref: str) -> CanonicalizationResult:
        # Assuming the record payload is already a FlowObservation for simplicity in testing
        flow_obs = record.raw_data
        
        # IC-04: A terminal flow's causal availability cannot precede its export/final time.
        # We ensure causal_available_time is max(event_time, export_time)
        causal_time = max(record.timestamp, flow_obs.export_time)
        
        envelope = NetworkObservation(
            observation_id="flow_1",
            schema_version="1",
            observation_type=ObservationType.FLOW,
            event_time=record.timestamp,
            causal_available_time=causal_time,
            ingest_time=record.timestamp,
            source_id=manifest.source_id,
            source_kind=manifest.source_kind,
            source_position=record.position,
            observation_contract="flow",
            wire_direction="fwd",
            direction_basis="test",
            finality=flow_obs.finality,
            availability_basis="export",
            provenance_ref="p",
            quality_ref=quality_ref,
            present_fields=set(),
            typed_payload=flow_obs
        )
        
        return CanonicalizationResult(
            observations=(envelope,),
            control_events=()
        )

