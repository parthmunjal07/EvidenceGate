from dataclasses import dataclass
from typing import Sequence
from datetime import datetime

@dataclass(frozen=True, slots=True)
class QualityGap:
    """
    QualityGap is an immutable interval with source/lane scope, first/last known 
    event time, count, types, reason, and detection time. It is emitted for 
    observed upstream loss, router/lane loss, parser failures that invalidate 
    facts, and declared capture gaps.
    """
    gap_id: str
    scope: str # source_id or lane_id
    first_known_event_time: datetime
    last_known_event_time: datetime
    detection_time: datetime
    count: int
    gap_types: tuple[str, ...]
    reason: str
