from dataclasses import dataclass
from typing import Any, Optional
from datetime import datetime

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
    # Canonical IP protocol number.  This optional tail field preserves every
    # existing positional constructor while allowing mechanisms to require a
    # factually declared protocol instead of guessing from ports or flags.
    protocol: Optional[int] = None

@dataclass(frozen=True, slots=True)
class FlowObservation:
    """Endpoints preserve source ordering only; tuple position assigns no role."""
    flow_id_basis: str
    endpoints: tuple[str, str]
    protocol: int
    start_time: datetime
    end_time: datetime
    export_time: datetime
    supplied_directional_counters: dict[str, int]
    exporter_semantics: str
    sampling: Optional[dict[str, Any]]
    documented_end_state: Optional[str]

@dataclass(frozen=True, slots=True)
class DNSObservation:
    flow_reference: str
    qr_state_decoded: bool
    transaction_id: int
    qname: Optional[str]
    qtype: Optional[str]
    qclass: Optional[str]
    rcode: Optional[str]
    answers: Optional[list[Any]]
    transport: str
    truncation: bool
    # Parser/source facts and shared DNS_NAME_REPRESENTATION_V1 derivations.
    # These are tail defaults so existing positional adapters remain compatible.
    raw_qname_ref: Optional[str] = None
    qname_rendered: Optional[str] = None
    qname_canonical: Optional[str] = None
    labels: Optional[tuple[str, ...]] = None
    parser_version: Optional[str] = None
    parser_status: Optional[str] = None
    message_length: Optional[int] = None
    representation_version: Optional[str] = None
    registrable_domain_ref: Optional[str] = None
    canonicalization_failure_reason: Optional[str] = None

@dataclass(frozen=True, slots=True)
class TLSObservation:
    flow_reference: str
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
