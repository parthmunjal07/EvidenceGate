"""Category-5 bounded, factual Recon activity measurements.

These mechanisms describe captured activity only. They do not infer intent,
authorization, actor identity, compromise, or a family-level score.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from typing import Any, Sequence

from evidencegate.admission.evaluator import EvaluationReadinessDecision
from evidencegate.domain.enums import (
    AnalyticFamily,
    AvailabilityBasis,
    EvidenceReadiness,
    Finality,
    GapAction,
    IntegrationStatus,
    ObservationType,
    OfficialPsCategory,
    QualityState,
    ResultType,
    VisibilityCapability,
    WireDirection,
)
from evidencegate.domain.events import NetworkObservation
from evidencegate.domain.quality import QualityGap
from evidencegate.registry.manifest import PluginManifest, StateResourcePolicy
from evidencegate.registry.plugin import (
    PluginProcessOutcome,
    PluginStateSnapshot,
    StateKey,
    StateTransitionRequest,
)
from evidencegate.results.types import ResultDraft
from evidencegate.runtime.state_contract import StateOperation

from .common import ProviderShellPlugin
from .recon_config import ReconConfig


CLAIM_CEILING = (
    "OBSERVED_SCAN_ACTIVITY_EVIDENCE_ONLY;"
    "NO_MALICIOUSNESS;"
    "NO_AUTHORIZATION_INFERENCE;"
    "NO_ATTACKER_IDENTITY;"
    "NO_COMPROMISE"
)

HARD_NEGATIVE_ALTERNATIVES = (
    "service discovery",
    "monitoring",
    "health checks",
    "asset inventory",
    "load balancers",
    "software deployment",
    "legitimate multi-service clients",
    "retry storms",
    "distributed administration",
    "NAT",
    "CDN behavior",
    "authorized vulnerability scanning",
)


class ReconShellPlugin(ProviderShellPlugin):
    plugin_id = "provider.recon.shell"
    category = OfficialPsCategory.RECONNAISSANCE_AND_PORT_SCANNING
    family = AnalyticFamily.RECON
    taxonomy = ("Network", "Reconnaissance", "Provider Shell")
    accepted_types = (ObservationType.PACKET, ObservationType.FLOW)
    capabilities_by_type = {
        ObservationType.PACKET: frozenset({VisibilityCapability.PACKET_FACTS}),
        ObservationType.FLOW: frozenset({VisibilityCapability.FLOW_FACTS}),
    }


@dataclass(frozen=True, slots=True)
class ReconAttemptEvent:
    event_time: datetime
    observation_id: str
    target_host: str
    target_port: int
    quality_states: tuple[str, str, str, str]


@dataclass(frozen=True, slots=True)
class ReconBreadthState:
    events: tuple[ReconAttemptEvent, ...]
    config_hash: str
    capacity_dropped_event_count: int = 0


@dataclass(frozen=True, slots=True)
class ReconTcpEvent:
    event_time: datetime
    observation_id: str
    fact: str


@dataclass(frozen=True, slots=True)
class ReconTcpState:
    events: tuple[ReconTcpEvent, ...]
    config_hash: str
    capacity_dropped_event_count: int = 0


def _quality_states(observation: NetworkObservation) -> tuple[str, str, str, str]:
    quality = observation.quality
    return (
        quality.packet_loss.value,
        quality.sampling.value,
        quality.parser.value,
        quality.capture_gap.value,
    )


def _quality_evidence(events: tuple[ReconAttemptEvent, ...]) -> dict[str, object]:
    names = ("packet_loss", "sampling", "parser", "capture_gap")
    states = {
        name: sorted({event.quality_states[index] for event in events})
        for index, name in enumerate(names)
    }
    return {
        "states_observed": states,
        "degraded": any(QualityState.DEGRADED.value in values for values in states.values()),
        "unknown_present": any(QualityState.UNKNOWN.value in values for values in states.values()),
        "count_interpretation": "OBSERVED_LOWER_BOUND",
    }


class _ReconPluginBase:
    mechanism_id: str
    plugin_id: str
    taxonomy_leaf: str
    state_key_declaration: str

    def __init__(
        self,
        config: ReconConfig,
        *,
        max_state_entries: int,
        governing_decision_ids: tuple[str, ...] = (),
    ) -> None:
        if not isinstance(config, ReconConfig):
            raise TypeError("config must be ReconConfig")
        if isinstance(max_state_entries, bool) or not isinstance(max_state_entries, int):
            raise TypeError("max_state_entries must be a non-bool integer")
        if max_state_entries <= 0:
            raise ValueError("max_state_entries must be greater than zero")
        self.config = config
        self._manifest = PluginManifest(
            plugin_id=self.plugin_id,
            plugin_version="0.1.0",
            analytic_version="recon-measurement-0.1.0",
            taxonomy=("Network", "Reconnaissance", self.taxonomy_leaf),
            accepted_observation_types=(ObservationType.PACKET,),
            routing_predicate_version="trusted-role-explicit-direction-tcp-facts-v1",
            admission_requirements=(
                "explicit FORWARD/REVERSE wire direction",
                "unique trusted initiator and target role assignments",
                "role identifiers agree with direction-oriented packet endpoints",
                "explicit TCP protocol fact in the canonical packet field",
            ),
            required_fields=(
                "protocol",
                "src_address",
                "dst_address",
                "src_port",
                "dst_port",
                "flags",
            ),
            required_observation_contracts=(),
            required_visibility_capabilities=frozenset({VisibilityCapability.PACKET_FACTS}),
            required_quality=(),
            allowed_finality=tuple(Finality),
            allowed_availability_basis=tuple(AvailabilityBasis),
            state_key_declaration=self.state_key_declaration,
            scientific_history_duration=(
                "configured bounded horizons: " + ",".join(str(item) for item in config.horizons)
            ),
            resource_retention_duration=str(config.state_ttl),
            gap_action=GapAction.CONTINUE_WITH_QUALITY_FLAG,
            allowed_result_types=(
                ResultType.REVIEW_FINDING,
                ResultType.INSUFFICIENT_EVIDENCE,
                ResultType.QUALITY_DEGRADED,
            ),
            integration_status=IntegrationStatus.BASELINE_IMPLEMENTED,
            profiling_hooks_enabled=False,
            governing_claim_ids=(),
            governing_decision_ids=governing_decision_ids,
            official_ps_category=OfficialPsCategory.RECONNAISSANCE_AND_PORT_SCANNING,
            analytic_family=AnalyticFamily.RECON,
            mechanism_id=self.mechanism_id,
            state_resource_policy=StateResourcePolicy(
                max_entries=max_state_entries, max_ttl=config.state_ttl
            ),
            config_hash=config.canonical_hash,
        )

    def manifest(self) -> PluginManifest:
        return self._manifest

    def _role_scope(self, observation: NetworkObservation) -> tuple[str, str] | None:
        resolved: list[str] = []
        for label in (self.config.initiator_role_label, self.config.target_role_label):
            matches = tuple(
                assignment.identifier
                for assignment in observation.identity.role_assignments
                if assignment.role == label
            )
            if len(matches) != 1 or not matches[0]:
                return None
            resolved.append(matches[0])
        return resolved[0], resolved[1]

    def _packet_scope(
        self, observation: NetworkObservation
    ) -> tuple[str, str, int, int, str] | None:
        if observation.observation_type is not ObservationType.PACKET:
            return None
        required = {
            "protocol",
            "src_address",
            "dst_address",
            "src_port",
            "dst_port",
            "flags",
        }
        if not required.issubset(observation.present_fields):
            return None
        if observation.wire_direction not in (WireDirection.FORWARD, WireDirection.REVERSE):
            return None
        payload = observation.typed_payload
        roles = self._role_scope(observation)
        if roles is None:
            return None
        protocol_value = payload.protocol
        if protocol_value == 6:
            protocol = "TCP"
        else:
            return None
        if not isinstance(payload.src_port, int) or not isinstance(payload.dst_port, int):
            return None
        if observation.wire_direction is WireDirection.FORWARD:
            addresses = (payload.src_address, payload.dst_address)
            initiator_port, target_port = payload.src_port, payload.dst_port
        else:
            addresses = (payload.dst_address, payload.src_address)
            initiator_port, target_port = payload.dst_port, payload.src_port
        if roles != addresses:
            return None
        return roles[0], roles[1], initiator_port, target_port, protocol

    @staticmethod
    def _flag_set(observation: NetworkObservation) -> frozenset[str]:
        return frozenset(item.upper() for item in observation.typed_payload.flags)

    def _is_forward_attempt(self, observation: NetworkObservation) -> bool:
        if self._packet_scope(observation) is None:
            return False
        flags = self._flag_set(observation)
        return (
            observation.wire_direction is WireDirection.FORWARD
            and "SYN" in flags
            and "ACK" not in flags
        )

    async def on_quality_gap(
        self, gap: QualityGap, context: Any, state: Any
    ) -> Sequence[ResultDraft]:
        return ()

    async def on_watermark(self, watermark: datetime, context: Any) -> PluginProcessOutcome:
        return PluginProcessOutcome()

    async def on_expire(
        self, key: StateKey, context: Any, state: PluginStateSnapshot
    ) -> PluginProcessOutcome:
        return PluginProcessOutcome()


class _ReconBreadthPlugin(_ReconPluginBase):
    def route(self, observation: NetworkObservation) -> bool:
        return self._is_forward_attempt(observation)

    def _key_parts(self, scope: tuple[str, str, int, int, str]) -> tuple[object, ...]:
        raise NotImplementedError

    def state_key(self, observation: NetworkObservation) -> StateKey | None:
        if not self._is_forward_attempt(observation):
            return None
        scope = self._packet_scope(observation)
        if scope is None:
            return None
        return StateKey(
            json.dumps(self._key_parts(scope), ensure_ascii=False, separators=(",", ":"))
        )

    def _measurement(self, events: tuple[ReconAttemptEvent, ...]) -> dict[str, int]:
        raise NotImplementedError

    async def process(
        self,
        observation: NetworkObservation,
        context: Any,
        state: PluginStateSnapshot | None,
    ) -> PluginProcessOutcome:
        key, scope = self.state_key(observation), self._packet_scope(observation)
        if key is None or scope is None:
            raise ValueError(f"{self.mechanism_id} prerequisites must hold")
        if state is not None and not isinstance(state.payload, ReconBreadthState):
            raise TypeError(f"{self.mechanism_id} state payload has an unexpected type")
        if state is not None and state.payload.config_hash != self.config.canonical_hash:
            raise ValueError(f"{self.mechanism_id} state configuration mismatch")
        prior = () if state is None else state.payload.events
        prior_dropped = 0 if state is None else state.payload.capacity_dropped_event_count
        current = ReconAttemptEvent(
            observation.event_time,
            observation.observation_id,
            scope[1],
            scope[3],
            _quality_states(observation),
        )
        oldest = observation.event_time - self.config.horizons[-1]
        retained = tuple(event for event in prior if event.event_time >= oldest) + (current,)
        retained = tuple(sorted(retained, key=lambda item: (item.event_time, item.observation_id)))
        overflow = max(0, len(retained) - self.config.max_events_per_key)
        if overflow:
            retained = retained[overflow:]
        dropped = prior_dropped + overflow
        horizons: list[dict[str, object]] = []
        for horizon in self.config.horizons:
            boundary = observation.event_time - horizon
            events = tuple(event for event in retained if event.event_time >= boundary)
            horizons.append(
                {
                    "horizon_seconds": horizon.total_seconds(),
                    **self._measurement(events),
                }
            )
        draft = ResultDraft(
            ResultType.REVIEW_FINDING,
            entity_reference=str(key),
            evidence_items=(),
            missing_prerequisites=(),
            evidence_interval=(retained[0].event_time, retained[-1].event_time),
            evidence={
                "evidence_kind": "OBSERVED_TCP_SCAN_ACTIVITY_MEASUREMENT",
                "mechanism": self.mechanism_id,
                "protocol": scope[4],
                "configured_horizons": horizons,
                "measurements": horizons[-1],
                "quality": _quality_evidence(retained),
                "state_capacity": {
                    "retained_event_count": len(retained),
                    "max_events_per_key": self.config.max_events_per_key,
                    "capacity_dropped_event_count": dropped,
                    "capacity_truncated": dropped > 0,
                },
                "claim_ceiling": CLAIM_CEILING,
                "hard_negative_alternatives": HARD_NEGATIVE_ALTERNATIVES,
            },
            source_observation_ids=tuple(
                event.observation_id
                for event in retained
                if event.observation_id != observation.observation_id
            ),
        )
        return PluginProcessOutcome(
            result_drafts=(draft,),
            state_transition=StateTransitionRequest(
                key=key,
                expected_version=None if state is None else state.version,
                operation=StateOperation.UPSERT,
                payload=ReconBreadthState(retained, self.config.canonical_hash, dropped),
                ttl=self.config.state_ttl,
            ),
            evaluation_readiness=EvaluationReadinessDecision(EvidenceReadiness.READY, None),
        )


class ReconHPlugin(_ReconBreadthPlugin):
    """RECON-H: horizontal target-host breadth per initiator/service/protocol."""

    plugin_id, mechanism_id = "provider.recon.h", "RECON-H"
    taxonomy_leaf = "Horizontal Host Breadth"
    state_key_declaration = "trusted initiator x target service x protocol"

    def _key_parts(self, scope: tuple[str, str, int, int, str]) -> tuple[object, ...]:
        return scope[0], scope[3], scope[4]

    def _measurement(self, events: tuple[ReconAttemptEvent, ...]) -> dict[str, int]:
        return {
            "distinct_hosts": len({e.target_host for e in events}),
            "attempt_count": len(events),
        }


class ReconVPlugin(_ReconBreadthPlugin):
    """RECON-V: vertical target-port breadth per initiator/target/protocol."""

    plugin_id, mechanism_id = "provider.recon.v", "RECON-V"
    taxonomy_leaf = "Vertical Port Breadth"
    state_key_declaration = "trusted initiator x trusted target x protocol"

    def _key_parts(self, scope: tuple[str, str, int, int, str]) -> tuple[object, ...]:
        return scope[0], scope[1], scope[4]

    def _measurement(self, events: tuple[ReconAttemptEvent, ...]) -> dict[str, int]:
        return {
            "distinct_ports": len({e.target_port for e in events}),
            "attempt_count": len(events),
        }


class Recon2DPlugin(_ReconBreadthPlugin):
    """RECON-2D: independent host-by-port exploration geometry."""

    plugin_id, mechanism_id = "provider.recon.2d", "RECON-2D"
    taxonomy_leaf = "Host Port Geometry"
    state_key_declaration = "trusted initiator x protocol"

    def _key_parts(self, scope: tuple[str, str, int, int, str]) -> tuple[object, ...]:
        return scope[0], scope[4]

    def _measurement(self, events: tuple[ReconAttemptEvent, ...]) -> dict[str, int]:
        return {
            "distinct_hosts": len({e.target_host for e in events}),
            "distinct_ports": len({e.target_port for e in events}),
            "distinct_host_port_pairs": len({(e.target_host, e.target_port) for e in events}),
            "attempt_count": len(events),
        }


class ReconTcpPlugin(_ReconPluginBase):
    """RECON-TCP: captured TCP attempt/response facts without port-state claims."""

    plugin_id, mechanism_id = "provider.recon.tcp", "RECON-TCP"
    taxonomy_leaf = "TCP Activity Evidence"
    state_key_declaration = (
        "trusted initiator x trusted target x initiator port x target port x protocol"
    )

    def _fact(self, observation: NetworkObservation) -> str | None:
        if self._packet_scope(observation) is None:
            return None
        flags = self._flag_set(observation)
        if observation.wire_direction is WireDirection.FORWARD:
            if "SYN" in flags and "ACK" not in flags:
                return "INITIATING_SYN_OBSERVED"
            if "ACK" in flags and "SYN" not in flags and "RST" not in flags:
                return "FORWARD_ACK_OBSERVED"
        elif "SYN" in flags and "ACK" in flags:
            return "SYN_ACK_RESPONSE_OBSERVED"
        elif "RST" in flags:
            return "RST_RESPONSE_OBSERVED"
        return None

    def route(self, observation: NetworkObservation) -> bool:
        return self._fact(observation) is not None

    def state_key(self, observation: NetworkObservation) -> StateKey | None:
        scope = self._packet_scope(observation)
        if scope is None or self._fact(observation) is None:
            return None
        return StateKey(json.dumps(scope, ensure_ascii=False, separators=(",", ":")))

    async def process(
        self,
        observation: NetworkObservation,
        context: Any,
        state: PluginStateSnapshot | None,
    ) -> PluginProcessOutcome:
        key, fact = self.state_key(observation), self._fact(observation)
        if key is None or fact is None:
            raise ValueError("RECON-TCP prerequisites must hold")
        if state is not None and not isinstance(state.payload, ReconTcpState):
            raise TypeError("RECON-TCP state payload has an unexpected type")
        if state is not None and state.payload.config_hash != self.config.canonical_hash:
            raise ValueError("RECON-TCP state configuration mismatch")
        prior = () if state is None else state.payload.events
        has_attempt = any(item.fact == "INITIATING_SYN_OBSERVED" for item in prior)
        if not has_attempt and fact != "INITIATING_SYN_OBSERVED":
            draft = ResultDraft(
                ResultType.INSUFFICIENT_EVIDENCE,
                entity_reference=str(key),
                evidence_items=(),
                missing_prerequisites=("prior captured initiating SYN",),
                evidence={
                    "evidence_kind": "MIDSTREAM_TCP_RESPONSE_OR_PROGRESSION",
                    "current_observed_fact": fact,
                    "forward_attempt_reconstructed": False,
                    "claim_ceiling": CLAIM_CEILING,
                },
            )
            return PluginProcessOutcome(
                result_drafts=(draft,),
                evaluation_readiness=EvaluationReadinessDecision(
                    EvidenceReadiness.ABSTAINING, "no prior captured initiating SYN"
                ),
            )
        current = ReconTcpEvent(observation.event_time, observation.observation_id, fact)
        retained = tuple(
            sorted(prior + (current,), key=lambda item: (item.event_time, item.observation_id))
        )
        overflow = max(0, len(retained) - self.config.max_events_per_key)
        if overflow:
            retained = retained[overflow:]
        dropped = (0 if state is None else state.payload.capacity_dropped_event_count) + overflow
        facts = tuple(item.fact for item in retained)
        first_syn_ack = next(
            (i for i, value in enumerate(facts) if value == "SYN_ACK_RESPONSE_OBSERVED"), None
        )
        ack_count = (
            0
            if first_syn_ack is None
            else sum(value == "FORWARD_ACK_OBSERVED" for value in facts[first_syn_ack + 1 :])
        )
        draft = ResultDraft(
            ResultType.REVIEW_FINDING,
            entity_reference=str(key),
            evidence_items=(),
            missing_prerequisites=(),
            evidence_interval=(retained[0].event_time, retained[-1].event_time),
            evidence={
                "evidence_kind": "OBSERVED_TCP_ATTEMPT_OUTCOME_FACTS",
                "observed_facts": {
                    "initiating_syn_count": facts.count("INITIATING_SYN_OBSERVED"),
                    "captured_syn_ack_response_count": facts.count("SYN_ACK_RESPONSE_OBSERVED"),
                    "captured_rst_response_count": facts.count("RST_RESPONSE_OBSERVED"),
                    "captured_ack_progression_count": ack_count,
                    "no_reverse_evidence_available": not any(
                        value in ("SYN_ACK_RESPONSE_OBSERVED", "RST_RESPONSE_OBSERVED")
                        for value in facts
                    ),
                },
                "current_observed_fact": fact,
                "state_capacity": {
                    "retained_event_count": len(retained),
                    "max_events_per_key": self.config.max_events_per_key,
                    "capacity_dropped_event_count": dropped,
                    "capacity_truncated": dropped > 0,
                },
                "claim_ceiling": CLAIM_CEILING,
                "hard_negative_alternatives": HARD_NEGATIVE_ALTERNATIVES,
            },
            source_observation_ids=tuple(
                item.observation_id
                for item in retained
                if item.observation_id != observation.observation_id
            ),
        )
        return PluginProcessOutcome(
            result_drafts=(draft,),
            state_transition=StateTransitionRequest(
                key=key,
                expected_version=None if state is None else state.version,
                operation=StateOperation.UPSERT,
                payload=ReconTcpState(retained, self.config.canonical_hash, dropped),
                ttl=self.config.state_ttl,
            ),
            evaluation_readiness=EvaluationReadinessDecision(EvidenceReadiness.READY, None),
        )
