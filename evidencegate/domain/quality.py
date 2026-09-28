from dataclasses import dataclass
from datetime import datetime
from evidencegate.domain.enums import QualityFact, QualityState


@dataclass(frozen=True, slots=True)
class QualityRequirement:
    fact: QualityFact
    allowed_states: frozenset[QualityState]

    def __post_init__(self) -> None:
        if not isinstance(self.fact, QualityFact):
            raise TypeError("quality requirement fact must be QualityFact")
        if not self.allowed_states or any(
            not isinstance(state, QualityState) for state in self.allowed_states
        ):
            raise TypeError("allowed_states must be a non-empty frozenset[QualityState]")


@dataclass(frozen=True, slots=True)
class EvidenceQuality:
    """Factual source/capture quality. Runtime queue gaps remain separate."""

    packet_loss: QualityState = QualityState.UNKNOWN
    sampling: QualityState = QualityState.UNKNOWN
    parser: QualityState = QualityState.UNKNOWN
    capture_gap: QualityState = QualityState.UNKNOWN

    def __post_init__(self) -> None:
        if any(
            not isinstance(state, QualityState)
            for state in (self.packet_loss, self.sampling, self.parser, self.capture_gap)
        ):
            raise TypeError("quality facts must use QualityState")

    def state(self, fact: QualityFact) -> QualityState:
        return {
            QualityFact.PACKET_LOSS: self.packet_loss,
            QualityFact.SAMPLING: self.sampling,
            QualityFact.PARSER: self.parser,
            QualityFact.CAPTURE_GAP: self.capture_gap,
        }[fact]


@dataclass(frozen=True, slots=True)
class QualityGap:
    """
    QualityGap is an immutable interval with source/lane scope, first/last known
    event time, count, types, reason, and detection time. It is emitted for
    observed upstream loss, router/lane loss, parser failures that invalidate
    facts, and declared capture gaps.
    """

    gap_id: str
    scope: str  # source_id or lane_id
    first_known_event_time: datetime
    last_known_event_time: datetime
    detection_time: datetime
    count: int
    gap_types: tuple[str, ...]
    reason: str
