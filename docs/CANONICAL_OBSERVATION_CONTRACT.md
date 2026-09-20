# Canonical Observation Contract

This document defines the executable `NetworkObservationEnvelope` contract. It is factual sensor metadata, not a threat interpretation.

## Time

- `event_time` is the source-declared time of the represented network event.
- `causal_available_time` is the earliest time that fact could be available to a streaming detector. It cannot precede `event_time`; terminal flow exports cannot precede their export time.
- `ingest_time` is the runtime-supplied time at which the canonical observation enters EvidenceGate. Pure canonicalizers receive it explicitly and never read a clock or copy event time implicitly.

All three timestamps are timezone-aware.

## Source and observation contract

- `source_kind` is a typed `SourceKind`; it identifies the adapter family and does not imply completeness, sampling, or quality.
- `source_position` is the source cursor used for replay identity and provenance.
- `observation_contract` is an explicit versioned identifier for the record semantics. Observation type alone is insufficient.
- `availability_basis` and `finality` are typed declarations. Unknown finality remains `Finality.UNKNOWN`, never `False`.

## Direction

- `wire_direction` is `FORWARD`, `REVERSE`, or `UNKNOWN`.
- `direction_basis` states why that label is meaningful: source record order, capture interface, flow exporter, explicit client/server role, local/external policy, or unknown.
- A known direction with an unknown basis is invalid. Forward/reverse labels never imply client/server, internal/external, attacker/victim, or any other role.
- The envelope owns canonical wire direction. Protocol payloads do not carry a second canonical direction.

## Presence

`present_fields` is an immutable set and is authoritative for source-observed payload fields. `None` means absent/not supplied and cannot be marked present. The literal `UNKNOWN` may be present when the source represented a fact but could not establish its value. Missing fields are never converted to zero, false, or benign evidence.

## Visibility

`VisibilityProfile` records typed capabilities as `AVAILABLE`, `UNAVAILABLE`, `DEGRADED`, or (when omitted) `UNKNOWN`. It distinguishes forward facts, reverse facts, packet facts, flow facts, clear DNS fields, TLS handshake metadata, TLS record metadata, and QUIC outer metadata. It is not a scalar score. One-way observations are valid; an unavailable reverse direction is absence of capability, not a zero-valued reverse observation.

## Quality

`EvidenceQuality` records factual states for packet loss, sampling, parser condition, and capture gaps. `UNKNOWN` is the safe default. `quality_ref` remains provenance for those declarations and is not itself proof of visibility or quality. Runtime queue gaps remain in the M2 gap lifecycle and are not duplicated here.

## Identity

`ObservationIdentity` separates observed endpoint identifiers from optional role assignments. Address presence does not create roles. Roles are represented only when a trusted source or policy explicitly supplies both a role and its basis.

## Validation and admission

Envelope construction rejects naive timestamps, contradictory direction/basis, type mismatches, causal time before event time, payload/type mismatch, impossible present-field names, and present fields whose value is `None`. Plugin admission evaluates typed visibility capabilities and typed quality requirements; it does not use `quality_ref` as a proxy. Routing remains observation-type candidate routing.
