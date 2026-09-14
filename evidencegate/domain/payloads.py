from dataclasses import dataclass
from typing import Any, Optional, Sequence
from datetime import datetime
from evidencegate.domain.enums import ObservationType, ControlType

@dataclass(frozen=True, slots=True)
class PacketObservation:
    lengths: dict[str, int]
    observed_l2_facts: dict[str, Any]
    observed_l3_facts: dict[str, Any]
    observed_l4_facts: dict[str, Any]
    src_address: Optional[str]
    dst_address: Optional[str]
    src_port: Optional[int]
    dst_port: Optional[int]
    flags: Optional[list[str]]
    sequence_facts: Optional[dict[str, Any]]
    fragmentation: Optional[dict[str, Any]]
    raw_reference: Optional[str]

@dataclass(frozen=True, slots=True)
class FlowObservation:
    flow_id_basis: str
    endpoints: tuple[str, str]
    protocol: int
    start_time: datetime
    end_time: datetime
    export_time: datetime
    supplied_directional_counters: dict[str, int]
    finality: bool
    exporter_semantics: str
    sampling: Optional[dict[str, Any]]
    documented_end_state: Optional[str]

@dataclass(frozen=True, slots=True)
class DNSObservation:
    flow_reference: str
    observed_direction: str
    qr_state_decoded: bool
    transaction_id: int
    qname: Optional[str]
    qtype: Optional[str]
    qclass: Optional[str]
    rcode: Optional[str]
    answers: Optional[list[Any]]
    transport: str
    truncation: bool
    clear_dns_visibility: bool

@dataclass(frozen=True, slots=True)
class TLSObservation:
    flow_reference: str
    observed_direction: str
    tcp_reassembly_state: str
    parser_version: str
    parsed_handshake_metadata: Optional[dict[str, Any]]
    parsed_record_metadata: Optional[dict[str, Any]]
    indexes: Optional[dict[str, int]]
    prefix_time: Optional[datetime]
    gaps: Optional[list[str]]

@dataclass(frozen=True, slots=True)
class QUICObservation:
    flow_reference: str
    direction: str
    version: str
    header_type: str
    length: int
    visible_connection_ids: list[str]
    parser_version: str
    index: int
    timing: datetime
    visibility_flags: list[str]

# The union of payload types for convenience in typing, though usually NetworkObservationEnvelope wraps these
NetworkPayloadType = PacketObservation | FlowObservation | DNSObservation | TLSObservation | QUICObservation
