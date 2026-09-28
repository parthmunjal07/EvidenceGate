from datetime import datetime
from typing import Any, Sequence

from evidencegate.domain.enums import (
    AnalyticFamily,
    AvailabilityBasis,
    CapabilityState,
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


class DgaShellPlugin(ProviderShellPlugin):
    plugin_id = "provider.dga.shell"
    category = OfficialPsCategory.DGA_AND_DNS_TUNNELLING
    family = AnalyticFamily.DGA
    taxonomy = ("Network", "DGA", "Provider Shell")
    accepted_types = (ObservationType.DNS,)
    capabilities_by_type = {ObservationType.DNS: frozenset({VisibilityCapability.CLEAR_DNS_FIELDS})}


class DnsT1StructuralPlugin:
    """DNS-T1: one-observation name/message structure, never a tunnel verdict."""

    _manifest = PluginManifest(
        plugin_id="provider.dns_tunnelling.t1",
        plugin_version="0.1.0",
        analytic_version="dns-t1-0.1.0",
        taxonomy=("Network", "DNS Tunnelling", "DNS Name Structure"),
        accepted_observation_types=(ObservationType.DNS,),
        routing_predicate_version="dns-name-representation-v1",
        admission_requirements=("clear DNS fields and canonical name",),
        required_fields=("qname_rendered", "qname_canonical", "labels", "representation_version"),
        required_observation_contracts=(),
        required_visibility_capabilities=frozenset({VisibilityCapability.CLEAR_DNS_FIELDS}),
        required_quality=(),
        allowed_finality=tuple(Finality),
        allowed_availability_basis=tuple(AvailabilityBasis),
        state_key_declaration=None,
        scientific_history_duration=None,
        resource_retention_duration=None,
        gap_action=GapAction.CONTINUE_WITH_QUALITY_FLAG,
        allowed_result_types=(ResultType.REVIEW_FINDING,),
        integration_status=IntegrationStatus.BASELINE_IMPLEMENTED,
        profiling_hooks_enabled=False,
        governing_claim_ids=(),
        governing_decision_ids=("C3-DEC-20260921-DNS-T1-CANON-V1",),
        official_ps_category=OfficialPsCategory.DGA_AND_DNS_TUNNELLING,
        analytic_family=AnalyticFamily.DNS_TUNNELLING,
        mechanism_id="DNS-T1",
    )

    def manifest(self) -> PluginManifest:
        return self._manifest

    def route(self, observation: NetworkObservation) -> bool:
        return (
            observation.observation_type is ObservationType.DNS
            and observation.visibility.state(VisibilityCapability.CLEAR_DNS_FIELDS)
            is CapabilityState.AVAILABLE
            and all(field in observation.present_fields for field in self._manifest.required_fields)
        )

    def state_key(self, observation: NetworkObservation) -> None:
        return None

    @staticmethod
    def _label_boundaries(labels: tuple[str, ...]) -> list[dict[str, object]]:
        boundaries: list[dict[str, object]] = []
        offset = 0
        for index, label in enumerate(labels):
            end = offset + len(label)
            boundaries.append({"index": index, "label": label, "start": offset, "end": end})
            offset = end + 1
        return boundaries

    async def process(
        self, observation: NetworkObservation, context: Any, state: PluginStateSnapshot | None
    ) -> PluginProcessOutcome:
        payload = observation.typed_payload
        canonical = payload.qname_canonical
        labels = payload.labels
        if not isinstance(canonical, str) or not isinstance(labels, tuple) or not labels:
            raise ValueError("DNS-T1 requires canonical DNS_NAME_REPRESENTATION_V1 fields")

        non_dot = canonical.replace(".", "")
        character_class_counts = {
            "letters": sum("a" <= char <= "z" for char in non_dot),
            "digits": sum("0" <= char <= "9" for char in non_dot),
            "hyphens": non_dot.count("-"),
        }
        character_class_counts["other"] = len(non_dot) - sum(character_class_counts.values())
        denominator = len(non_dot)
        comparable = non_dot.replace("-", "")
        evidence: dict[str, object] = {
            "evidence_kind": "DNS_NAME_STRUCTURE",
            "observation_ref": observation.observation_id,
            "qname_rendered": payload.qname_rendered,
            "qname_canonical": canonical,
            "labels": labels,
            "label_boundaries": self._label_boundaries(labels),
            "label_lengths": [len(label) for label in labels],
            "full_qname_length": len(canonical),
            "full_qname_length_definition": "canonical characters including separators, excluding removed terminal root dot",
            "label_count": len(labels),
            "max_label_length": max(map(len, labels)),
            "leftmost_label_length": len(labels[0]),
            "character_class_counts": character_class_counts,
            "character_class_definition": {
                "letters": "ASCII a-z",
                "digits": "ASCII 0-9",
                "hyphens": "-",
                "other": "all remaining non-dot characters",
            },
            "character_class_denominator": denominator,
            "character_class_denominator_definition": "canonical characters excluding dot separators",
            "digit_fraction": character_class_counts["digits"] / denominator,
            "hyphen_fraction": character_class_counts["hyphens"] / denominator,
            "alphabet_compatibility_descriptors": {
                "ignored_characters": [".", "-"],
                "base32_like_alphabet": "abcdefghijklmnopqrstuvwxyz234567",
                "base32_like_compatible": bool(comparable)
                and all(char in "abcdefghijklmnopqrstuvwxyz234567" for char in comparable),
                "base64_like_alphabet": "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/",
                "base64_like_compatible": bool(comparable)
                and all(
                    char in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
                    for char in comparable
                ),
                "successful_decode_implied": False,
            },
            "visibility": {
                capability.value: observation.visibility.state(capability).value
                for capability in VisibilityCapability
            },
            "quality": {
                "packet_loss": observation.quality.packet_loss.value,
                "sampling": observation.quality.sampling.value,
                "parser": observation.quality.parser.value,
                "capture_gap": observation.quality.capture_gap.value,
            },
            "present_fields": sorted(observation.present_fields),
            "event_time": observation.event_time,
            "representation_version": payload.representation_version,
        }
        for name in (
            "raw_qname_ref",
            "qtype",
            "qclass",
            "message_length",
            "parser_version",
            "parser_status",
            "registrable_domain_ref",
            "transport",
            "truncation",
        ):
            if name in observation.present_fields:
                evidence[name] = getattr(payload, name)
        return PluginProcessOutcome(
            (
                ResultDraft(
                    result_type=ResultType.REVIEW_FINDING,
                    entity_reference=observation.observation_id,
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
