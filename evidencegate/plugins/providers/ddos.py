"""Category-1 DDoS shell and factual DDOS-A-B0 TCP attempt state."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
import json
from typing import Any, Sequence

from evidencegate.admission.evaluator import EvaluationReadinessDecision
from evidencegate.domain.enums import (
    AnalyticFamily, AvailabilityBasis, CapabilityState, EvidenceReadiness,
    Finality, GapAction, IntegrationStatus, ObservationType, OfficialPsCategory,
    QualityState, ResultType, VisibilityCapability, WireDirection,
)
from evidencegate.domain.events import NetworkObservation
from evidencegate.domain.quality import QualityGap
from evidencegate.registry.manifest import PluginManifest, StateResourcePolicy
from evidencegate.registry.plugin import (
    PluginProcessOutcome, PluginStateSnapshot, StateKey, StateTransitionRequest,
)
from evidencegate.results.types import ResultDraft
from evidencegate.runtime.state_contract import StateOperation

from .common import ProviderShellPlugin
from .ddos_config import DdosASynConfig

class DdosShellPlugin(ProviderShellPlugin):
    plugin_id = "provider.ddos.shell"
    category = OfficialPsCategory.DDOS
    family = AnalyticFamily.DDOS
    taxonomy = ("Network", "DDoS", "Provider Shell")
    accepted_types = (ObservationType.PACKET, ObservationType.FLOW)
    capabilities_by_type = {ObservationType.PACKET: frozenset({VisibilityCapability.PACKET_FACTS}), ObservationType.FLOW: frozenset({VisibilityCapability.FLOW_FACTS})}


DDOS_A_CLAIM_CEILING = (
    "OBSERVED_TCP_SYN_AND_CAPTURED_STATE_EVIDENCE_ONLY;"
    "NO_DDOS_CONFIRMED;NO_VICTIM_EXHAUSTION;NO_BACKLOG_EXHAUSTION;"
    "NO_MALICIOUSNESS;NO_ATTACKER_IDENTITY"
)


@dataclass(frozen=True, slots=True)
class DdosASynState:
    """Fixed-size factual state for one visible normalized TCP tuple."""

    phase: str
    target_ref: str
    service_ref: str
    normalized_tuple: tuple[tuple[str, int], tuple[str, int]]
    first_seen_time: datetime
    last_seen_time: datetime
    initiating_syn_observation_id: str
    synack_observation_id: str | None
    ack_observation_id: str | None
    rst_observation_id: str | None
    raw_syn_observations: int
    recognized_retransmissions: int
    retransmission_deduplication_available: bool
    reverse_visibility_available_at_start: bool
    source_visibility: tuple[tuple[str, str], ...]
    capture_quality: tuple[tuple[str, str], ...]
    quality_degraded: bool
    midstream_or_unknown_history: bool
    initial_syn_signature: str | None
    config_hash: str


class DdosASynPlugin:
    """DDOS-A-B0: factual SYN arrival and captured TCP state evidence only."""

    RECOGNIZED_FLAGS = frozenset({"SYN", "ACK", "RST"})
    HARD_NEGATIVE_ALTERNATIVES = (
        "flash crowd", "authorized load/performance test",
        "retry/reconnection storm", "scanner burst", "outage recovery",
        "misconfiguration", "NAT/load-balancer behavior",
        "asymmetric routing", "packet loss", "capture overload",
    )

    def __init__(
        self, config: DdosASynConfig, *, max_state_entries: int,
        governing_decision_ids: tuple[str, ...] = (),
    ) -> None:
        if not isinstance(config, DdosASynConfig):
            raise TypeError("config must be DdosASynConfig")
        if isinstance(max_state_entries, bool) or not isinstance(max_state_entries, int):
            raise TypeError("max_state_entries must be a non-bool integer")
        if max_state_entries <= 0:
            raise ValueError("max_state_entries must be greater than zero")
        self.config = config
        self._manifest = PluginManifest(
            plugin_id="provider.ddos.syn_state",
            plugin_version="0.1.0",
            analytic_version="ddos-a-b0-0.1.0",
            taxonomy=("Network", "DDoS", "TCP SYN State Evidence"),
            accepted_observation_types=(ObservationType.PACKET,),
            routing_predicate_version="ddos-a-visible-tcp-state-v1",
            admission_requirements=(
                "known explicit wire direction",
                "unique trusted target_id and service_id role assignments",
                "explicit canonical TCP protocol and supported canonical flags",
            ),
            required_fields=(
                "protocol", "src_address", "dst_address", "src_port",
                "dst_port", "flags",
            ),
            required_observation_contracts=(),
            required_visibility_capabilities=frozenset(
                {VisibilityCapability.PACKET_FACTS}
            ),
            required_quality=(),
            allowed_finality=tuple(Finality),
            allowed_availability_basis=tuple(AvailabilityBasis),
            state_key_declaration=(
                "target x service x normalized visible tuple x protocol"
            ),
            scientific_history_duration=(
                "transition or watermark expiry; no minimum observation count"
            ),
            resource_retention_duration=str(config.syn_state_ttl),
            gap_action=GapAction.CONTINUE_WITH_QUALITY_FLAG,
            allowed_result_types=(
                ResultType.REVIEW_FINDING, ResultType.INSUFFICIENT_EVIDENCE,
                ResultType.QUALITY_DEGRADED,
            ),
            integration_status=IntegrationStatus.BASELINE_IMPLEMENTED,
            profiling_hooks_enabled=False,
            governing_claim_ids=(),
            governing_decision_ids=governing_decision_ids,
            official_ps_category=OfficialPsCategory.DDOS,
            analytic_family=AnalyticFamily.DDOS,
            mechanism_id="DDOS-A-B0",
            state_resource_policy=StateResourcePolicy(
                max_entries=max_state_entries, max_ttl=config.syn_state_ttl
            ),
            config_hash=config.canonical_hash,
        )

    def manifest(self) -> PluginManifest:
        return self._manifest

    def _identity_scope(
        self, observation: NetworkObservation
    ) -> tuple[str, str] | None:
        resolved: list[str] = []
        for label in (
            self.config.target_role_label, self.config.service_role_label
        ):
            matches = tuple(
                assignment.identifier
                for assignment in observation.identity.role_assignments
                if assignment.role == label
            )
            if len(matches) != 1 or not matches[0]:
                return None
            resolved.append(matches[0])
        return resolved[0], resolved[1]

    @staticmethod
    def _normalized_tuple(
        observation: NetworkObservation,
    ) -> tuple[tuple[str, int], tuple[str, int]] | None:
        payload = observation.typed_payload
        values = (
            payload.src_address, payload.src_port,
            payload.dst_address, payload.dst_port,
        )
        if (
            not isinstance(values[0], str) or not values[0]
            or isinstance(values[1], bool) or not isinstance(values[1], int)
            or not isinstance(values[2], str) or not values[2]
            or isinstance(values[3], bool) or not isinstance(values[3], int)
        ):
            return None
        endpoints = ((values[0], values[1]), (values[2], values[3]))
        return tuple(sorted(endpoints, key=lambda item: (item[0], item[1])))  # type: ignore[return-value]

    def _flags(self, observation: NetworkObservation) -> frozenset[str] | None:
        flags = observation.typed_payload.flags
        if (
            not isinstance(flags, list) or not flags
            or any(not isinstance(flag, str) for flag in flags)
        ):
            return None
        values = frozenset(flags)
        if not values <= self.RECOGNIZED_FLAGS:
            return None
        return values

    def _prerequisites_hold(self, observation: NetworkObservation) -> bool:
        if observation.observation_type is not ObservationType.PACKET:
            return False
        if any(name not in observation.present_fields for name in self._manifest.required_fields):
            return False
        payload = observation.typed_payload
        return (
            payload.protocol == self.config.tcp_protocol_number
            and observation.wire_direction is not WireDirection.UNKNOWN
            and self._identity_scope(observation) is not None
            and self._normalized_tuple(observation) is not None
            and self._flags(observation) is not None
        )

    def route(self, observation: NetworkObservation) -> bool:
        return self._prerequisites_hold(observation)

    def state_key(self, observation: NetworkObservation) -> StateKey | None:
        if not self._prerequisites_hold(observation):
            return None
        target_ref, service_ref = self._identity_scope(observation)  # type: ignore[misc]
        visible_tuple = self._normalized_tuple(observation)
        return StateKey(json.dumps(
            [target_ref, service_ref, observation.typed_payload.protocol, visible_tuple],
            ensure_ascii=False, separators=(",", ":"),
        ))

    @staticmethod
    def _quality(observation: NetworkObservation) -> tuple[tuple[str, str], ...]:
        return (
            ("packet_loss", observation.quality.packet_loss.value),
            ("sampling", observation.quality.sampling.value),
            ("parser", observation.quality.parser.value),
            ("capture_gap", observation.quality.capture_gap.value),
        )

    @staticmethod
    def _merge_quality(
        prior: tuple[tuple[str, str], ...], observation: NetworkObservation
    ) -> tuple[tuple[str, str], ...]:
        """Retain the most conservative factual quality seen by the attempt."""
        current = dict(DdosASynPlugin._quality(observation))
        merged: list[tuple[str, str]] = []
        for name, prior_value in prior:
            values = {prior_value, current[name]}
            if QualityState.DEGRADED.value in values:
                value = QualityState.DEGRADED.value
            elif QualityState.UNKNOWN.value in values:
                value = QualityState.UNKNOWN.value
            else:
                value = QualityState.CLEAR.value
            merged.append((name, value))
        return tuple(merged)

    @staticmethod
    def _visibility(observation: NetworkObservation) -> tuple[tuple[str, str], ...]:
        return tuple(
            (capability.value, observation.visibility.state(capability).value)
            for capability in (
                VisibilityCapability.FORWARD_FACTS,
                VisibilityCapability.REVERSE_FACTS,
            )
        )

    @staticmethod
    def _observation_degraded(observation: NetworkObservation) -> bool:
        return QualityState.DEGRADED in (
            observation.quality.packet_loss, observation.quality.sampling,
            observation.quality.parser, observation.quality.capture_gap,
        )

    @staticmethod
    def _sequence_signature(
        observation: NetworkObservation,
        normalized_tuple: tuple[tuple[str, int], tuple[str, int]],
        flags: frozenset[str],
    ) -> str | None:
        """Use only the declared controlled mini-contract: integer seq/ack."""
        facts = observation.typed_payload.sequence_facts
        if not isinstance(facts, dict) or "seq" not in facts:
            return None
        if set(facts) - {"seq", "ack"}:
            return None
        if any(
            isinstance(value, bool) or not isinstance(value, int)
            for value in facts.values()
        ):
            return None
        return json.dumps(
            [normalized_tuple, observation.wire_direction.value,
             sorted(flags), facts.get("seq"), facts.get("ack")],
            ensure_ascii=False, separators=(",", ":"),
        )

    @staticmethod
    def _supporting_ids(state: DdosASynState) -> tuple[str, ...]:
        return tuple(dict.fromkeys(item for item in (
            state.initiating_syn_observation_id, state.synack_observation_id,
            state.ack_observation_id, state.rst_observation_id,
        ) if item))

    def _evidence(
        self, state: DdosASynState, *, state_before: str, state_after: str,
        evidence_kind: str, direction: str | None,
        missing_evidence: tuple[str, ...] = (), statement: str | None = None,
        dedupe_status: str | None = None,
    ) -> dict[str, object]:
        value: dict[str, object] = {
            "analytic_path": "DDOS-A",
            "evidence_kind": evidence_kind,
            "target_ref": state.target_ref,
            "service_ref": state.service_ref,
            "protocol": self.config.tcp_protocol_number,
            "visible_tuple": state.normalized_tuple,
            "state_before": state_before,
            "state_after": state_after,
            "first_seen_time": state.first_seen_time,
            "last_seen_time": state.last_seen_time,
            "observed_syn": bool(state.initiating_syn_observation_id),
            "observed_synack": state.synack_observation_id is not None,
            "observed_ack": state.ack_observation_id is not None,
            "observed_rst": state.rst_observation_id is not None,
            "raw_syn_observations": state.raw_syn_observations,
            "recognized_retransmissions": state.recognized_retransmissions,
            "retransmission_deduplication_status": dedupe_status or (
                "AVAILABLE" if state.retransmission_deduplication_available
                else "UNAVAILABLE"
            ),
            "source_visibility": dict(state.source_visibility),
            "wire_direction": direction,
            "capture_quality": dict(state.capture_quality),
            "runtime_or_state_quality_degraded": state.quality_degraded,
            "missing_evidence": missing_evidence,
            "hard_negative_alternatives": self.HARD_NEGATIVE_ALTERNATIVES,
            "claim_ceiling": DDOS_A_CLAIM_CEILING,
            "config_status": self.config.config_status,
            "science_admitted": self.config.science_admitted,
            "state_horizon_seconds": self.config.syn_state_ttl.total_seconds(),
        }
        if statement is not None:
            value["statement"] = statement
        return value

    def _draft(
        self, result_type: ResultType, key: StateKey, state: DdosASynState,
        evidence: dict[str, object], *, missing: tuple[str, ...] = (),
        supporting_ids: tuple[str, ...] = (),
    ) -> ResultDraft:
        return ResultDraft(
            result_type=result_type,
            entity_reference=str(key),
            evidence_items=(),
            missing_prerequisites=missing,
            evidence_interval=(state.first_seen_time, state.last_seen_time),
            evidence=evidence,
            source_observation_ids=supporting_ids,
        )

    def _pending(self, reason: str) -> EvaluationReadinessDecision:
        return EvaluationReadinessDecision(
            EvidenceReadiness.TERMINAL_EVIDENCE_PENDING, reason
        )

    async def process(
        self, observation: NetworkObservation, context: Any,
        state: PluginStateSnapshot | None,
    ) -> PluginProcessOutcome:
        key = self.state_key(observation)
        scope = self._identity_scope(observation)
        visible_tuple = self._normalized_tuple(observation)
        flags = self._flags(observation)
        if key is None or scope is None or visible_tuple is None or flags is None:
            raise ValueError("DDOS-A prerequisites must hold before processing")
        if state is not None and not isinstance(state.payload, DdosASynState):
            raise TypeError("DDOS-A state payload has an unexpected type")
        prior = None if state is None else state.payload
        if prior is not None and prior.config_hash != self.config.canonical_hash:
            raise ValueError("DDOS-A state configuration provenance mismatch")

        direction = observation.wire_direction
        is_synack = flags == frozenset({"SYN", "ACK"}) and direction is WireDirection.REVERSE
        is_initial_syn = "SYN" in flags and "ACK" not in flags and direction is WireDirection.FORWARD
        is_final_ack = "ACK" in flags and "SYN" not in flags and direction is WireDirection.FORWARD
        is_rst = "RST" in flags

        if prior is None and is_initial_syn and not is_rst:
            target_ref, service_ref = scope
            signature = self._sequence_signature(observation, visible_tuple, flags)
            both_visible = all(
                observation.visibility.state(capability) is CapabilityState.AVAILABLE
                for capability in (
                    VisibilityCapability.FORWARD_FACTS,
                    VisibilityCapability.REVERSE_FACTS,
                )
            )
            next_state = DdosASynState(
                phase="SYN_SEEN", target_ref=target_ref, service_ref=service_ref,
                normalized_tuple=visible_tuple,
                first_seen_time=observation.event_time,
                last_seen_time=observation.event_time,
                initiating_syn_observation_id=observation.observation_id,
                synack_observation_id=None, ack_observation_id=None,
                rst_observation_id=None, raw_syn_observations=1,
                recognized_retransmissions=0,
                retransmission_deduplication_available=signature is not None,
                reverse_visibility_available_at_start=both_visible,
                source_visibility=self._visibility(observation),
                capture_quality=self._quality(observation),
                quality_degraded=(self._observation_degraded(observation)
                                  or bool(context.get("quality_degraded", False))),
                midstream_or_unknown_history=False,
                initial_syn_signature=signature,
                config_hash=self.config.canonical_hash,
            )
            evidence = self._evidence(
                next_state, state_before="UNKNOWN", state_after="SYN_SEEN",
                evidence_kind="SYN_ARRIVAL_FACT", direction=direction.value,
                statement="Initiating TCP SYN was observed.",
            )
            return PluginProcessOutcome(
                result_drafts=(self._draft(
                    ResultType.REVIEW_FINDING, key, next_state, evidence
                ),),
                state_transition=StateTransitionRequest(
                    key, None, StateOperation.UPSERT, next_state,
                    self.config.syn_state_ttl,
                ),
                evaluation_readiness=self._pending(
                    "awaiting an observed transition or state expiry"
                ),
            )

        if prior is None:
            target_ref, service_ref = scope
            transient = DdosASynState(
                phase="UNKNOWN", target_ref=target_ref, service_ref=service_ref,
                normalized_tuple=visible_tuple,
                first_seen_time=observation.event_time,
                last_seen_time=observation.event_time,
                initiating_syn_observation_id="",
                synack_observation_id=None, ack_observation_id=None,
                rst_observation_id=None, raw_syn_observations=0,
                recognized_retransmissions=0,
                retransmission_deduplication_available=False,
                reverse_visibility_available_at_start=False,
                source_visibility=self._visibility(observation),
                capture_quality=self._quality(observation),
                quality_degraded=self._observation_degraded(observation),
                midstream_or_unknown_history=True,
                initial_syn_signature=None,
                config_hash=self.config.canonical_hash,
            )
            evidence = self._evidence(
                transient, state_before="UNKNOWN", state_after="UNKNOWN",
                evidence_kind="TCP_STATE_HISTORY_INSUFFICIENT",
                direction=direction.value,
                missing_evidence=("initiating SYN / prior history",),
                statement=(
                    "A TCP state flag was observed without the prerequisite "
                    "visible initiating-SYN history."
                ),
            )
            return PluginProcessOutcome(
                result_drafts=(self._draft(
                    ResultType.INSUFFICIENT_EVIDENCE, key, transient, evidence,
                    missing=("initiating SYN / prior history",),
                ),),
                evaluation_readiness=EvaluationReadinessDecision(
                    EvidenceReadiness.ABSTAINING,
                    "history/midstream prerequisite missing",
                ),
            )

        degraded = (
            prior.quality_degraded or self._observation_degraded(observation)
            or bool(context.get("quality_degraded", False))
        )
        if is_rst:
            terminal = replace(
                prior, phase="RST_SEEN", last_seen_time=observation.event_time,
                rst_observation_id=observation.observation_id,
                capture_quality=self._merge_quality(
                    prior.capture_quality, observation
                ),
                quality_degraded=degraded,
            )
            evidence = self._evidence(
                terminal, state_before=prior.phase, state_after="RST_SEEN",
                evidence_kind="CAPTURED_TCP_RESET_FACT",
                direction=direction.value,
                statement="Captured TCP reset was observed.",
            )
            return PluginProcessOutcome(
                result_drafts=(self._draft(
                    ResultType.REVIEW_FINDING, key, terminal, evidence,
                    supporting_ids=self._supporting_ids(prior),
                ),),
                state_transition=StateTransitionRequest(
                    key, state.version, StateOperation.DELETE
                ),
                evaluation_readiness=EvaluationReadinessDecision(
                    EvidenceReadiness.READY, "captured reset terminal fact observed"
                ),
            )

        if is_initial_syn:
            signature = self._sequence_signature(observation, visible_tuple, flags)
            recognized = (
                signature is not None
                and prior.initial_syn_signature is not None
                and signature == prior.initial_syn_signature
            )
            updated = replace(
                prior,
                last_seen_time=observation.event_time,
                raw_syn_observations=prior.raw_syn_observations + 1,
                recognized_retransmissions=(
                    prior.recognized_retransmissions + int(recognized)
                ),
                retransmission_deduplication_available=(
                    prior.retransmission_deduplication_available
                    and signature is not None
                ),
                capture_quality=self._merge_quality(
                    prior.capture_quality, observation
                ),
                quality_degraded=degraded,
            )
            status = (
                "AVAILABLE_RETRANSMISSION_RECOGNIZED" if recognized
                else "AVAILABLE_NO_EXACT_MATCH" if signature is not None
                else "UNAVAILABLE"
            )
            evidence = self._evidence(
                updated, state_before=prior.phase, state_after=prior.phase,
                evidence_kind="SYN_ARRIVAL_FACT", direction=direction.value,
                statement="Additional initiating TCP SYN observation was retained.",
                dedupe_status=status,
            )
            elapsed = observation.event_time - prior.first_seen_time
            remaining = max(
                self.config.syn_state_ttl - elapsed, timedelta(microseconds=1)
            )
            return PluginProcessOutcome(
                result_drafts=(self._draft(
                    ResultType.REVIEW_FINDING, key, updated, evidence,
                    supporting_ids=self._supporting_ids(prior),
                ),),
                state_transition=StateTransitionRequest(
                    key, state.version, StateOperation.UPSERT, updated, remaining
                ),
                evaluation_readiness=self._pending(
                    "awaiting an observed transition or state expiry"
                ),
            )

        if is_synack and prior.phase == "SYN_SEEN":
            updated = replace(
                prior, phase="SYNACK_SEEN",
                last_seen_time=observation.event_time,
                synack_observation_id=observation.observation_id,
                capture_quality=self._merge_quality(
                    prior.capture_quality, observation
                ),
                quality_degraded=degraded,
            )
            evidence = self._evidence(
                updated, state_before="SYN_SEEN", state_after="SYNACK_SEEN",
                evidence_kind="CAPTURED_SYNACK_TRANSITION_FACT",
                direction=direction.value,
                statement="Captured response to the visible initiating SYN was observed.",
            )
            elapsed = observation.event_time - prior.first_seen_time
            remaining = max(
                self.config.syn_state_ttl - elapsed, timedelta(microseconds=1)
            )
            return PluginProcessOutcome(
                result_drafts=(self._draft(
                    ResultType.REVIEW_FINDING, key, updated, evidence,
                    supporting_ids=self._supporting_ids(prior),
                ),),
                state_transition=StateTransitionRequest(
                    key, state.version, StateOperation.UPSERT, updated, remaining
                ),
                evaluation_readiness=self._pending(
                    "awaiting final ACK, reset, or state expiry"
                ),
            )

        if is_final_ack and prior.phase == "SYNACK_SEEN":
            terminal = replace(
                prior, phase="ACK_SEEN", last_seen_time=observation.event_time,
                ack_observation_id=observation.observation_id,
                capture_quality=self._merge_quality(
                    prior.capture_quality, observation
                ),
                quality_degraded=degraded,
            )
            evidence = self._evidence(
                terminal, state_before="SYNACK_SEEN", state_after="ACK_SEEN",
                evidence_kind="CAPTURED_TCP_HANDSHAKE_PROGRESSION_FACT",
                direction=direction.value,
                statement="Captured three-way TCP handshake progression observed.",
            )
            return PluginProcessOutcome(
                result_drafts=(self._draft(
                    ResultType.REVIEW_FINDING, key, terminal, evidence,
                    supporting_ids=self._supporting_ids(prior),
                ),),
                state_transition=StateTransitionRequest(
                    key, state.version, StateOperation.DELETE
                ),
                evaluation_readiness=EvaluationReadinessDecision(
                    EvidenceReadiness.READY,
                    "captured handshake progression terminal fact observed",
                ),
            )

        evidence = self._evidence(
            prior, state_before=prior.phase, state_after=prior.phase,
            evidence_kind="TCP_STATE_TRANSITION_INSUFFICIENT",
            direction=direction.value,
            missing_evidence=("required prior phase and declared packet direction",),
            statement="Observed flags do not establish the required next TCP state transition.",
        )
        return PluginProcessOutcome(
            result_drafts=(self._draft(
                ResultType.INSUFFICIENT_EVIDENCE, key, prior, evidence,
                missing=("required prior phase and declared packet direction",),
                supporting_ids=self._supporting_ids(prior),
            ),),
            evaluation_readiness=self._pending(
                "required state transition was not established"
            ),
        )

    async def on_expire(
        self, key: StateKey, context: Any, state: PluginStateSnapshot
    ) -> PluginProcessOutcome:
        if not isinstance(state.payload, DdosASynState):
            raise TypeError("DDOS-A expired state payload has an unexpected type")
        value = state.payload
        if value.config_hash != self.config.canonical_hash:
            raise ValueError("DDOS-A expired state configuration provenance mismatch")
        degraded = value.quality_degraded or bool(context.get("quality_degraded", False))
        supporting = self._supporting_ids(value)
        if degraded:
            result_type = ResultType.QUALITY_DEGRADED
            kind = "TCP_SYN_STATE_QUALITY_DEGRADED"
            missing = ("reliable captured TCP state evidence",)
            statement = (
                "Initiating SYN was observed; degraded capture quality can remove "
                "subsequent TCP state packets."
            )
        elif not value.reverse_visibility_available_at_start:
            result_type = ResultType.INSUFFICIENT_EVIDENCE
            kind = "REVERSE_TCP_STATE_UNOBSERVABLE"
            missing = ("reverse TCP state evidence",)
            statement = (
                "Initiating SYN was observed; reverse completion state is not "
                "observable from this source contract."
            )
        else:
            result_type = ResultType.REVIEW_FINDING
            kind = "CAPTURED_INCOMPLETE_SYN_STATE_EVIDENCE"
            missing = ()
            statement = (
                "Captured TCP attempt did not reach an observed completed handshake "
                "state within the controlled POC state horizon."
            )
        evidence = self._evidence(
            value, state_before=value.phase, state_after="EXPIRED",
            evidence_kind=kind, direction=None, missing_evidence=missing,
            statement=statement,
        )
        evidence["runtime_or_state_quality_degraded"] = degraded
        return PluginProcessOutcome(result_drafts=(self._draft(
            result_type, key, value, evidence, missing=missing,
            supporting_ids=supporting,
        ),))

    async def on_watermark(
        self, watermark: datetime, context: Any
    ) -> PluginProcessOutcome:
        return PluginProcessOutcome()

    async def on_quality_gap(
        self, gap: QualityGap, context: Any, state: Any
    ) -> Sequence[ResultDraft]:
        return ()
