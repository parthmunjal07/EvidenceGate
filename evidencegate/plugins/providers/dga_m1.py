"""Fail-closed DGA-A1/M1 artifact, representation, and plugin integration."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Sequence

from evidencegate.domain.enums import (
    AnalyticFamily, AnalyticUnavailableReason, AvailabilityBasis, CapabilityState,
    Finality, GapAction, IntegrationStatus, ObservationType, OfficialPsCategory,
    ResultType, VisibilityCapability,
)
from evidencegate.domain.events import NetworkObservation
from evidencegate.domain.quality import QualityGap
from evidencegate.registry.manifest import PluginManifest
from evidencegate.registry.plugin import PluginProcessOutcome, PluginStateSnapshot, StateKey
from evidencegate.results.types import ResultDraft


MODEL_ID = "DGA-A1-M1-R1"
REPRESENTATION_VERSION = "DGA_M1_REPRESENTATION_v1"
NORMALIZATION = "str(value).strip().lower().rstrip('.')"
ARTIFACT_BYTES = 5720970
ARTIFACT_SHA256 = "39da209d2cfd869dd284e10b8a07adc04826c95146712cc6854a69b9873890df"
ARTIFACT_DRIVE_ID = "16YbGrjsC_aCluWGa8-bC0mN5DVPO_T-Y"
R1_POSITIVE_CLASS = "dga"
R1_NEGATIVE_CLASS = "benign"
CLAIM_CEILING = (
    "DGA_LABELLED_LEXICAL_REVIEW_EVIDENCE_ONLY;NO_MALWARE_CONFIRMATION;"
    "NO_INFECTION_INFERENCE;NO_C2_INFERENCE;NO_DNS_TUNNEL_INFERENCE;"
    "NO_EXFILTRATION_INFERENCE;NO_DOMAIN_OWNERSHIP_OR_INTENT"
)
PSL_PROVIDER = "tldextract-5.1.3-bundled-snapshot-offline-private-included"
IDNA_POLICY = "ASCII and xn-- labels are accepted as text; Unicode and malformed IDNA are unavailable"


@dataclass(frozen=True, slots=True)
class DgaM1RepresentationResult:
    raw_qname_ref: str | None
    qname_rendered: str | None
    qname_canonical: str | None
    registrable_domain: str | None
    model_input: str | None
    dns_representation_version: str | None
    m1_representation_version: str = REPRESENTATION_VERSION
    normalization_version: str = NORMALIZATION
    psl_provider: str = PSL_PROVIDER
    psl_version: str = "5.1.3"
    idna_policy: str = IDNA_POLICY
    status: str = "ANALYTIC_UNAVAILABLE"
    failure_reason: str | None = None


class DgaM1RepresentationAdapter:
    """Maps a factual DNS-T1 representation to the separately governed M1 input."""

    def __init__(self) -> None:
        try:
            import tldextract
        except ImportError as exc:  # optional non-default integration dependency
            raise RuntimeError("DGA_M1_PSL_DEPENDENCY_MISSING") from exc
        # Empty URLs force use of the bundled snapshot: no network fetch or cache update.
        self._extract = tldextract.TLDExtract(
            suffix_list_urls=(), include_psl_private_domains=True,
        )

    def adapt(self, observation: NetworkObservation) -> DgaM1RepresentationResult:
        payload = observation.typed_payload
        rendered = getattr(payload, "qname_rendered", None)
        canonical = getattr(payload, "qname_canonical", None)
        common = dict(
            raw_qname_ref=getattr(payload, "raw_qname_ref", None), qname_rendered=rendered,
            qname_canonical=canonical,
            dns_representation_version=getattr(payload, "representation_version", None),
        )
        if not isinstance(rendered, str) or not isinstance(canonical, str):
            return DgaM1RepresentationResult(**common, registrable_domain=None, model_input=None,
                failure_reason="DNS_T1_CANONICAL_REPRESENTATION_UNAVAILABLE")
        if any(ord(char) > 127 for char in canonical):
            return DgaM1RepresentationResult(**common, registrable_domain=None, model_input=None,
                failure_reason="UNICODE_IDNA_POLICY_UNRESOLVED")
        extracted = self._extract(canonical)
        if not extracted.suffix:
            return DgaM1RepresentationResult(**common, registrable_domain=None, model_input=None,
                failure_reason="UNKNOWN_OR_INTERNAL_SUFFIX")
        if not extracted.domain:
            return DgaM1RepresentationResult(**common, registrable_domain=None, model_input=None,
                failure_reason="NO_REGISTRABLE_DOMAIN")
        # Both components originate from the pinned PSL extractor; this is not
        # a label-count heuristic.
        domain = f"{extracted.domain}.{extracted.suffix}"
        # Historical M1 normalization is deliberately independent of DNS-T1.
        return DgaM1RepresentationResult(**common, registrable_domain=domain,
            model_input=str(domain).strip().lower().rstrip("."), status="AVAILABLE")


@dataclass(frozen=True, slots=True)
class DgaM1Verification:
    available: bool
    failure_reason: str | None = None
    loaded: dict[str, Any] | None = None


def r1_class_semantic_failure(classes: Sequence[object], positive_class: object,
                              negative_class: object) -> str | None:
    """Return a strict R1 semantic-contract failure without assuming numeric labels."""
    values = list(classes)
    if len(values) != 2:
        return "R1_CLASS_COUNT_MISMATCH"
    if values.count(positive_class) != 1:
        return "R1_POSITIVE_CLASS_MISSING_OR_AMBIGUOUS"
    if values.count(negative_class) != 1:
        return "R1_NEGATIVE_CLASS_MISMATCH"
    if set(values) != {positive_class, negative_class}:
        return "R1_CLASS_SEMANTIC_CONTRACT_MISMATCH"
    return None


class DgaM1ArtifactVerifier:
    """Validates identity before joblib's pickle-based deserialization."""

    def verify_and_load(self, model_path: str | os.PathLike[str] | None) -> DgaM1Verification:
        if not model_path:
            return DgaM1Verification(False, "MODEL_PATH_MISSING")
        path = Path(model_path)
        if path.name != "DGA_M1_R1_SERIALIZED_MODEL.joblib" or not path.is_file():
            return DgaM1Verification(False, "MODEL_PATH_OR_FILENAME_INVALID")
        data = path.read_bytes()
        if len(data) != ARTIFACT_BYTES:
            return DgaM1Verification(False, "ARTIFACT_BYTE_COUNT_MISMATCH")
        if hashlib.sha256(data).hexdigest() != ARTIFACT_SHA256:
            return DgaM1Verification(False, "ARTIFACT_SHA256_MISMATCH")
        try:
            import joblib
            import sklearn
        except ImportError:
            return DgaM1Verification(False, "MODEL_DEPENDENCY_MISSING")
        if joblib.__version__ != "1.6.0" or sklearn.__version__ != "1.6.1":
            return DgaM1Verification(False, "MODEL_DEPENDENCY_VERSION_MISMATCH")
        try:
            loaded = joblib.load(path)
        except Exception:
            return DgaM1Verification(False, "MODEL_DESERIALIZATION_FAILED")
        if not isinstance(loaded, dict) or set(("model_id", "representation_version", "normalization", "vectorizer", "classifier", "config")) - set(loaded):
            return DgaM1Verification(False, "MODEL_STRUCTURE_MISMATCH")
        if (loaded["model_id"] != MODEL_ID or loaded["representation_version"] != REPRESENTATION_VERSION
                or loaded["normalization"] != NORMALIZATION):
            return DgaM1Verification(False, "MODEL_METADATA_MISMATCH")
        config = loaded["config"]
        if not isinstance(config, dict) or config.get("positive_class") != R1_POSITIVE_CLASS or config.get("label_column") != "label":
            return DgaM1Verification(False, "R1_LABEL_SCHEMA_CONFIG_MISMATCH")
        vectorizer, classifier = loaded["vectorizer"], loaded["classifier"]
        vectorizer_expectations = {"analyzer": "char", "ngram_range": (2, 5), "min_df": 2,
            "max_features": 150000, "sublinear_tf": True, "dtype": "float32", "use_idf": True,
            "smooth_idf": True, "norm": "l2", "lowercase": True}
        classifier_expectations = {"C": 2.0, "solver": "liblinear", "class_weight": "balanced",
            "max_iter": 200, "random_state": 26145}
        try:
            vectorizer_params = vectorizer.get_params()
            classifier_params = classifier.get_params()
            class_values = classifier.classes_.tolist()
        except Exception:
            return DgaM1Verification(False, "MODEL_COMPONENT_MISMATCH")
        if any(vectorizer_params.get(key) != value for key, value in vectorizer_expectations.items()):
            return DgaM1Verification(False, "VECTORIZER_CONTRACT_MISMATCH")
        if any(classifier_params.get(key) != value for key, value in classifier_expectations.items()):
            return DgaM1Verification(False, "CLASSIFIER_CONTRACT_MISMATCH")
        class_failure = r1_class_semantic_failure(class_values, R1_POSITIVE_CLASS, R1_NEGATIVE_CLASS)
        if class_failure is not None:
            return DgaM1Verification(False, class_failure)
        return DgaM1Verification(True, loaded=loaded)


class DgaM1ModelService:
    def __init__(self, model_path: str | None = None, verifier: DgaM1ArtifactVerifier | None = None) -> None:
        self.verification = (verifier or DgaM1ArtifactVerifier()).verify_and_load(
            model_path or os.getenv("EVIDENCEGATE_DGA_MODEL")
        )

    @property
    def available(self) -> bool:
        return self.verification.available

    def score(self, model_input: str) -> float:
        if not self.verification.available or self.verification.loaded is None:
            raise RuntimeError(self.verification.failure_reason or "MODEL_UNAVAILABLE")
        model = self.verification.loaded
        positive_index = self.positive_class_index
        return float(model["classifier"].predict_proba(model["vectorizer"].transform([model_input]))[0][positive_index])

    @property
    def positive_class(self) -> str:
        return R1_POSITIVE_CLASS

    @property
    def positive_class_index(self) -> int:
        if not self.verification.available or self.verification.loaded is None:
            raise RuntimeError(self.verification.failure_reason or "MODEL_UNAVAILABLE")
        return list(self.verification.loaded["classifier"].classes_).index(R1_POSITIVE_CLASS)

    @property
    def classifier_classes(self) -> list[str]:
        if not self.verification.available or self.verification.loaded is None:
            return []
        return list(self.verification.loaded["classifier"].classes_)


def dga_m1_config_hash() -> str:
    value = {"artifact_sha256": ARTIFACT_SHA256, "representation_version": REPRESENTATION_VERSION,
        "normalization": NORMALIZATION, "psl_provider": PSL_PROVIDER, "idna_policy": IDNA_POLICY,
        "input_selection": "registrable_domain_from_offline_psl"}
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class DgaM1Plugin:
    """Explicit-only stateless lane; never included in the default registry."""
    _manifest = PluginManifest(
        plugin_id="provider.dga.a1.m1", plugin_version="0.1.0", analytic_version="dga-a1-m1-r1",
        taxonomy=("Network", "DGA", "Lexical Model Evidence"), accepted_observation_types=(ObservationType.DNS,),
        routing_predicate_version="dga-m1-representation-v1", admission_requirements=("clear DNS fields",),
        required_fields=("qname_rendered", "qname_canonical", "representation_version"),
        required_observation_contracts=(), required_visibility_capabilities=frozenset({VisibilityCapability.CLEAR_DNS_FIELDS}),
        required_quality=(), allowed_finality=tuple(Finality), allowed_availability_basis=tuple(AvailabilityBasis),
        state_key_declaration=None, scientific_history_duration=None, resource_retention_duration=None,
        gap_action=GapAction.CONTINUE_WITH_QUALITY_FLAG,
        allowed_result_types=(ResultType.REVIEW_FINDING, ResultType.ANALYTIC_UNAVAILABLE),
        integration_status=IntegrationStatus.BASELINE_IMPLEMENTED, profiling_hooks_enabled=False,
        governing_claim_ids=(), governing_decision_ids=("C3-DEC-M14-DGA-M1-R1",),
        official_ps_category=OfficialPsCategory.DGA_AND_DNS_TUNNELLING, analytic_family=AnalyticFamily.DGA,
        mechanism_id="DGA-A1-M1", config_hash=dga_m1_config_hash(),
    )

    def __init__(self, model_path: str | None = None, service: DgaM1ModelService | None = None,
                 adapter: DgaM1RepresentationAdapter | None = None) -> None:
        self.service = service or DgaM1ModelService(model_path)
        self.adapter = adapter or DgaM1RepresentationAdapter()

    def manifest(self) -> PluginManifest: return self._manifest
    def model_refs(self) -> tuple[str, ...]:
        return (f"model:{MODEL_ID}", f"sha256:{ARTIFACT_SHA256}", f"drive:{ARTIFACT_DRIVE_ID}")
    def route(self, observation: NetworkObservation) -> bool:
        return observation.observation_type is ObservationType.DNS and observation.visibility.state(VisibilityCapability.CLEAR_DNS_FIELDS) is CapabilityState.AVAILABLE
    def state_key(self, observation: NetworkObservation) -> None: return None

    async def process(self, observation: NetworkObservation, context: Any, state: PluginStateSnapshot | None) -> PluginProcessOutcome:
        representation = self.adapter.adapt(observation)
        evidence = {"evidence_kind": "DGA_LEXICAL_MODEL_EVIDENCE", "representation": asdict(representation),
            "claim_ceiling": CLAIM_CEILING, "source_shift_warning": "Score is not calibrated deployment risk."}
        if not self.service.available or representation.status != "AVAILABLE" or not representation.model_input:
            evidence["availability"] = "ANALYTIC_UNAVAILABLE"
            evidence["failure_reason"] = self.service.verification.failure_reason or representation.failure_reason
            return PluginProcessOutcome((ResultDraft(ResultType.ANALYTIC_UNAVAILABLE, observation.observation_id, (), (),
                reason_code=AnalyticUnavailableReason.IMPLEMENTATION_NOT_READY, evidence=evidence),))
        score = self.service.score(representation.model_input)
        evidence["availability"] = "AVAILABLE"
        evidence["dga_labelled_lexical_resemblance_score"] = score
        evidence["positive_class"] = self.service.positive_class
        evidence["positive_class_index"] = self.service.positive_class_index
        evidence["classifier_classes"] = self.service.classifier_classes
        return PluginProcessOutcome((ResultDraft(ResultType.REVIEW_FINDING, observation.observation_id, (), (), evidence=evidence),))

    async def on_quality_gap(self, gap: QualityGap, context: Any, state: Any) -> Sequence[ResultDraft]: return ()
    async def on_watermark(self, watermark: Any, context: Any) -> PluginProcessOutcome: return PluginProcessOutcome()
    async def on_expire(self, key: StateKey, context: Any, state: PluginStateSnapshot) -> PluginProcessOutcome: return PluginProcessOutcome()
