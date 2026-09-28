from datetime import datetime
from typing import Any, Sequence

from evidencegate.domain.enums import (
    AnalyticFamily,
    AvailabilityBasis,
    Finality,
    GapAction,
    IntegrationStatus,
    ObservationType,
    OfficialPsCategory,
    ResultType,
    VisibilityCapability,
)
from evidencegate.domain.events import NetworkObservation
from evidencegate.domain.quality import QualityGap
from evidencegate.registry.manifest import PluginManifest
from evidencegate.registry.plugin import PluginProcessOutcome, PluginStateSnapshot, StateKey
from evidencegate.results.types import ResultDraft
from .common import ProviderShellPlugin


class EncryptedSessionShellPlugin(ProviderShellPlugin):
    plugin_id = "provider.encrypted_session.shell"
    category = OfficialPsCategory.ENCRYPTED_SESSIONS
    family = AnalyticFamily.ENCRYPTED_SESSION
    taxonomy = ("Network", "Encrypted Session", "Provider Shell")
    accepted_types = (ObservationType.TLS, ObservationType.QUIC)
    capabilities_by_type = {
        ObservationType.TLS: frozenset(
            {VisibilityCapability.TLS_HANDSHAKE_METADATA, VisibilityCapability.TLS_RECORD_METADATA}
        ),
        ObservationType.QUIC: frozenset({VisibilityCapability.QUIC_OUTER_METADATA}),
    }


class EncAHandshakePlugin:
    """ENC-A: factual visible TLS ClientHello and fingerprint context only."""

    _manifest = PluginManifest(
        plugin_id="provider.encrypted_session.enc_a",
        plugin_version="0.1.0",
        analytic_version="enc-a-0.1.0",
        taxonomy=("Network", "Encrypted Session", "TLS Handshake Context"),
        accepted_observation_types=(ObservationType.TLS,),
        routing_predicate_version="structural-1",
        admission_requirements=("visible TLS handshake metadata",),
        required_fields=("parsed_handshake_metadata", "parser_version", "flow_reference"),
        required_observation_contracts=(),
        required_visibility_capabilities=frozenset({VisibilityCapability.TLS_HANDSHAKE_METADATA}),
        required_quality=(),
        allowed_finality=tuple(Finality),
        allowed_availability_basis=tuple(AvailabilityBasis),
        state_key_declaration=None,
        scientific_history_duration=None,
        resource_retention_duration=None,
        gap_action=GapAction.CONTINUE_WITH_QUALITY_FLAG,
        allowed_result_types=(
            ResultType.REVIEW_FINDING,
            ResultType.PREREQUISITE_MISSING,
            ResultType.QUALITY_DEGRADED,
            ResultType.ANALYTIC_UNAVAILABLE,
        ),
        integration_status=IntegrationStatus.BASELINE_IMPLEMENTED,
        profiling_hooks_enabled=False,
        governing_claim_ids=(),
        governing_decision_ids=(),
        official_ps_category=OfficialPsCategory.ENCRYPTED_SESSIONS,
        analytic_family=AnalyticFamily.ENCRYPTED_SESSION,
        mechanism_id="ENC-A",
    )

    def manifest(self) -> PluginManifest:
        return self._manifest

    def route(self, observation: NetworkObservation) -> bool:
        return observation.observation_type is ObservationType.TLS

    def state_key(self, observation: NetworkObservation) -> None:
        return None

    async def process(
        self, observation: NetworkObservation, context: Any, state: PluginStateSnapshot | None
    ) -> PluginProcessOutcome:
        payload = observation.typed_payload
        evidence: dict[str, object] = {
            "evidence_kind": "ENCRYPTED_HANDSHAKE_CONTEXT",
            "protocol": "TLS",
            "flow_reference": payload.flow_reference,
            "parser_version": payload.parser_version,
            "parsed_handshake_metadata": payload.parsed_handshake_metadata,
        }
        if "tcp_reassembly_state" in observation.present_fields:
            evidence["tcp_reassembly_state"] = payload.tcp_reassembly_state
        if "gaps" in observation.present_fields:
            evidence["gaps"] = payload.gaps
        return PluginProcessOutcome(
            (
                ResultDraft(
                    result_type=ResultType.REVIEW_FINDING,
                    entity_reference=payload.flow_reference,
                    evidence_items=(),
                    missing_prerequisites=(),
                    evidence=evidence,
                ),
            )
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
