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
from dataclasses import dataclass
from datetime import datetime

from evidencegate.ingest.source import RawSourceRecord, SourceManifest
from evidencegate.domain.events import NetworkObservation, RuntimeControlEvent
from evidencegate.domain.payloads import FlowObservation
from evidencegate.domain.enums import (
    AvailabilityBasis, Finality, ObservationType, VisibilityCapability,
    WireDirection,
)


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

        # Build the present_fields set from what the FlowObservation actually has.
        present: set[str] = set()
        if flow_obs.flow_id_basis is not None:
            present.add("flow_id_basis")
        if flow_obs.endpoints is not None:
            present.add("endpoints")
        if flow_obs.protocol is not None:
            present.add("protocol")
        if flow_obs.supplied_directional_counters is not None:
            present.add("supplied_directional_counters")
        if flow_obs.start_time is not None:
            present.add("start_time")
        if flow_obs.end_time is not None:
            present.add("end_time")
        if flow_obs.export_time is not None:
            present.add("export_time")
        if flow_obs.exporter_semantics is not None:
            present.add("exporter_semantics")
        if flow_obs.sampling is not None:
            present.add("sampling")
        if flow_obs.documented_end_state is not None:
            present.add("documented_end_state")

        # Observation ID is a stable derivation from source position so that
        # re-processing the same source record yields the same ID (deterministic).
        obs_id = f"flow:{manifest.source_id}:{record.position}"

        unavailable_protocol_facts = frozenset({
            VisibilityCapability.PACKET_FACTS,
            VisibilityCapability.CLEAR_DNS_FIELDS,
            VisibilityCapability.TLS_HANDSHAKE_METADATA,
            VisibilityCapability.TLS_RECORD_METADATA,
            VisibilityCapability.QUIC_OUTER_METADATA,
        })
        directional_facts = {
            WireDirection.FORWARD: frozenset({VisibilityCapability.FORWARD_FACTS}),
            WireDirection.REVERSE: frozenset({VisibilityCapability.REVERSE_FACTS}),
            WireDirection.UNKNOWN: frozenset(),
        }[manifest.wire_direction]
        visibility = manifest.visibility.with_facts(
            available=frozenset({VisibilityCapability.FLOW_FACTS}) | directional_facts,
            unavailable=unavailable_protocol_facts,
        )

        envelope = NetworkObservation(
            observation_id=obs_id,
            schema_version="1.1",
            observation_type=ObservationType.FLOW,
            event_time=record.timestamp,
            causal_available_time=causal_time,
            ingest_time=ingest_time,
            source_id=manifest.source_id,
            source_kind=manifest.source_kind,
            source_position=str(record.position),
            observation_contract=manifest.input_observation_contract,
            wire_direction=manifest.wire_direction,
            direction_basis=manifest.direction_basis,
            finality=record.finality,
            availability_basis=(AvailabilityBasis.FLOW_END_ONLY
                                if record.finality is Finality.TERMINAL
                                else AvailabilityBasis.IMMEDIATE),
            provenance_ref=f"prov:{manifest.source_id}:{record.position}",
            quality_ref=quality_ref,
            present_fields=frozenset(present),
            typed_payload=flow_obs,
            visibility=visibility,
            quality=manifest.quality,
        )

        # Pure result: tuple of observations and tuple of control_events.
        # No side effects produced here.
        return CanonicalizationResult(
            observations=(envelope,),
            control_events=(),
        )
