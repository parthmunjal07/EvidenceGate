"""Bounded factual event-time measurements for the Category-1 DDoS family."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
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

from .ddos_config import (
    DdosConnectionChurnConfig,
    DdosFragmentDemandConfig,
    DdosIcmpDemandConfig,
    DdosReflectionVictimConfig,
    DdosSourceDiversityConfig,
    DdosUdpDemandConfig,
    DdosWindowConfig,
)


DDOS_B_CLAIM_CEILING = (
    "OBSERVED_UDP_DEMAND_ONLY;NO_DDOS_CONFIRMED;NO_SERVICE_IMPACT;"
    "NO_COMPLETION_SEMANTICS;NO_MALICIOUSNESS"
)
DDOS_CV_CLAIM_CEILING = (
    "RESPONSE_SHAPED_TRAFFIC_ONLY;NO_AMPLIFICATION_RATIO;"
    "NO_SPOOFING_CONFIRMED;NO_DDOS_CONFIRMED;NO_ATTACKER_IDENTITY"
)
DDOS_D_CLAIM_CEILING = (
    "APPARENT_SOURCE_DISTRIBUTION_ONLY;NO_SPOOFING_CONFIRMED;"
    "NO_BOTNET_CONFIRMED;NO_DDOS_CONFIRMED;NO_ATTRIBUTION"
)
DDOS_E1_CLAIM_CEILING = (
    "OBSERVED_ICMP_DEMAND_ONLY;NO_DDOS_CONFIRMED;NO_SERVICE_IMPACT;NO_MALICIOUSNESS"
)
DDOS_E2_CLAIM_CEILING = (
    "OBSERVED_FRAGMENTED_PACKET_DEMAND_ONLY;NO_DDOS_CONFIRMED;NO_SERVICE_IMPACT;NO_MALICIOUSNESS"
)
DDOS_E3_CLAIM_CEILING = (
    "OBSERVED_TCP_INITIATING_ATTEMPT_MEASUREMENT_ONLY;NO_DDOS_CONFIRMED;"
    "NO_RESOURCE_EXHAUSTION;NO_SCAN_CLASSIFICATION;NO_MALICIOUSNESS"
)

COMMON_HARD_NEGATIVES = (
    "flash crowd",
    "authorized load test",
    "performance benchmark",
    "backup/update traffic",
    "retry storm",
    "outage recovery",
    "scanner burst",
    "large legitimate UDP",
    "DNS/NTP service burst",
    "CDN",
    "anycast",
    "NAT",
    "load balancer",
    "routing changes",
    "capture overload",
    "sampling/loss",
)


@dataclass(frozen=True, slots=True)
class DdosWindowState:
    """Externally and internally bounded state for one measurement window."""

    mechanism_id: str
    target_ref: str
    service_ref: str
    direction: str
    window_start: datetime
    window_end: datetime
    protocols: tuple[int, ...]
    protocol_context: str | None
    packet_count: int
    measured_byte_count: int
    measured_length_count: int
    missing_length_count: int
    minimum_packet_length: int | None
    maximum_packet_length: int | None
    sources: tuple[str, ...]
    source_capacity_reached: bool
    attempts: tuple[str, ...]
    attempt_capacity_reached: bool
    first_observation_id: str
    last_observation_id: str
    first_seen_time: datetime
    last_seen_time: datetime
    capture_quality: tuple[tuple[str, str], ...]
    source_visibility: tuple[tuple[str, str], ...]
    quality_degraded: bool
    config_hash: str


def _resolve_scope(
    observation: NetworkObservation, config: DdosWindowConfig
) -> tuple[str, str] | None:
    resolved: list[str] = []
    for label in (config.target_role_label, config.service_role_label):
        matches = tuple(
            assignment.identifier
            for assignment in observation.identity.role_assignments
            if assignment.role == label
        )
        if len(matches) != 1 or not matches[0]:
            return None
        resolved.append(matches[0])
    return resolved[0], resolved[1]


def _normalized_tuple(
    observation: NetworkObservation,
) -> tuple[tuple[str, int], tuple[str, int]] | None:
    payload = observation.typed_payload
    values = (
        payload.src_address,
        payload.src_port,
        payload.dst_address,
        payload.dst_port,
    )
    if (
        not isinstance(values[0], str)
        or not values[0]
        or isinstance(values[1], bool)
        or not isinstance(values[1], int)
        or not isinstance(values[2], str)
        or not values[2]
        or isinstance(values[3], bool)
        or not isinstance(values[3], int)
    ):
        return None
    endpoints = ((values[0], values[1]), (values[2], values[3]))
    return tuple(sorted(endpoints, key=lambda item: (item[0], item[1])))  # type: ignore[return-value]


def _quality(observation: NetworkObservation) -> tuple[tuple[str, str], ...]:
    return (
        ("packet_loss", observation.quality.packet_loss.value),
        ("sampling", observation.quality.sampling.value),
        ("parser", observation.quality.parser.value),
        ("capture_gap", observation.quality.capture_gap.value),
    )


def _merge_quality(
    prior: tuple[tuple[str, str], ...], observation: NetworkObservation
) -> tuple[tuple[str, str], ...]:
    current = dict(_quality(observation))
    merged: list[tuple[str, str]] = []
    for name, previous in prior:
        values = {previous, current[name]}
        if QualityState.DEGRADED.value in values:
            value = QualityState.DEGRADED.value
        elif QualityState.UNKNOWN.value in values:
            value = QualityState.UNKNOWN.value
        else:
            value = QualityState.CLEAR.value
        merged.append((name, value))
    return tuple(merged)


def _degraded(observation: NetworkObservation) -> bool:
    return QualityState.DEGRADED in (
        observation.quality.packet_loss,
        observation.quality.sampling,
        observation.quality.parser,
        observation.quality.capture_gap,
    )


def _visibility(observation: NetworkObservation) -> tuple[tuple[str, str], ...]:
    return tuple(
        (capability.value, observation.visibility.state(capability).value)
        for capability in (
            VisibilityCapability.FORWARD_FACTS,
            VisibilityCapability.REVERSE_FACTS,
        )
    )


def _window_bounds(event_time: datetime, duration: timedelta) -> tuple[datetime, datetime]:
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    value = event_time.astimezone(timezone.utc)
    elapsed = value - epoch
    elapsed_us = elapsed.days * 86_400_000_000 + elapsed.seconds * 1_000_000 + elapsed.microseconds
    window_us = int(duration.total_seconds() * 1_000_000)
    start = epoch + timedelta(microseconds=(elapsed_us // window_us) * window_us)
    return start, start + duration


def _packet_length(observation: NetworkObservation, key: str) -> int | None:
    if "lengths" not in observation.present_fields:
        return None
    value = observation.typed_payload.lengths.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


class _DdosWindowPlugin:
    mechanism_id = ""
    plugin_id = ""
    analytic_version = ""
    taxonomy_label = ""
    evidence_kind = ""
    claim_ceiling = ""
    required_fields: tuple[str, ...] = ("protocol",)
    source_tracking = False
    attempt_tracking = False

    def __init__(
        self,
        config: DdosWindowConfig,
        *,
        max_state_entries: int,
        max_sources_per_window: int | None = None,
        max_attempts_per_window: int | None = None,
        governing_decision_ids: tuple[str, ...] = (),
    ) -> None:
        if not isinstance(config, DdosWindowConfig):
            raise TypeError("config must be a DdosWindowConfig")
        self._positive_integer(max_state_entries, "max_state_entries")
        if self.source_tracking:
            self._positive_integer(max_sources_per_window, "max_sources_per_window")
        elif max_sources_per_window is not None:
            raise ValueError("max_sources_per_window is not used by this mechanism")
        if self.attempt_tracking:
            self._positive_integer(max_attempts_per_window, "max_attempts_per_window")
        elif max_attempts_per_window is not None:
            raise ValueError("max_attempts_per_window is not used by this mechanism")
        self.config = config
        self.max_sources_per_window = max_sources_per_window
        self.max_attempts_per_window = max_attempts_per_window
        self._manifest = PluginManifest(
            plugin_id=self.plugin_id,
            plugin_version="0.1.0",
            analytic_version=self.analytic_version,
            taxonomy=("Network", "DDoS", self.taxonomy_label),
            accepted_observation_types=(ObservationType.PACKET,),
            routing_predicate_version=f"{self.mechanism_id.lower()}-factual-window-v1",
            admission_requirements=(
                "known explicit wire direction",
                "unique trusted target_id and service_id role assignments",
                "explicit canonical protocol and mechanism facts",
            ),
            required_fields=self.required_fields,
            required_observation_contracts=(),
            required_visibility_capabilities=frozenset({VisibilityCapability.PACKET_FACTS}),
            required_quality=(),
            allowed_finality=tuple(Finality),
            allowed_availability_basis=tuple(AvailabilityBasis),
            state_key_declaration=self._state_key_declaration(),
            scientific_history_duration=(
                f"controlled POC measurement window {config.measurement_window}"
            ),
            resource_retention_duration=str(config.measurement_window),
            gap_action=GapAction.CONTINUE_WITH_QUALITY_FLAG,
            allowed_result_types=(ResultType.REVIEW_FINDING, ResultType.QUALITY_DEGRADED),
            integration_status=IntegrationStatus.BASELINE_IMPLEMENTED,
            profiling_hooks_enabled=False,
            governing_claim_ids=(),
            governing_decision_ids=governing_decision_ids,
            official_ps_category=OfficialPsCategory.DDOS,
            analytic_family=AnalyticFamily.DDOS,
            mechanism_id=self.mechanism_id,
            state_resource_policy=StateResourcePolicy(
                max_entries=max_state_entries,
                max_ttl=config.measurement_window,
            ),
            config_hash=config.canonical_hash,
        )

    @staticmethod
    def _positive_integer(value: object, name: str) -> None:
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{name} must be a non-bool integer")
        if value <= 0:
            raise ValueError(f"{name} must be greater than zero")

    def manifest(self) -> PluginManifest:
        return self._manifest

    def _state_key_declaration(self) -> str:
        return "target x service x direction x event-time window"

    def _route_specific(self, observation: NetworkObservation) -> bool:
        raise NotImplementedError

    def _key_extra(self, observation: NetworkObservation) -> tuple[object, ...]:
        return ()

    def _protocol_context(self, observation: NetworkObservation) -> str | None:
        return None

    def _source_value(self, observation: NetworkObservation) -> str | None:
        return None

    def _attempt_value(self, observation: NetworkObservation) -> str | None:
        return None

    def _extra_evidence(self, state: DdosWindowState) -> dict[str, object]:
        return {}

    def route(self, observation: NetworkObservation) -> bool:
        if observation.observation_type is not ObservationType.PACKET:
            return False
        if any(name not in observation.present_fields for name in self.required_fields):
            return False
        if observation.wire_direction is WireDirection.UNKNOWN:
            return False
        protocol = observation.typed_payload.protocol
        if isinstance(protocol, bool) or not isinstance(protocol, int):
            return False
        if not 0 <= protocol <= 255:
            return False
        if _resolve_scope(observation, self.config) is None:
            return False
        return self._route_specific(observation)

    def state_key(self, observation: NetworkObservation) -> StateKey | None:
        if not self.route(observation):
            return None
        target_ref, service_ref = _resolve_scope(observation, self.config)  # type: ignore[misc]
        start, _ = _window_bounds(observation.event_time, self.config.measurement_window)
        return StateKey(
            json.dumps(
                [
                    target_ref,
                    service_ref,
                    observation.wire_direction.value,
                    start.isoformat(),
                    *self._key_extra(observation),
                ],
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )

    def _new_state(self, observation: NetworkObservation, context: Any) -> DdosWindowState:
        target_ref, service_ref = _resolve_scope(observation, self.config)  # type: ignore[misc]
        start, end = _window_bounds(observation.event_time, self.config.measurement_window)
        length = _packet_length(observation, self.config.packet_length_key)
        source = self._source_value(observation)
        attempt = self._attempt_value(observation)
        return DdosWindowState(
            mechanism_id=self.mechanism_id,
            target_ref=target_ref,
            service_ref=service_ref,
            direction=observation.wire_direction.value,
            window_start=start,
            window_end=end,
            protocols=(observation.typed_payload.protocol,),
            protocol_context=self._protocol_context(observation),
            packet_count=1,
            measured_byte_count=0 if length is None else length,
            measured_length_count=0 if length is None else 1,
            missing_length_count=1 if length is None else 0,
            minimum_packet_length=length,
            maximum_packet_length=length,
            sources=(() if source is None else (source,)),
            source_capacity_reached=False,
            attempts=(() if attempt is None else (attempt,)),
            attempt_capacity_reached=False,
            first_observation_id=observation.observation_id,
            last_observation_id=observation.observation_id,
            first_seen_time=observation.event_time,
            last_seen_time=observation.event_time,
            capture_quality=_quality(observation),
            source_visibility=_visibility(observation),
            quality_degraded=(
                _degraded(observation) or bool(context.get("quality_degraded", False))
            ),
            config_hash=self.config.canonical_hash,
        )

    def _updated_state(
        self, prior: DdosWindowState, observation: NetworkObservation, context: Any
    ) -> DdosWindowState:
        length = _packet_length(observation, self.config.packet_length_key)
        sources = prior.sources
        source_capacity_reached = prior.source_capacity_reached
        source = self._source_value(observation)
        if source is not None and source not in sources:
            if len(sources) < self.max_sources_per_window:  # type: ignore[operator]
                sources = tuple(sorted((*sources, source)))
            else:
                source_capacity_reached = True
        attempts = prior.attempts
        attempt_capacity_reached = prior.attempt_capacity_reached
        attempt = self._attempt_value(observation)
        if attempt is not None and attempt not in attempts:
            if len(attempts) < self.max_attempts_per_window:  # type: ignore[operator]
                attempts = tuple(sorted((*attempts, attempt)))
            else:
                attempt_capacity_reached = True
        protocols = tuple(sorted(set((*prior.protocols, observation.typed_payload.protocol))))
        return DdosWindowState(
            mechanism_id=prior.mechanism_id,
            target_ref=prior.target_ref,
            service_ref=prior.service_ref,
            direction=prior.direction,
            window_start=prior.window_start,
            window_end=prior.window_end,
            protocols=protocols,
            protocol_context=prior.protocol_context,
            packet_count=prior.packet_count + 1,
            measured_byte_count=(prior.measured_byte_count + (0 if length is None else length)),
            measured_length_count=(prior.measured_length_count + (0 if length is None else 1)),
            missing_length_count=(prior.missing_length_count + (1 if length is None else 0)),
            minimum_packet_length=(
                prior.minimum_packet_length
                if length is None
                else length
                if prior.minimum_packet_length is None
                else min(prior.minimum_packet_length, length)
            ),
            maximum_packet_length=(
                prior.maximum_packet_length
                if length is None
                else length
                if prior.maximum_packet_length is None
                else max(prior.maximum_packet_length, length)
            ),
            sources=sources,
            source_capacity_reached=source_capacity_reached,
            attempts=attempts,
            attempt_capacity_reached=attempt_capacity_reached,
            first_observation_id=prior.first_observation_id,
            last_observation_id=observation.observation_id,
            first_seen_time=prior.first_seen_time,
            last_seen_time=observation.event_time,
            capture_quality=_merge_quality(prior.capture_quality, observation),
            source_visibility=prior.source_visibility,
            quality_degraded=(
                prior.quality_degraded
                or _degraded(observation)
                or bool(context.get("quality_degraded", False))
            ),
            config_hash=prior.config_hash,
        )

    async def process(
        self,
        observation: NetworkObservation,
        context: Any,
        state: PluginStateSnapshot | None,
    ) -> PluginProcessOutcome:
        key = self.state_key(observation)
        if key is None:
            raise ValueError(f"{self.mechanism_id} prerequisites must hold")
        if state is not None and not isinstance(state.payload, DdosWindowState):
            raise TypeError(f"{self.mechanism_id} state payload has an unexpected type")
        if state is not None and state.payload.config_hash != self.config.canonical_hash:
            raise ValueError(f"{self.mechanism_id} state configuration mismatch")
        next_state = (
            self._new_state(observation, context)
            if state is None
            else self._updated_state(state.payload, observation, context)
        )
        remaining = next_state.window_end - observation.event_time
        if remaining <= timedelta(0):
            raise ValueError("event does not fall before its computed window end")
        return PluginProcessOutcome(
            state_transition=StateTransitionRequest(
                key=key,
                expected_version=None if state is None else state.version,
                operation=StateOperation.UPSERT,
                payload=next_state,
                ttl=remaining,
            ),
            evaluation_readiness=EvaluationReadinessDecision(
                EvidenceReadiness.TERMINAL_EVIDENCE_PENDING,
                "measurement becomes available when watermark passes window end",
            ),
        )

    def _evidence(self, state: DdosWindowState, degraded: bool) -> dict[str, object]:
        complete_lengths = state.missing_length_count == 0
        missing: list[str] = []
        if not complete_lengths:
            missing.append(f"{self.config.packet_length_key} packet length for every observation")
        if degraded:
            missing.append("complete unsampled/loss-free observation coverage")
        if state.source_capacity_reached:
            missing.append("additional apparent sources beyond engineering capacity")
        if state.attempt_capacity_reached:
            missing.append("additional visible tuples beyond engineering capacity")
        evidence: dict[str, object] = {
            "analytic_path": self.mechanism_id,
            "evidence_kind": self.evidence_kind,
            "target_ref": state.target_ref,
            "service_ref": state.service_ref,
            "direction": state.direction,
            "protocols": state.protocols,
            "protocol_context": state.protocol_context,
            "window_start": state.window_start,
            "window_end": state.window_end,
            "packet_count": state.packet_count,
            "byte_count": state.measured_byte_count if complete_lengths else None,
            "observed_byte_count_for_length_available_packets": (state.measured_byte_count),
            "measured_length_count": state.measured_length_count,
            "missing_length_count": state.missing_length_count,
            "mean_packet_length": (
                state.measured_byte_count / state.measured_length_count
                if complete_lengths and state.measured_length_count
                else None
            ),
            "minimum_packet_length": (state.minimum_packet_length if complete_lengths else None),
            "maximum_packet_length": (state.maximum_packet_length if complete_lengths else None),
            "measurement_is_lower_bound": degraded,
            "capture_quality": dict(state.capture_quality),
            "source_visibility": dict(state.source_visibility),
            "source_capacity_reached": state.source_capacity_reached,
            "attempt_capacity_reached": state.attempt_capacity_reached,
            "missing_evidence": tuple(missing),
            "hard_negative_alternatives": COMMON_HARD_NEGATIVES,
            "claim_ceiling": self.claim_ceiling,
            "config_status": self.config.config_status,
            "science_admitted": self.config.science_admitted,
            "measurement_window_seconds": self.config.measurement_window.total_seconds(),
        }
        evidence.update(self._extra_evidence(state))
        return evidence

    async def on_expire(
        self, key: StateKey, context: Any, state: PluginStateSnapshot
    ) -> PluginProcessOutcome:
        if not isinstance(state.payload, DdosWindowState):
            raise TypeError(f"{self.mechanism_id} expired state has unexpected type")
        value = state.payload
        degraded = (
            value.quality_degraded
            or value.source_capacity_reached
            or value.attempt_capacity_reached
            or bool(context.get("quality_degraded", False))
        )
        result_type = ResultType.QUALITY_DEGRADED if degraded else ResultType.REVIEW_FINDING
        supporting = tuple(dict.fromkeys((value.first_observation_id, value.last_observation_id)))
        evidence = self._evidence(value, degraded)
        missing = tuple(evidence["missing_evidence"])  # type: ignore[arg-type]
        return PluginProcessOutcome(
            result_drafts=(
                ResultDraft(
                    result_type=result_type,
                    entity_reference=str(key),
                    evidence_items=(),
                    missing_prerequisites=missing,
                    evidence_interval=(value.window_start, value.window_end),
                    evidence=evidence,
                    source_observation_ids=supporting,
                ),
            )
        )

    async def on_watermark(self, watermark: datetime, context: Any) -> PluginProcessOutcome:
        return PluginProcessOutcome()

    async def on_quality_gap(
        self, gap: QualityGap, context: Any, state: Any
    ) -> Sequence[ResultDraft]:
        return ()


class DdosUdpDemandPlugin(_DdosWindowPlugin):
    mechanism_id = "DDOS-B-B0"
    plugin_id = "provider.ddos.udp_demand"
    analytic_version = "ddos-b-b0-0.1.0"
    taxonomy_label = "UDP Demand Measurement"
    evidence_kind = "UDP_DEMAND_MEASUREMENT"
    claim_ceiling = DDOS_B_CLAIM_CEILING

    def __init__(self, config: DdosUdpDemandConfig, **kwargs: Any) -> None:
        if not isinstance(config, DdosUdpDemandConfig):
            raise TypeError("config must be DdosUdpDemandConfig")
        super().__init__(config, **kwargs)

    def _route_specific(self, observation: NetworkObservation) -> bool:
        return observation.typed_payload.protocol == 17


class DdosReflectionVictimPlugin(_DdosWindowPlugin):
    """Victim-side response shape using DDOS_REFLECTION_FACT_V1 only."""

    mechanism_id = "DDOS-CV-B0"
    plugin_id = "provider.ddos.reflection_victim"
    analytic_version = "ddos-cv-b0-0.1.0"
    taxonomy_label = "Victim Reflection Shape"
    evidence_kind = "REFLECTION_CONSISTENT_TRAFFIC_SHAPE"
    claim_ceiling = DDOS_CV_CLAIM_CEILING
    required_fields = ("protocol", "observed_l4_facts", "src_address")
    source_tracking = True

    def __init__(self, config: DdosReflectionVictimConfig, **kwargs: Any) -> None:
        if not isinstance(config, DdosReflectionVictimConfig):
            raise TypeError("config must be DdosReflectionVictimConfig")
        super().__init__(config, **kwargs)

    def _facts(self, observation: NetworkObservation) -> tuple[bool, str | None]:
        facts = observation.typed_payload.observed_l4_facts
        if not isinstance(facts, dict):
            return False, None
        if set(facts) != {"fact_contract", "response_like", "protocol_context"}:
            return False, None
        context = facts.get("protocol_context")
        valid = (
            facts.get("fact_contract") == "DDOS_REFLECTION_FACT_V1"
            and facts.get("response_like") is True
            and isinstance(context, str)
            and bool(context.strip())
        )
        return valid, context if valid else None

    def _route_specific(self, observation: NetworkObservation) -> bool:
        valid, _ = self._facts(observation)
        return (
            observation.typed_payload.protocol == 17
            and observation.wire_direction is WireDirection.FORWARD
            and valid
            and isinstance(observation.typed_payload.src_address, str)
            and bool(observation.typed_payload.src_address)
        )

    def _key_extra(self, observation: NetworkObservation) -> tuple[object, ...]:
        return (self._facts(observation)[1],)

    def _protocol_context(self, observation: NetworkObservation) -> str | None:
        return self._facts(observation)[1]

    def _source_value(self, observation: NetworkObservation) -> str | None:
        value = observation.typed_payload.src_address
        return value if isinstance(value, str) and value else None

    def _extra_evidence(self, state: DdosWindowState) -> dict[str, object]:
        return {
            "response_shaped_packet_count": state.packet_count,
            "apparent_source_cardinality_lower_bound": len(state.sources),
            "reflection_fact_contract": "DDOS_REFLECTION_FACT_V1",
            "independent_victim_impact": None,
            "source_authenticity": None,
            "reflector_request": None,
        }


class DdosSourceDiversityPlugin(_DdosWindowPlugin):
    mechanism_id = "DDOS-D-B0"
    plugin_id = "provider.ddos.source_diversity"
    analytic_version = "ddos-d-b0-0.1.0"
    taxonomy_label = "Apparent Source Distribution"
    evidence_kind = "APPARENT_SOURCE_DISTRIBUTION_MEASUREMENT"
    claim_ceiling = DDOS_D_CLAIM_CEILING
    required_fields = ("protocol", "src_address")
    source_tracking = True

    def __init__(self, config: DdosSourceDiversityConfig, **kwargs: Any) -> None:
        if not isinstance(config, DdosSourceDiversityConfig):
            raise TypeError("config must be DdosSourceDiversityConfig")
        super().__init__(config, **kwargs)

    def _route_specific(self, observation: NetworkObservation) -> bool:
        value = observation.typed_payload.src_address
        return isinstance(value, str) and bool(value)

    def _source_value(self, observation: NetworkObservation) -> str | None:
        return observation.typed_payload.src_address

    def _extra_evidence(self, state: DdosWindowState) -> dict[str, object]:
        return {
            "apparent_source_cardinality_lower_bound": len(state.sources),
            "exact_within_engineering_capacity": not state.source_capacity_reached,
        }


class DdosIcmpDemandPlugin(_DdosWindowPlugin):
    mechanism_id = "DDOS-E1-B0"
    plugin_id = "provider.ddos.icmp_demand"
    analytic_version = "ddos-e1-b0-0.1.0"
    taxonomy_label = "ICMP Demand Measurement"
    evidence_kind = "ICMP_DEMAND_MEASUREMENT"
    claim_ceiling = DDOS_E1_CLAIM_CEILING

    def __init__(self, config: DdosIcmpDemandConfig, **kwargs: Any) -> None:
        if not isinstance(config, DdosIcmpDemandConfig):
            raise TypeError("config must be DdosIcmpDemandConfig")
        super().__init__(config, **kwargs)

    def _route_specific(self, observation: NetworkObservation) -> bool:
        return observation.typed_payload.protocol == 1


class DdosFragmentDemandPlugin(_DdosWindowPlugin):
    """Fragment demand using the explicit DDOS_FRAGMENT_FACT_V1 mini-contract."""

    mechanism_id = "DDOS-E2-B0"
    plugin_id = "provider.ddos.fragment_demand"
    analytic_version = "ddos-e2-b0-0.1.0"
    taxonomy_label = "Fragment Demand Measurement"
    evidence_kind = "FRAGMENT_DEMAND_MEASUREMENT"
    claim_ceiling = DDOS_E2_CLAIM_CEILING
    required_fields = ("protocol", "fragmentation")

    def __init__(self, config: DdosFragmentDemandConfig, **kwargs: Any) -> None:
        if not isinstance(config, DdosFragmentDemandConfig):
            raise TypeError("config must be DdosFragmentDemandConfig")
        super().__init__(config, **kwargs)

    def _route_specific(self, observation: NetworkObservation) -> bool:
        facts = observation.typed_payload.fragmentation
        if not isinstance(facts, dict):
            return False
        if set(facts) - {"fact_contract", "is_fragment", "offset", "more_fragments"}:
            return False
        if facts.get("fact_contract") != "DDOS_FRAGMENT_FACT_V1":
            return False
        if facts.get("is_fragment") is not True:
            return False
        offset = facts.get("offset")
        more = facts.get("more_fragments")
        return (
            offset is None
            or (not isinstance(offset, bool) and isinstance(offset, int) and offset >= 0)
        ) and (more is None or isinstance(more, bool))

    def _key_extra(self, observation: NetworkObservation) -> tuple[object, ...]:
        return (observation.typed_payload.protocol,)

    def _extra_evidence(self, state: DdosWindowState) -> dict[str, object]:
        return {
            "fragmented_packet_count": state.packet_count,
            "fragment_fact_contract": "DDOS_FRAGMENT_FACT_V1",
        }


class DdosConnectionChurnPlugin(_DdosWindowPlugin):
    mechanism_id = "DDOS-E3-B0"
    plugin_id = "provider.ddos.connection_churn"
    analytic_version = "ddos-e3-b0-0.1.0"
    taxonomy_label = "TCP Initiating Attempt Measurement"
    evidence_kind = "TCP_INITIATING_ATTEMPT_MEASUREMENT"
    claim_ceiling = DDOS_E3_CLAIM_CEILING
    required_fields = (
        "protocol",
        "src_address",
        "dst_address",
        "src_port",
        "dst_port",
        "flags",
    )
    attempt_tracking = True

    def __init__(self, config: DdosConnectionChurnConfig, **kwargs: Any) -> None:
        if not isinstance(config, DdosConnectionChurnConfig):
            raise TypeError("config must be DdosConnectionChurnConfig")
        super().__init__(config, **kwargs)

    def _route_specific(self, observation: NetworkObservation) -> bool:
        flags = observation.typed_payload.flags
        return (
            observation.typed_payload.protocol == 6
            and observation.wire_direction is WireDirection.FORWARD
            and isinstance(flags, list)
            and all(isinstance(flag, str) for flag in flags)
            and "SYN" in flags
            and "ACK" not in flags
            and "RST" not in flags
            and _normalized_tuple(observation) is not None
        )

    def _attempt_value(self, observation: NetworkObservation) -> str | None:
        value = _normalized_tuple(observation)
        return None if value is None else json.dumps(value, separators=(",", ":"))

    def _extra_evidence(self, state: DdosWindowState) -> dict[str, object]:
        return {
            "observed_initiating_syn_count": state.packet_count,
            "unique_visible_tuple_count_lower_bound": len(state.attempts),
            "exact_within_engineering_capacity": not state.attempt_capacity_reached,
        }
