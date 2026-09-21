"""Category-2 C2 provider shell and C2-R1 factual recurrence measurement."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from statistics import median
from typing import Any, Sequence

from evidencegate.admission.evaluator import EvaluationReadinessDecision
from evidencegate.domain.enums import (
    AnalyticFamily, AvailabilityBasis, EvidenceReadiness, Finality, GapAction,
    IntegrationStatus, ObservationType, OfficialPsCategory, ResultType,
    VisibilityCapability,
)
from evidencegate.domain.events import NetworkObservation
from evidencegate.domain.quality import QualityGap
from evidencegate.registry.manifest import PluginManifest, StateResourcePolicy
from evidencegate.registry.plugin import (
    PluginProcessOutcome, PluginStateSnapshot, StateKey, StateTransitionRequest,
)
from evidencegate.results.types import ResultDraft
from evidencegate.runtime.state_contract import StateOperation
from .c2_config import C2R1Config
from .common import ProviderShellPlugin

class C2ShellPlugin(ProviderShellPlugin):
    plugin_id = "provider.c2.shell"
    category = OfficialPsCategory.C2_BEACONING
    family = AnalyticFamily.C2
    taxonomy = ("Network", "C2", "Provider Shell")
    accepted_types = (ObservationType.PACKET, ObservationType.FLOW)
    capabilities_by_type = {ObservationType.PACKET: frozenset({VisibilityCapability.PACKET_FACTS}), ObservationType.FLOW: frozenset({VisibilityCapability.FLOW_FACTS})}


@dataclass(frozen=True, slots=True)
class C2R1HistoryEvent:
    event_time: datetime
    observation_id: str


@dataclass(frozen=True, slots=True)
class C2R1State:
    events: tuple[C2R1HistoryEvent, ...]
    event_basis: str
    config_hash: str


class C2R1Plugin:
    """C2-R1/C2-M1: bounded descriptive flow-start recurrence measurement."""

    HARD_NEGATIVE_ALTERNATIVES = (
        "monitoring", "updater polling", "telemetry", "health checks", "RMM",
        "API automation",
    )

    def __init__(self, config: C2R1Config, *, max_state_entries: int) -> None:
        if not isinstance(config, C2R1Config):
            raise TypeError("config must be C2R1Config")
        if isinstance(max_state_entries, bool) or not isinstance(max_state_entries, int):
            raise TypeError("max_state_entries must be a non-bool integer")
        if max_state_entries <= 0:
            raise ValueError("max_state_entries must be greater than zero")
        self.config = config
        self._manifest = PluginManifest(
            plugin_id="provider.c2.r1", plugin_version="0.1.0",
            analytic_version="c2-r1-0.1.0",
            taxonomy=("Network", "C2", "Recurrence Measurement"),
            accepted_observation_types=(ObservationType.FLOW,),
            routing_predicate_version="c2-r1-flow-start-identity-v1",
            admission_requirements=(
                "FLOW_START equals canonical event_time",
                "unique trusted configured client, peer, and service roles",
            ),
            required_fields=("start_time", "protocol"),
            required_observation_contracts=(),
            required_visibility_capabilities=frozenset({VisibilityCapability.FLOW_FACTS}),
            required_quality=(), allowed_finality=tuple(Finality),
            allowed_availability_basis=tuple(AvailabilityBasis),
            state_key_declaration="client_ref x peer_ref x service_ref x protocol",
            scientific_history_duration=(
                f"configured minimum {config.minimum_history_events} FLOW_START events"
            ),
            resource_retention_duration=str(config.state_ttl),
            gap_action=GapAction.CONTINUE_WITH_QUALITY_FLAG,
            allowed_result_types=(
                ResultType.REVIEW_FINDING, ResultType.INSUFFICIENT_EVIDENCE,
                ResultType.PREREQUISITE_MISSING, ResultType.QUALITY_DEGRADED,
            ),
            integration_status=IntegrationStatus.BASELINE_IMPLEMENTED,
            profiling_hooks_enabled=False, governing_claim_ids=(),
            governing_decision_ids=(),
            official_ps_category=OfficialPsCategory.C2_BEACONING,
            analytic_family=AnalyticFamily.C2,
            # The active contract names C2-R1 as the analytic path and C2-M1 as
            # its mechanism ID.  Keep both rather than inventing a third ID.
            mechanism_id="C2-M1",
            state_resource_policy=StateResourcePolicy(
                max_entries=max_state_entries, max_ttl=config.state_ttl
            ),
            config_hash=config.canonical_hash,
        )

    def manifest(self) -> PluginManifest:
        return self._manifest

    def _identity_scope(
        self, observation: NetworkObservation
    ) -> tuple[str, str, str] | None:
        labels = (
            self.config.client_role_label,
            self.config.peer_role_label,
            self.config.service_role_label,
        )
        resolved: list[str] = []
        for label in labels:
            matches = tuple(
                assignment.identifier
                for assignment in observation.identity.role_assignments
                if assignment.role == label
            )
            if len(matches) != 1 or not matches[0]:
                return None
            resolved.append(matches[0])
        return resolved[0], resolved[1], resolved[2]

    def _prerequisites_hold(self, observation: NetworkObservation) -> bool:
        if observation.observation_type is not ObservationType.FLOW:
            return False
        if any(name not in observation.present_fields for name in ("start_time", "protocol")):
            return False
        payload = observation.typed_payload
        return (
            payload.start_time == observation.event_time
            and self._identity_scope(observation) is not None
        )

    def route(self, observation: NetworkObservation) -> bool:
        return self._prerequisites_hold(observation)

    def state_key(self, observation: NetworkObservation) -> StateKey | None:
        if not self._prerequisites_hold(observation):
            return None
        client_ref, peer_ref, service_ref = self._identity_scope(observation)  # type: ignore[misc]
        return StateKey(json.dumps(
            [client_ref, peer_ref, service_ref, observation.typed_payload.protocol],
            ensure_ascii=False, separators=(",", ":"),
        ))

    @staticmethod
    def _mad(values: tuple[float, ...]) -> float:
        center = median(values)
        return float(median(tuple(abs(value - center) for value in values)))

    @staticmethod
    def _quality_evidence(observation: NetworkObservation) -> dict[str, str]:
        return {
            "packet_loss": observation.quality.packet_loss.value,
            "sampling": observation.quality.sampling.value,
            "parser": observation.quality.parser.value,
            "capture_gap": observation.quality.capture_gap.value,
        }

    async def process(
        self, observation: NetworkObservation, context: Any,
        state: PluginStateSnapshot | None,
    ) -> PluginProcessOutcome:
        key = self.state_key(observation)
        scope = self._identity_scope(observation)
        if key is None or scope is None:
            raise ValueError("C2-R1 prerequisites must hold before processing")
        if state is not None and not isinstance(state.payload, C2R1State):
            raise TypeError("C2-R1 state payload has an unexpected type")
        if state is not None and (
            state.payload.event_basis != self.config.event_basis.value
            or state.payload.config_hash != self.config.canonical_hash
        ):
            raise ValueError("C2-R1 state configuration provenance mismatch")

        prior = () if state is None else state.payload.events
        current = C2R1HistoryEvent(
            event_time=observation.typed_payload.start_time,
            observation_id=observation.observation_id,
        )
        causal_events = prior + (current,)
        retained = causal_events[-self.config.max_retained_events_per_pair:]
        next_state = C2R1State(
            events=retained,
            event_basis=self.config.event_basis.value,
            config_hash=self.config.canonical_hash,
        )
        measurement_events = retained
        count = len(measurement_events)
        ready = count >= self.config.minimum_history_events
        readiness = EvaluationReadinessDecision(
            EvidenceReadiness.READY if ready else EvidenceReadiness.INSUFFICIENT_HISTORY,
            None if ready else (
                f"observed {count} of {self.config.minimum_history_events} required events"
            ),
        )
        client_ref, peer_ref, service_ref = scope
        entity = {
            "client_ref": client_ref, "peer_ref": peer_ref,
            "service_ref": service_ref, "protocol": observation.typed_payload.protocol,
        }
        # The runtime always adds the triggering observation.  The draft names
        # only the additional retained causal observations used by R1.
        supporting_ids = tuple(
            event.observation_id for event in measurement_events[:-1]
        )
        common_evidence: dict[str, object] = {
            "analytic_path": "C2-R1",
            "evidence_kind": "C2_COMMUNICATION_PATTERN_MEASUREMENT",
            "entity": entity,
            "event_basis": self.config.event_basis.value,
            "observed_event_count": count,
            "required_event_count": self.config.minimum_history_events,
            "capture_quality": self._quality_evidence(observation),
            "claim_ceiling": (
                "RECURRENT_COMMUNICATION_MEASUREMENT_ONLY; NOT_C2; NOT_MALWARE; "
                "NOT_COMPROMISE; NOT_BENIGN"
            ),
        }
        if ready:
            intervals = tuple(
                (later.event_time - earlier.event_time).total_seconds()
                for earlier, later in zip(measurement_events, measurement_events[1:])
            )
            evidence = {
                **common_evidence,
                "measurements": {
                    "event_count": count,
                    "history_span_seconds": (
                        measurement_events[-1].event_time - measurement_events[0].event_time
                    ).total_seconds(),
                    "interval_count": len(intervals),
                    "iat_median_seconds": float(median(intervals)),
                    # Required by the active C2 plugin contract as a factual
                    # dispersion primitive; this is not an R2 conclusion.
                    "iat_mad_seconds": self._mad(intervals),
                },
                "hard_negative_alternatives": self.HARD_NEGATIVE_ALTERNATIVES,
            }
            draft = ResultDraft(
                ResultType.REVIEW_FINDING,
                entity_reference=str(key), evidence_items=(),
                missing_prerequisites=(),
                evidence_interval=(
                    measurement_events[0].event_time, measurement_events[-1].event_time
                ),
                evidence=evidence, source_observation_ids=supporting_ids,
            )
        else:
            draft = ResultDraft(
                ResultType.INSUFFICIENT_EVIDENCE,
                entity_reference=str(key), evidence_items=(),
                missing_prerequisites=(
                    f"{self.config.minimum_history_events - count} additional FLOW_START event(s)",
                ),
                evidence=common_evidence,
                source_observation_ids=supporting_ids,
            )
        return PluginProcessOutcome(
            result_drafts=(draft,),
            state_transition=StateTransitionRequest(
                key=key,
                expected_version=None if state is None else state.version,
                operation=StateOperation.UPSERT,
                payload=next_state,
                ttl=self.config.state_ttl,
            ),
            evaluation_readiness=readiness,
        )

    async def on_quality_gap(
        self, gap: QualityGap, context: Any, state: Any
    ) -> Sequence[ResultDraft]:
        return ()

    async def on_watermark(
        self, watermark: datetime, context: Any
    ) -> PluginProcessOutcome:
        return PluginProcessOutcome()

    async def on_expire(
        self, key: StateKey, context: Any, state: PluginStateSnapshot
    ) -> PluginProcessOutcome:
        return PluginProcessOutcome()
