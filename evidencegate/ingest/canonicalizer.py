"""
ingest/canonicalizer.py — Pure, deterministic, side-effect-free canonicalization.

IC-15: Canonicalization must be pure and return observations plus control events
without side effects. It must not publish, enqueue, write SQLite, or depend on
logging. CanonicalizationResult contains typed tuples (not Sequences).

Presence rules:
  - present_fields: set of field names that were actually observed in the source
  - None: field was absent / not supplied in the source record
  - UNKNOWN: field exists in the envelope but its factual value is unknown
"""
from typing import Protocol
from dataclasses import dataclass, fields
from datetime import datetime

from evidencegate.ingest.source import RawSourceRecord, SourceManifest
from evidencegate.domain.events import NetworkObservation, RuntimeControlEvent, VisibilityProfile
from evidencegate.domain.payloads import FlowObservation
from evidencegate.domain.enums import AvailabilityBasis, Finality, ObservationType, VisibilityCapability
from evidencegate.ingest.builders import CanonicalObservationBuilder, identity_from_identifiers


@dataclass(frozen=True, slots=True)
class CanonicalizationResult:
    """
    Immutable result of canonicalization. Both fields are proper tuples
    (not Sequence) to satisfy IC-15 purity requirements.
    """
    observations: tuple[NetworkObservation, ...]
    control_events: tuple[RuntimeControlEvent, ...]


class Canonicalizer(Protocol):
    """
    Canonicalizer is factual, deterministic, and side-effect-free except for
    emitting parser/quality control events via the result tuple. It must not
    publish or write to DB directly (IC-15).
    """
    def canonicalize(
        self,
        record: RawSourceRecord,
        manifest: SourceManifest,
        quality_ref: str,
        ingest_time: datetime,
    ) -> CanonicalizationResult:
        ...


class FlowCanonicalizer:
    """
    Concrete canonicalizer for FlowObservation payloads.
    Deterministic: same record + manifest + quality_ref + ingest_time yields same output.
    Side-effect-free: no I/O, no logging calls, no queue writes.
    """

    def canonicalize(
        self,
        record: RawSourceRecord,
        manifest: SourceManifest,
        quality_ref: str,
        ingest_time: datetime,
    ) -> CanonicalizationResult:
        flow_obs: FlowObservation = record.raw_data

        # IC-04: A terminal flow's causal availability cannot precede its
        # export/final time. Take max(record_timestamp, export_time).
        causal_time = max(record.timestamp, flow_obs.export_time)

        unavailable_protocol_facts = frozenset({
            VisibilityCapability.PACKET_FACTS,
            VisibilityCapability.CLEAR_DNS_FIELDS,
            VisibilityCapability.TLS_HANDSHAKE_METADATA,
            VisibilityCapability.TLS_RECORD_METADATA,
            VisibilityCapability.QUIC_OUTER_METADATA,
        })
        present = (field.name for field in fields(flow_obs)
                   if getattr(flow_obs, field.name) is not None)
        envelope = CanonicalObservationBuilder().build(
            observation_type=ObservationType.FLOW, payload=flow_obs, record=record,
            manifest=manifest, quality_ref=quality_ref, ingest_time=ingest_time,
            declared_observed_fields=present, causal_available_time=causal_time,
            availability_basis=(AvailabilityBasis.FLOW_END_ONLY
                                if record.finality is Finality.TERMINAL
                                else AvailabilityBasis.IMMEDIATE),
            visibility=VisibilityProfile(
                available=frozenset({VisibilityCapability.FLOW_FACTS}),
                unavailable=unavailable_protocol_facts,
            ),
            identity=identity_from_identifiers(flow_obs.endpoints),
        )

        # Pure result: tuple of observations and tuple of control_events.
        # No side effects produced here.
        return CanonicalizationResult(
            observations=(envelope,),
            control_events=(),
        )
