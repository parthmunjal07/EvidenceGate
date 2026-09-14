from dataclasses import dataclass
from typing import Any, Optional, Set
from datetime import datetime
from evidencegate.domain.enums import ObservationType, ControlType
from evidencegate.domain.payloads import NetworkPayloadType

@dataclass(frozen=True, slots=True)
class NetworkObservationEnvelope:
    observation_id: str
    schema_version: str
    observation_type: ObservationType
    event_time: datetime
    causal_available_time: datetime
    ingest_time: datetime
    source_id: str
    source_kind: str
    source_position: str
    observation_contract: str
    wire_direction: str
    direction_basis: str
    finality: bool
    availability_basis: str
    provenance_ref: str
    quality_ref: str
    present_fields: Set[str]
    typed_payload: NetworkPayloadType

@dataclass(frozen=True, slots=True)
class RuntimeControlEvent:
    control_event_id: str
    schema_version: str
    control_type: ControlType
    ingest_time: datetime
    typed_payload: Any
    event_time: Optional[datetime] = None
    source_id: Optional[str] = None
    lane_id: Optional[str] = None
    provenance_ref: Optional[str] = None
    quality_ref: Optional[str] = None

# Unions
NetworkObservation = NetworkObservationEnvelope
CanonicalEvent = NetworkObservation | RuntimeControlEvent
