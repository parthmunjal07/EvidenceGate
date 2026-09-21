from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Protocol, Sequence, Any, Optional
from evidencegate.registry.manifest import PluginManifest
from evidencegate.domain.events import NetworkObservation
from evidencegate.domain.quality import QualityGap
from evidencegate.results.types import ResultDraft
from evidencegate.runtime.state_contract import StateKey, StateOperation
from evidencegate.admission.evaluator import EvaluationReadinessDecision

if TYPE_CHECKING:
    from evidencegate.runtime.state import StateEntry


@dataclass(frozen=True, slots=True)
class PluginStateSnapshot:
    """Defensive, versioned state exposed to one plugin invocation."""

    key: StateKey
    payload: Any
    version: int
    expires_at: datetime

    @classmethod
    def from_entry(cls, entry: "StateEntry") -> "PluginStateSnapshot":
        return cls(
            key=StateKey(entry.key),
            payload=deepcopy(entry.payload),
            version=entry.version,
            expires_at=entry.expires_at,
        )


@dataclass(frozen=True, slots=True)
class StateTransitionRequest:
    """One declarative state change requested by a plugin."""

    key: StateKey
    expected_version: int | None
    operation: StateOperation
    payload: Any = None
    ttl: timedelta | None = None


@dataclass(frozen=True, slots=True)
class PluginProcessOutcome:
    """Results and the optional single state transition from an invocation."""

    result_drafts: tuple[ResultDraft, ...] = ()
    state_transition: StateTransitionRequest | None = None
    # Stateful invocations must explicitly supply this mechanism decision.
    evaluation_readiness: EvaluationReadinessDecision | None = None

class AnalyticPlugin(Protocol):
    def manifest(self) -> PluginManifest: ...
    
    def route(self, observation: NetworkObservation) -> bool: ...
    
    def state_key(self, observation: NetworkObservation) -> Optional[StateKey]: ...
    
    async def process(
        self,
        observation: NetworkObservation,
        context: Any,
        state: PluginStateSnapshot | None,
    ) -> PluginProcessOutcome: ...
    
    async def on_quality_gap(self, gap: QualityGap, context: Any, state: Any) -> Sequence[ResultDraft]: ...
    
    async def on_watermark(self, watermark: datetime, context: Any) -> PluginProcessOutcome: ...

    async def on_expire(
        self, key: StateKey, context: Any, state: PluginStateSnapshot
    ) -> PluginProcessOutcome: ...
