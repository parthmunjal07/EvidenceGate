"""Immutable contracts for derived factual correlation records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
import hashlib

from evidencegate.domain.events import VisibilityProfile
from evidencegate.domain.quality import EvidenceQuality


class CorrelationFactKind(StrEnum):
    EXACT_OBSERVATION = "EXACT_OBSERVATION"
    SCOPED_ENTITY = "SCOPED_ENTITY"
    PEER = "PEER"
    DOMAIN = "DOMAIN"
    OBSERVED_DNS_ANSWER = "OBSERVED_DNS_ANSWER"
    SERVICE = "SERVICE"
    SESSION = "SESSION"
    TARGET_SERVICE = "TARGET_SERVICE"
    PROTOCOL_CONTEXT = "PROTOCOL_CONTEXT"


class IdentityBasis(StrEnum):
    EXACT_SOURCE_OBSERVATION_ID = "EXACT_SOURCE_OBSERVATION_ID"
    EXPLICIT_TYPED_IDENTITY = "EXPLICIT_TYPED_IDENTITY"


class EventTimeBasis(StrEnum):
    EVIDENCE_INTERVAL = "EVIDENCE_INTERVAL"
    RESULT_EVENT_TIME = "RESULT_EVENT_TIME"
    EXPLICIT_SOURCE_EVENT_TIME = "EXPLICIT_SOURCE_EVENT_TIME"


class DerivationBasis(StrEnum):
    SOURCE_OBSERVATION_ID = "SOURCE_OBSERVATION_ID"
    EXPLICIT_TYPED_SOURCE_FIELD = "EXPLICIT_TYPED_SOURCE_FIELD"


class RelationPolicy(StrEnum):
    EXACT_OBSERVATION = "EXACT_OBSERVATION"
    SCOPED_ENTITY = "SCOPED_ENTITY"
    PEER = "PEER"
    DOMAIN = "DOMAIN"
    OBSERVED_DNS_ANSWER = "OBSERVED_DNS_ANSWER"
    SERVICE = "SERVICE"
    SESSION = "SESSION"
    TARGET_SERVICE = "TARGET_SERVICE"
    DNS_ANSWER_TO_TLS_PEER = "DNS_ANSWER_TO_TLS_PEER"
    C2_TO_TRANSFER = "C2_TO_TRANSFER"
    RECON_TO_DEMAND = "RECON_TO_DEMAND"


class CandidateStatus(StrEnum):
    CANDIDATE_FOR_JOINT_REVIEW = "CANDIDATE_FOR_JOINT_REVIEW"


class EventTimeRelationship(StrEnum):
    OVERLAPPING_INTERVALS = "OVERLAPPING_INTERVALS"
    NON_OVERLAPPING_INTERVALS = "NON_OVERLAPPING_INTERVALS"
    EVENT_TIME_UNAVAILABLE = "EVENT_TIME_UNAVAILABLE"


class MatchedReason(StrEnum):
    EXACT_SHARED_SOURCE_OBSERVATION = "EXACT_SHARED_SOURCE_OBSERVATION"


class ClaimType(StrEnum):
    FACTUAL_RELATION = "FACTUAL_RELATION"
    MATCHED_FACTS = "MATCHED_FACTS"
    PROVENANCE = "PROVENANCE"
    EVENT_TIME_RELATIONSHIP = "EVENT_TIME_RELATIONSHIP"
    CANDIDATE_FOR_JOINT_REVIEW = "CANDIDATE_FOR_JOINT_REVIEW"
    CAUSALITY = "CAUSALITY"
    SAME_ATTACKER = "SAME_ATTACKER"
    SAME_CAMPAIGN = "SAME_CAMPAIGN"
    ATTACK_CHAIN_CONFIRMATION = "ATTACK_CHAIN_CONFIRMATION"
    COMPROMISE_INFERENCE = "COMPROMISE_INFERENCE"
    MALICIOUSNESS_PROBABILITY = "MALICIOUSNESS_PROBABILITY"


class ClaimLimit(StrEnum):
    NO_CAUSALITY = "NO_CAUSALITY"
    NO_COMMON_ATTACKER = "NO_COMMON_ATTACKER"
    NO_SAME_CAMPAIGN = "NO_SAME_CAMPAIGN"
    NO_ATTACK_CHAIN_CONFIRMATION = "NO_ATTACK_CHAIN_CONFIRMATION"
    NO_COMPROMISE_INFERENCE = "NO_COMPROMISE_INFERENCE"
    NO_MALICIOUSNESS_PROBABILITY = "NO_MALICIOUSNESS_PROBABILITY"


ALLOWED_CLAIMS = (
    ClaimType.FACTUAL_RELATION,
    ClaimType.MATCHED_FACTS,
    ClaimType.PROVENANCE,
    ClaimType.EVENT_TIME_RELATIONSHIP,
    ClaimType.CANDIDATE_FOR_JOINT_REVIEW,
)

PROHIBITED_CLAIMS = (
    ClaimLimit.NO_CAUSALITY,
    ClaimLimit.NO_COMMON_ATTACKER,
    ClaimLimit.NO_SAME_CAMPAIGN,
    ClaimLimit.NO_ATTACK_CHAIN_CONFIRMATION,
    ClaimLimit.NO_COMPROMISE_INFERENCE,
    ClaimLimit.NO_MALICIOUSNESS_PROBABILITY,
)

FACT_DERIVATION_VERSION = "corr-04a-fact-v1"
NORMALIZER_VERSION = "exact-observation-v1"
EXACT_OBSERVATION_POLICY_VERSION = "corr-04a-exact-observation-v1"


@dataclass(frozen=True, slots=True)
class EventInterval:
    start: datetime
    end: datetime
    basis: EventTimeBasis

    def __post_init__(self) -> None:
        for value in (self.start, self.end):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("event interval datetimes must be timezone-aware")
        if self.end < self.start:
            raise ValueError("event interval end must not precede start")


@dataclass(frozen=True, slots=True)
class CorrelationFactSeed:
    """One observed/supplied typed value with provenance and time context."""

    fact_kind: CorrelationFactKind
    normalized_value: str
    namespace: str
    scope: str
    role: str
    identity_basis: IdentityBasis
    event_interval: EventInterval
    available_time: datetime | None
    source_result_id: str
    source_result_hash: str
    source_observation_ids: tuple[str, ...]
    visibility_basis: VisibilityProfile
    quality_basis: EvidenceQuality
    source_fields: tuple[str, ...]
    derivation_basis: DerivationBasis
    normalizer_version: str
    derivation_version: str = FACT_DERIVATION_VERSION

    def __post_init__(self) -> None:
        for name, value in (
            ("normalized_value", self.normalized_value),
            ("namespace", self.namespace),
            ("scope", self.scope),
            ("role", self.role),
            ("source_result_id", self.source_result_id),
            ("source_result_hash", self.source_result_hash),
            ("normalizer_version", self.normalizer_version),
            ("derivation_version", self.derivation_version),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if self.available_time is not None and (
            self.available_time.tzinfo is None or self.available_time.utcoffset() is None
        ):
            raise ValueError("available_time must be timezone-aware")
        if not self.source_observation_ids:
            raise ValueError("a correlation fact requires source observation provenance")
        if not self.source_fields:
            raise ValueError("a correlation fact requires source field provenance")
        if self.fact_kind is CorrelationFactKind.SCOPED_ENTITY:
            if self.identity_basis is not IdentityBasis.EXPLICIT_TYPED_IDENTITY:
                raise ValueError("SCOPED_ENTITY requires an explicit typed identity basis")
        if self.fact_kind is CorrelationFactKind.EXACT_OBSERVATION:
            if self.identity_basis is not IdentityBasis.EXACT_SOURCE_OBSERVATION_ID:
                raise ValueError("EXACT_OBSERVATION requires exact source-observation identity")
            if self.normalized_value not in self.source_observation_ids:
                raise ValueError("EXACT_OBSERVATION value must retain its source observation")

    @property
    def fact_id(self) -> str:
        seed = "\0".join(
            (
                self.source_result_id,
                self.source_result_hash,
                self.derivation_version,
                self.fact_kind.value,
                self.namespace,
                self.scope,
                self.role,
                self.normalized_value,
            )
        )
        return "fact:" + hashlib.sha256(seed.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class MatchedFact:
    reason: MatchedReason
    fact_kind: CorrelationFactKind
    normalized_value: str
    left_fact_id: str
    right_fact_id: str
    source_observation_id: str


@dataclass(frozen=True, slots=True)
class ClaimGuard:
    allowed: tuple[ClaimType, ...] = ALLOWED_CLAIMS
    prohibited: tuple[ClaimLimit, ...] = PROHIBITED_CLAIMS

    def __post_init__(self) -> None:
        if self.allowed != ALLOWED_CLAIMS or self.prohibited != PROHIBITED_CLAIMS:
            raise ValueError("correlation claim guard must preserve the fixed scientific boundary")


def validate_claim(claim: ClaimType) -> None:
    """Reject prohibited or untyped persisted correlation claims."""
    if not isinstance(claim, ClaimType):
        raise TypeError("correlation claims must use ClaimType")
    if claim not in ALLOWED_CLAIMS:
        raise ValueError(f"correlation claim is prohibited: {claim.value}")


@dataclass(frozen=True, slots=True)
class CorrelationCandidate:
    """A precise derived relation between two immutable Result IDs."""

    pair_id: str
    left_result_id: str
    right_result_id: str
    left_source_result_hash: str
    right_source_result_hash: str
    relation_policy: RelationPolicy
    relation_policy_version: str
    matched_facts: tuple[MatchedFact, ...]
    matched_fact_ids: tuple[str, ...]
    source_observation_ids: tuple[str, ...]
    left_event_interval: EventInterval
    right_event_interval: EventInterval
    event_time_relationship: EventTimeRelationship
    left_visibility: VisibilityProfile
    right_visibility: VisibilityProfile
    left_quality: EvidenceQuality
    right_quality: EvidenceQuality
    left_source_provenance: tuple[str, ...]
    right_source_provenance: tuple[str, ...]
    status: CandidateStatus = CandidateStatus.CANDIDATE_FOR_JOINT_REVIEW
    claim_guard: ClaimGuard = ClaimGuard()

    def __post_init__(self) -> None:
        if self.left_result_id >= self.right_result_id:
            raise ValueError("pair orientation must be canonical by Result ID")
        if self.pair_id != canonical_pair_id(
            self.left_result_id, self.right_result_id, self.relation_policy_version
        ):
            raise ValueError("pair_id must be the canonical identity for this Result pair")
        if self.relation_policy is not RelationPolicy.EXACT_OBSERVATION:
            raise ValueError("only the exact-observation relation is enabled")
        if self.relation_policy_version != EXACT_OBSERVATION_POLICY_VERSION:
            raise ValueError("exact-observation candidate has an unsupported policy version")
        if not self.matched_facts:
            raise ValueError("a candidate requires at least one matched factual reason")
        if tuple(sorted(set(self.matched_fact_ids))) != self.matched_fact_ids:
            raise ValueError("matched_fact_ids must be unique and sorted")
        if tuple(sorted(set(self.source_observation_ids))) != self.source_observation_ids:
            raise ValueError("source_observation_ids must be unique and sorted")
        if self.claim_guard != ClaimGuard():
            raise ValueError("candidate must carry the fixed correlation claim guard")
        if self.status is not CandidateStatus.CANDIDATE_FOR_JOINT_REVIEW:
            raise ValueError("correlation candidates must remain joint-review candidates")


def canonical_pair_id(left_result_id: str, right_result_id: str, policy_version: str) -> str:
    left, right = sorted((left_result_id, right_result_id))
    seed = "\0".join((left, right, policy_version))
    return "candidate:" + hashlib.sha256(seed.encode("utf-8")).hexdigest()


def utc_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("correlation datetimes must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")
