"""Deterministic exact-observation fact extraction and pair construction."""

from __future__ import annotations

from dataclasses import dataclass, replace

from evidencegate.correlation.contracts import (
    EXACT_OBSERVATION_POLICY_VERSION,
    NORMALIZER_VERSION,
    CandidateStatus,
    CorrelationCandidate,
    CorrelationFactKind,
    CorrelationFactSeed,
    DerivationBasis,
    EventInterval,
    EventTimeBasis,
    EventTimeRelationship,
    IdentityBasis,
    MatchedFact,
    RelationPolicy,
    canonical_pair_id,
)
from evidencegate.domain.events import VisibilityProfile
from evidencegate.domain.quality import EvidenceQuality
from evidencegate.family.composer import FAMILY_BY_LANE
from evidencegate.results.types import Result


@dataclass(frozen=True, slots=True)
class RelationRulePolicy:
    policy: RelationPolicy
    enabled: bool
    window_seconds: int | None = None

    def __post_init__(self) -> None:
        if self.window_seconds is not None and self.window_seconds < 0:
            raise ValueError("relation windows must be non-negative or unset")
        if not self.enabled and self.window_seconds is not None:
            raise ValueError("disabled relation policies must not set a time window")


RELATION_POLICIES = {
    policy: RelationRulePolicy(policy, policy is RelationPolicy.EXACT_OBSERVATION)
    for policy in RelationPolicy
}


@dataclass(frozen=True, slots=True)
class ResultCorrelationContext:
    result_id: str
    source_result_hash: str
    lane_id: str
    event_interval: EventInterval
    visibility: VisibilityProfile
    quality: EvidenceQuality
    source_provenance: tuple[str, ...]


def _event_interval(result: Result) -> EventInterval:
    if result.evidence_interval is not None:
        start, end = result.evidence_interval
        basis = EventTimeBasis.EVIDENCE_INTERVAL
    else:
        start = end = result.created_time
        basis = EventTimeBasis.RESULT_EVENT_TIME
    return EventInterval(start, end, basis)


def context_for_result(result: Result, source_result_hash: str) -> ResultCorrelationContext:
    return ResultCorrelationContext(
        result_id=result.result_id,
        source_result_hash=source_result_hash,
        lane_id=result.lane_id,
        event_interval=_event_interval(result),
        visibility=result.visibility_snapshot,
        quality=result.quality_snapshot,
        source_provenance=result.provenance_refs,
    )


def exact_observation_facts(
    result: Result, source_result_hash: str
) -> tuple[CorrelationFactSeed, ...]:
    """Materialize only immutable, exact source-observation identity facts."""
    return tuple(
        exact_observation_fact(context_for_result(result, source_result_hash), observation_id)
        for observation_id in result.source_observation_ids
    )


def exact_observation_fact(
    context: ResultCorrelationContext, observation_id: str
) -> CorrelationFactSeed:
    return CorrelationFactSeed(
        fact_kind=CorrelationFactKind.EXACT_OBSERVATION,
        normalized_value=observation_id,
        namespace="evidencegate.source_observation",
        scope="source_observation_id",
        role="observed",
        identity_basis=IdentityBasis.EXACT_SOURCE_OBSERVATION_ID,
        event_interval=context.event_interval,
        available_time=None,
        source_result_id=context.result_id,
        source_result_hash=context.source_result_hash,
        source_observation_ids=(observation_id,),
        visibility_basis=context.visibility,
        quality_basis=context.quality,
        source_fields=("Result.source_observation_ids",),
        derivation_basis=DerivationBasis.SOURCE_OBSERVATION_ID,
        normalizer_version=NORMALIZER_VERSION,
    )


def _event_relationship(left: EventInterval, right: EventInterval) -> EventTimeRelationship:
    if left.end < right.start or right.end < left.start:
        return EventTimeRelationship.NON_OVERLAPPING_INTERVALS
    return EventTimeRelationship.OVERLAPPING_INTERVALS


def candidate_for_exact_observation(
    left: ResultCorrelationContext,
    right: ResultCorrelationContext,
    matched_facts: tuple[MatchedFact, ...],
) -> CorrelationCandidate | None:
    """Build a candidate only for distinct known families and exact shared facts."""
    if not matched_facts:
        return None
    left_family = FAMILY_BY_LANE.get(left.lane_id)
    right_family = FAMILY_BY_LANE.get(right.lane_id)
    if left_family is None or right_family is None or left_family == right_family:
        return None

    if left.result_id > right.result_id:
        left, right = right, left
        matched_facts = tuple(
            MatchedFact(
                reason=item.reason,
                fact_kind=item.fact_kind,
                normalized_value=item.normalized_value,
                left_fact_id=item.right_fact_id,
                right_fact_id=item.left_fact_id,
                source_observation_id=item.source_observation_id,
            )
            for item in matched_facts
        )

    facts = tuple(
        sorted(
            set(matched_facts),
            key=lambda item: (
                item.source_observation_id,
                item.left_fact_id,
                item.right_fact_id,
            ),
        )
    )
    matched_fact_ids = tuple(
        sorted({fact_id for item in facts for fact_id in (item.left_fact_id, item.right_fact_id)})
    )
    source_observation_ids = tuple(sorted({item.source_observation_id for item in facts}))
    return CorrelationCandidate(
        pair_id=canonical_pair_id(
            left.result_id, right.result_id, EXACT_OBSERVATION_POLICY_VERSION
        ),
        left_result_id=left.result_id,
        right_result_id=right.result_id,
        left_source_result_hash=left.source_result_hash,
        right_source_result_hash=right.source_result_hash,
        relation_policy=RelationPolicy.EXACT_OBSERVATION,
        relation_policy_version=EXACT_OBSERVATION_POLICY_VERSION,
        matched_facts=facts,
        matched_fact_ids=matched_fact_ids,
        source_observation_ids=source_observation_ids,
        left_event_interval=left.event_interval,
        right_event_interval=right.event_interval,
        event_time_relationship=_event_relationship(left.event_interval, right.event_interval),
        left_visibility=left.visibility,
        right_visibility=right.visibility,
        left_quality=left.quality,
        right_quality=right.quality,
        left_source_provenance=left.source_provenance,
        right_source_provenance=right.source_provenance,
        status=CandidateStatus.CANDIDATE_FOR_JOINT_REVIEW,
    )


def merge_candidates(
    existing: CorrelationCandidate, addition: CorrelationCandidate
) -> CorrelationCandidate:
    """Merge duplicate factual reasons deterministically without changing pair identity."""
    if (
        existing.pair_id != addition.pair_id
        or existing.left_result_id != addition.left_result_id
        or existing.right_result_id != addition.right_result_id
    ):
        raise ValueError("only reasons for the same canonical pair can be merged")
    facts = tuple(
        sorted(
            set(existing.matched_facts) | set(addition.matched_facts),
            key=lambda item: (
                item.source_observation_id,
                item.left_fact_id,
                item.right_fact_id,
            ),
        )
    )
    return replace(
        existing,
        matched_facts=facts,
        matched_fact_ids=tuple(
            sorted(
                {fact_id for item in facts for fact_id in (item.left_fact_id, item.right_fact_id)}
            )
        ),
        source_observation_ids=tuple(sorted({item.source_observation_id for item in facts})),
    )
