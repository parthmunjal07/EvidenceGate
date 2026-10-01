"""Canonical SQLite encoding for typed correlation contracts."""

from __future__ import annotations

import json
from datetime import datetime

from evidencegate.correlation.contracts import (
    CandidateStatus,
    ClaimGuard,
    ClaimLimit,
    ClaimType,
    CorrelationCandidate,
    CorrelationFactKind,
    CorrelationFactSeed,
    DerivationBasis,
    EventInterval,
    EventTimeBasis,
    EventTimeRelationship,
    IdentityBasis,
    MatchedFact,
    MatchedReason,
    RelationPolicy,
    utc_text,
)
from evidencegate.domain.enums import QualityState, VisibilityCapability
from evidencegate.domain.events import VisibilityProfile
from evidencegate.domain.quality import EvidenceQuality


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def visibility_from_json(value: str) -> VisibilityProfile:
    data = json.loads(value)
    return VisibilityProfile(
        available=frozenset(VisibilityCapability(item) for item in data.get("available", ())),
        unavailable=frozenset(VisibilityCapability(item) for item in data.get("unavailable", ())),
        degraded=frozenset(VisibilityCapability(item) for item in data.get("degraded", ())),
    )


def quality_from_json(value: str) -> EvidenceQuality:
    data = json.loads(value)
    return EvidenceQuality(
        packet_loss=QualityState(data["packet_loss"]),
        sampling=QualityState(data["sampling"]),
        parser=QualityState(data["parser"]),
        capture_gap=QualityState(data["capture_gap"]),
    )


def event_interval_from_values(start: str, end: str, basis: str) -> EventInterval:
    return EventInterval(
        datetime.fromisoformat(start), datetime.fromisoformat(end), EventTimeBasis(basis)
    )


def fact_values(fact: CorrelationFactSeed) -> tuple[object, ...]:
    return (
        fact.fact_id,
        fact.source_result_id,
        fact.source_result_hash,
        fact.fact_kind.value,
        fact.normalized_value,
        fact.namespace,
        fact.scope,
        fact.role,
        fact.identity_basis.value,
        utc_text(fact.event_interval.start),
        utc_text(fact.event_interval.end),
        fact.event_interval.basis.value,
        utc_text(fact.available_time) if fact.available_time else None,
        canonical_json(fact.source_observation_ids),
        canonical_json(
            {
                "available": sorted(item.value for item in fact.visibility_basis.available),
                "unavailable": sorted(item.value for item in fact.visibility_basis.unavailable),
                "degraded": sorted(item.value for item in fact.visibility_basis.degraded),
            }
        ),
        canonical_json(
            {
                "packet_loss": fact.quality_basis.packet_loss.value,
                "sampling": fact.quality_basis.sampling.value,
                "parser": fact.quality_basis.parser.value,
                "capture_gap": fact.quality_basis.capture_gap.value,
            }
        ),
        canonical_json(fact.source_fields),
        fact.derivation_basis.value,
        fact.normalizer_version,
        fact.derivation_version,
    )


def fact_from_row(values: dict[str, object]) -> CorrelationFactSeed:
    return CorrelationFactSeed(
        fact_kind=CorrelationFactKind(str(values["fact_kind"])),
        normalized_value=str(values["normalized_value"]),
        namespace=str(values["namespace"]),
        scope=str(values["scope"]),
        role=str(values["role"]),
        identity_basis=IdentityBasis(str(values["identity_basis"])),
        event_interval=event_interval_from_values(
            str(values["event_interval_start"]),
            str(values["event_interval_end"]),
            str(values["event_time_basis"]),
        ),
        available_time=(
            datetime.fromisoformat(str(values["available_time"]))
            if values["available_time"]
            else None
        ),
        source_result_id=str(values["source_result_id"]),
        source_result_hash=str(values["source_result_hash"]),
        source_observation_ids=tuple(json.loads(str(values["source_observation_ids"]))),
        visibility_basis=visibility_from_json(str(values["visibility_basis"])),
        quality_basis=quality_from_json(str(values["quality_basis"])),
        source_fields=tuple(json.loads(str(values["source_fields"]))),
        derivation_basis=DerivationBasis(str(values["derivation_basis"])),
        normalizer_version=str(values["normalizer_version"]),
        derivation_version=str(values["derivation_version"]),
    )


def _matched_fact_value(fact: MatchedFact) -> dict[str, str]:
    return {
        "reason": fact.reason.value,
        "fact_kind": fact.fact_kind.value,
        "normalized_value": fact.normalized_value,
        "left_fact_id": fact.left_fact_id,
        "right_fact_id": fact.right_fact_id,
        "source_observation_id": fact.source_observation_id,
    }


def _matched_fact_from_value(value: dict[str, str]) -> MatchedFact:
    return MatchedFact(
        reason=MatchedReason(value["reason"]),
        fact_kind=CorrelationFactKind(value["fact_kind"]),
        normalized_value=value["normalized_value"],
        left_fact_id=value["left_fact_id"],
        right_fact_id=value["right_fact_id"],
        source_observation_id=value["source_observation_id"],
    )


def candidate_values(candidate: CorrelationCandidate) -> tuple[object, ...]:
    return (
        candidate.pair_id,
        candidate.left_result_id,
        candidate.right_result_id,
        candidate.left_source_result_hash,
        candidate.right_source_result_hash,
        candidate.relation_policy.value,
        candidate.relation_policy_version,
        canonical_json([_matched_fact_value(item) for item in candidate.matched_facts]),
        canonical_json(candidate.matched_fact_ids),
        canonical_json(candidate.source_observation_ids),
        utc_text(candidate.left_event_interval.start),
        utc_text(candidate.left_event_interval.end),
        candidate.left_event_interval.basis.value,
        utc_text(candidate.right_event_interval.start),
        utc_text(candidate.right_event_interval.end),
        candidate.right_event_interval.basis.value,
        candidate.event_time_relationship.value,
        canonical_json(
            {
                "available": sorted(item.value for item in candidate.left_visibility.available),
                "unavailable": sorted(item.value for item in candidate.left_visibility.unavailable),
                "degraded": sorted(item.value for item in candidate.left_visibility.degraded),
            }
        ),
        canonical_json(
            {
                "available": sorted(item.value for item in candidate.right_visibility.available),
                "unavailable": sorted(
                    item.value for item in candidate.right_visibility.unavailable
                ),
                "degraded": sorted(item.value for item in candidate.right_visibility.degraded),
            }
        ),
        canonical_json(
            {
                "packet_loss": candidate.left_quality.packet_loss.value,
                "sampling": candidate.left_quality.sampling.value,
                "parser": candidate.left_quality.parser.value,
                "capture_gap": candidate.left_quality.capture_gap.value,
            }
        ),
        canonical_json(
            {
                "packet_loss": candidate.right_quality.packet_loss.value,
                "sampling": candidate.right_quality.sampling.value,
                "parser": candidate.right_quality.parser.value,
                "capture_gap": candidate.right_quality.capture_gap.value,
            }
        ),
        canonical_json(candidate.left_source_provenance),
        canonical_json(candidate.right_source_provenance),
        candidate.status.value,
        canonical_json(
            {
                "allowed": [item.value for item in candidate.claim_guard.allowed],
                "prohibited": [item.value for item in candidate.claim_guard.prohibited],
            }
        ),
    )


def candidate_from_row(values: dict[str, object]) -> CorrelationCandidate:
    guard = json.loads(str(values["claim_guard"]))
    return CorrelationCandidate(
        pair_id=str(values["pair_id"]),
        left_result_id=str(values["left_result_id"]),
        right_result_id=str(values["right_result_id"]),
        left_source_result_hash=str(values["left_source_result_hash"]),
        right_source_result_hash=str(values["right_source_result_hash"]),
        relation_policy=RelationPolicy(str(values["relation_policy"])),
        relation_policy_version=str(values["relation_policy_version"]),
        matched_facts=tuple(
            _matched_fact_from_value(item) for item in json.loads(str(values["matched_reasons"]))
        ),
        matched_fact_ids=tuple(json.loads(str(values["matched_fact_ids"]))),
        source_observation_ids=tuple(json.loads(str(values["source_observation_ids"]))),
        left_event_interval=event_interval_from_values(
            str(values["left_event_interval_start"]),
            str(values["left_event_interval_end"]),
            str(values["left_event_time_basis"]),
        ),
        right_event_interval=event_interval_from_values(
            str(values["right_event_interval_start"]),
            str(values["right_event_interval_end"]),
            str(values["right_event_time_basis"]),
        ),
        event_time_relationship=EventTimeRelationship(str(values["event_time_relationship"])),
        left_visibility=visibility_from_json(str(values["left_visibility"])),
        right_visibility=visibility_from_json(str(values["right_visibility"])),
        left_quality=quality_from_json(str(values["left_quality"])),
        right_quality=quality_from_json(str(values["right_quality"])),
        left_source_provenance=tuple(json.loads(str(values["left_source_provenance"]))),
        right_source_provenance=tuple(json.loads(str(values["right_source_provenance"]))),
        status=CandidateStatus(str(values["status"])),
        claim_guard=ClaimGuard(
            tuple(ClaimType(item) for item in guard["allowed"]),
            tuple(ClaimLimit(item) for item in guard["prohibited"]),
        ),
    )
