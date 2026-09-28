"""M15 default DGA M1-R1 activation and fail-closed contract tests."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from evidencegate.domain.enums import (
    DirectionBasis,
    ResultType,
    ScientificStatus,
    SourceKind,
    TimestampSemantics,
    WireDirection,
)
from evidencegate.domain.governance import LaneGovernance
from evidencegate.domain.payloads import DNSObservation
from evidencegate.ingest.builders import DNSCanonicalBuilder
from evidencegate.ingest.source import RawSourceRecord, SourceManifest
from evidencegate.plugins.providers.dga_m1 import (
    ARTIFACT_BYTES,
    ARTIFACT_SHA256,
    CLAIM_CEILING,
    DgaM1ArtifactVerifier,
    DgaM1ModelService,
    DgaM1Plugin,
    DgaM1Readiness,
    DgaM1RepresentationAdapter,
    MODEL_ID,
    NORMALIZATION,
    PROMOTION_DECISION_ID,
    REPRESENTATION_VERSION,
    R1_NEGATIVE_CLASS,
    R1_POSITIVE_CLASS,
    dga_m1_config_hash,
    resolve_dga_model_path,
    r1_class_semantic_failure,
)
from evidencegate.routing.router import LaneTarget
from evidencegate.runtime.supervisor import RuntimeSupervisor
from evidencegate.plugins.providers.registry import build_mvp_provider_registry

NOW = datetime(2026, 9, 23, tzinfo=timezone.utc)
ARTIFACT = Path("artifacts/dga/local/DGA_M1_R1_SERIALIZED_MODEL.joblib")
requires_model = pytest.mark.skipif(
    not ARTIFACT.is_file(),
    reason="The admitted DGA model bytes are private and absent from a clean checkout",
)


def test_model_path_resolution_precedence_and_canonical_discovery(tmp_path):
    explicit = tmp_path / "explicit.joblib"
    environment = tmp_path / "environment.joblib"
    canonical = tmp_path / "DGA_M1_R1_SERIALIZED_MODEL.joblib"
    canonical.touch()
    assert resolve_dga_model_path(
        str(explicit), environment_path=str(environment), canonical_path=canonical
    ) == str(explicit)
    assert resolve_dga_model_path(
        None, environment_path=str(environment), canonical_path=canonical
    ) == str(environment)
    assert resolve_dga_model_path(None, canonical_path=canonical) == str(canonical)
    canonical.unlink()
    assert resolve_dga_model_path(None, canonical_path=canonical) is None


def observation(qname: str):
    payload = DNSObservation(
        "flow",
        True,
        1,
        qname,
        "A",
        "IN",
        None,
        None,
        "UDP",
        False,
        raw_qname_ref="fixture:qname",
        parser_version="fixture",
    )
    manifest = SourceManifest(
        "dns",
        SourceKind.PCAP,
        None,
        None,
        TimestampSemantics.SOURCE_EVENT_TIME,
        "dns_v1",
        DirectionBasis.CAPTURE_INTERFACE,
        WireDirection.FORWARD,
    )
    return DNSCanonicalBuilder().canonicalize(
        RawSourceRecord(payload, NOW, 1),
        manifest,
        "quality",
        NOW,
        {"qname", "qtype", "qclass", "raw_qname_ref", "parser_version"},
        clear_dns_fields=True,
    )


@requires_model
def test_m1_artifact_identity_then_exact_r1_string_label_contract_passes():
    assert MODEL_ID == "DGA-A1-M1-R1"
    assert ARTIFACT.name == "DGA_M1_R1_SERIALIZED_MODEL.joblib"
    assert ARTIFACT_BYTES == 5720970
    assert ARTIFACT_SHA256 == "39da209d2cfd869dd284e10b8a07adc04826c95146712cc6854a69b9873890df"
    assert REPRESENTATION_VERSION == "DGA_M1_REPRESENTATION_v1"
    assert NORMALIZATION == "str(value).strip().lower().rstrip('.')"
    assert ARTIFACT.stat().st_size == ARTIFACT_BYTES
    verifier = DgaM1ArtifactVerifier()
    value = verifier.verify_and_load(ARTIFACT)
    assert value.available is True
    assert value.loaded["model_id"] == MODEL_ID
    assert value.loaded["representation_version"] == REPRESENTATION_VERSION
    assert value.loaded["normalization"] == NORMALIZATION
    assert value.loaded["config"]["positive_class"] == R1_POSITIVE_CLASS
    assert value.loaded["classifier"].classes_.tolist() == ["benign", "dga"]
    assert R1_NEGATIVE_CLASS == "benign"


def test_r1_semantic_contract_rejects_wrong_negative_missing_positive_and_multiclass():
    assert r1_class_semantic_failure(["benign", "dga"], "dga", "benign") is None
    assert (
        r1_class_semantic_failure(["clean", "dga"], "dga", "benign") == "R1_NEGATIVE_CLASS_MISMATCH"
    )
    assert (
        r1_class_semantic_failure(["benign", "malware"], "dga", "benign")
        == "R1_POSITIVE_CLASS_MISSING_OR_AMBIGUOUS"
    )
    assert (
        r1_class_semantic_failure(["benign", "dga", "other"], "dga", "benign")
        == "R1_CLASS_COUNT_MISMATCH"
    )
    assert r1_class_semantic_failure(["dga", "benign"], "dga", "benign") is None


def test_missing_and_wrong_path_never_deserialize():
    verifier = DgaM1ArtifactVerifier()
    assert verifier.verify_and_load(None).failure_reason == "MODEL_PATH_MISSING"
    assert (
        verifier.verify_and_load("not-the-artifact.joblib").failure_reason
        == "MODEL_PATH_OR_FILENAME_INVALID"
    )


def test_same_size_wrong_sha_fails_closed(tmp_path):
    target = tmp_path / ARTIFACT.name
    target.write_bytes(b"\0" * ARTIFACT_BYTES)
    value = DgaM1ArtifactVerifier().verify_and_load(target)
    assert value.available is False
    assert value.readiness is DgaM1Readiness.ARTIFACT_HASH_MISMATCH
    assert value.failure_reason == "ARTIFACT_SHA256_MISMATCH"


def test_dependency_version_mismatch_fails_closed(tmp_path, monkeypatch):
    import hashlib
    import joblib
    from evidencegate.plugins.providers import dga_m1

    data = b"test bytes that are not a model"
    target = tmp_path / ARTIFACT.name
    target.write_bytes(data)
    monkeypatch.setattr(dga_m1, "ARTIFACT_BYTES", len(data))
    monkeypatch.setattr(dga_m1, "ARTIFACT_SHA256", hashlib.sha256(data).hexdigest())
    monkeypatch.setattr(joblib, "__version__", "0.invalid")
    value = DgaM1ArtifactVerifier().verify_and_load(target)
    assert value.available is False
    assert value.readiness is DgaM1Readiness.DEPENDENCY_MISMATCH
    assert value.failure_reason == "MODEL_DEPENDENCY_VERSION_MISMATCH"


def test_psl_dependency_mismatch_constructs_unavailable_adapter(monkeypatch):
    import tldextract

    monkeypatch.setattr(tldextract, "__version__", "0.invalid")
    adapter = DgaM1RepresentationAdapter()
    assert adapter.available is False
    result = adapter.adapt(observation("example.com"))
    assert result.status == "ANALYTIC_UNAVAILABLE"
    assert result.failure_reason == "DGA_M1_PSL_DEPENDENCY_VERSION_MISMATCH"


@pytest.mark.parametrize(
    ("qname", "status", "model_input"),
    [
        ("Example.COM.", "AVAILABLE", "example.com"),
        ("example.com", "AVAILABLE", "example.com"),
        ("example.com..", "ANALYTIC_UNAVAILABLE", None),
        ("a.b.example.com", "AVAILABLE", "example.com"),
        ("a.b.example.co.uk", "AVAILABLE", "example.co.uk"),
        ("xn--exmple-cua.com", "AVAILABLE", "xn--exmple-cua.com"),
        ("Bücher.com", "ANALYTIC_UNAVAILABLE", None),
        ("foo.blogspot.com", "AVAILABLE", "foo.blogspot.com"),
        ("localhost", "ANALYTIC_UNAVAILABLE", None),
        ("internal", "ANALYTIC_UNAVAILABLE", None),
        ("example.unknown", "ANALYTIC_UNAVAILABLE", None),
        (".", "ANALYTIC_UNAVAILABLE", None),
        ("", "ANALYTIC_UNAVAILABLE", None),
        ("white space.example", "ANALYTIC_UNAVAILABLE", None),
        (".example.com", "ANALYTIC_UNAVAILABLE", None),
        ("foo..example.com", "ANALYTIC_UNAVAILABLE", None),
        ("xn--exmple-cua.example", "ANALYTIC_UNAVAILABLE", None),
    ],
)
def test_gate_b_representation_is_explicit_and_no_last_two_label_fallback(
    qname, status, model_input
):
    result = DgaM1RepresentationAdapter().adapt(observation(qname))
    assert result.status == status
    assert result.model_input == model_input


@requires_model
@pytest.mark.asyncio
async def test_plugin_emits_review_finding_with_semantic_score_and_model_provenance():
    plugin = DgaM1Plugin(model_path=str(ARTIFACT))
    outcome = await plugin.process(observation("example.com"), None, None)
    draft = outcome.result_drafts[0]
    assert draft.result_type is ResultType.REVIEW_FINDING
    evidence = draft.evidence
    assert evidence["claim_ceiling"] == CLAIM_CEILING
    assert evidence["positive_class"] == "dga"
    assert evidence["positive_class_index"] == 1
    assert evidence["classifier_classes"] == ["benign", "dga"]
    assert 0 <= evidence["dga_labelled_lexical_resemblance_score"] <= 1
    assert "sha256:" + ARTIFACT_SHA256 in plugin.model_refs()
    assert len(dga_m1_config_hash()) == 64


@pytest.mark.asyncio
async def test_missing_model_emits_truthful_unavailable_with_model_refs():
    plugin = DgaM1Plugin(model_path="missing/DGA_M1_R1_SERIALIZED_MODEL.joblib")
    outcome = await plugin.process(observation("example.com"), None, None)
    draft = outcome.result_drafts[0]
    assert draft.result_type is ResultType.ANALYTIC_UNAVAILABLE
    assert "dga_labelled_lexical_resemblance_score" not in draft.evidence
    assert draft.evidence["model_readiness"] == "ARTIFACT_MISSING"
    assert draft.evidence["failure_reason"] == "MODEL_PATH_OR_FILENAME_INVALID"
    assert "model:DGA-A1-M1-R1" in plugin.model_refs()


@requires_model
def test_score_uses_semantic_positive_class_index():
    service = DgaM1ModelService(str(ARTIFACT))
    assert service.positive_class == "dga"
    assert service.positive_class_index == list(service.classifier_classes).index("dga")


@requires_model
@pytest.mark.asyncio
async def test_explicit_nondefault_runtime_emits_provenance_bearing_review_finding():
    plugin = DgaM1Plugin(model_path=str(ARTIFACT))
    lane = LaneTarget("dga.m1")
    governance = LaneGovernance(
        analytic_lane="dga.m1",
        scientific_status=ScientificStatus.EVIDENCE_CONSTRUCTION,
        scientific_phase="explicit non-default lexical evidence",
        scientific_blockers=(),
        claim_ceiling=CLAIM_CEILING,
        governance_version="dga-m1-r1-0.1.0",
        effective_at=NOW,
        allowed_result_types=(ResultType.REVIEW_FINDING, ResultType.ANALYTIC_UNAVAILABLE),
        ingest_permitted=True,
    )
    emitted = []

    async def collect(result, result_lane):
        emitted.append((result, result_lane))

    supervisor = RuntimeSupervisor({lane: plugin}, {lane: governance}, collect, shard_count=1)
    supervisor.start_all()
    try:
        await supervisor.ingest_observation(observation("example.com"))
        await supervisor.dispatchers[lane].queue.join()
        await supervisor.shards[lane][0].queue.join()
        result, result_lane = emitted[0]
        assert str(result_lane) == "dga.m1" and result.result_type is ResultType.REVIEW_FINDING
        assert result.model_refs and "sha256:" + ARTIFACT_SHA256 in result.model_refs
        assert result.evidence.to_value()["positive_class"] == "dga"
    finally:
        await supervisor.stop_all()


@requires_model
@pytest.mark.asyncio
async def test_dga_m1_and_dns_t1_route_zero_to_many_without_score_fusion():
    dga_lane, t1_lane = LaneTarget("dga.m1"), LaneTarget("dns_tunnelling.t1")
    default_plugins, default_governances = build_mvp_provider_registry(NOW)
    plugin = DgaM1Plugin(model_path=str(ARTIFACT))
    governance = LaneGovernance(
        analytic_lane="dga.m1",
        scientific_status=ScientificStatus.EVIDENCE_CONSTRUCTION,
        scientific_phase="explicit non-default lexical evidence",
        scientific_blockers=(),
        claim_ceiling=CLAIM_CEILING,
        governance_version="dga-m1-r1-0.1.0",
        effective_at=NOW,
        allowed_result_types=(ResultType.REVIEW_FINDING, ResultType.ANALYTIC_UNAVAILABLE),
        ingest_permitted=True,
    )
    emitted = []

    async def collect(result, lane):
        emitted.append((result, str(lane)))

    supervisor = RuntimeSupervisor(
        {dga_lane: plugin, t1_lane: default_plugins[t1_lane]},
        {dga_lane: governance, t1_lane: default_governances[t1_lane]},
        collect,
        shard_count=1,
    )
    supervisor.start_all()
    try:
        plan = await supervisor.ingest_observation(observation("example.com"))
        assert set(plan.selected_targets) == {"dga.m1", "dns_tunnelling.t1"}
        for lane in (dga_lane, t1_lane):
            await supervisor.dispatchers[lane].queue.join()
            await supervisor.shards[lane][0].queue.join()
        assert {lane for _, lane in emitted} == {"dga.m1", "dns_tunnelling.t1"}
        assert all(
            "DNS_NAME_STRUCTURE" not in result.evidence.canonical_json
            or result.mechanism_id == "DNS-T1"
            for result, _ in emitted
        )
    finally:
        await supervisor.stop_all()


def test_default_registry_exact_activation_governance_and_no_reorder(monkeypatch):
    monkeypatch.setenv("EVIDENCEGATE_DGA_MODEL", str(ARTIFACT.resolve()))
    from evidencegate.plugins.providers.registry import build_mvp_runtime_registration

    registration = build_mvp_runtime_registration(NOW)
    expected = {
        "ddos.syn_state",
        "ddos.udp_demand",
        "ddos.reflection_victim",
        "ddos.source_diversity",
        "ddos.icmp_demand",
        "ddos.fragment_demand",
        "ddos.connection_churn",
        "c2.r1",
        "dga.m1",
        "dns_tunnelling.t1",
        "encrypted_session.enc_a",
        "recon.h",
        "recon.v",
        "recon.2d",
        "recon.tcp",
        "unusual_transfer.m1",
    }
    assert set(map(str, registration.plugins)) == expected
    assert len(registration.plugins) == 16 and "dga" not in registration.plugins
    assert "dga.m1" not in registration.reorder_policies
    plugin = registration.plugins["dga.m1"]
    governance = registration.governances["dga.m1"]
    expected_readiness = (
        DgaM1Readiness.VERIFIED_READY if ARTIFACT.is_file() else DgaM1Readiness.ARTIFACT_MISSING
    )
    assert plugin.service.verification.readiness is expected_readiness
    assert governance.scientific_phase == "DGA-labelled lexical review evidence"
    assert governance.scientific_blockers == ()
    assert governance.claim_ceiling == CLAIM_CEILING
    assert plugin.manifest().governing_decision_ids == (PROMOTION_DECISION_ID,)


@requires_model
@pytest.mark.asyncio
async def test_default_registry_dns_zero_to_many_and_pinned_score(monkeypatch):
    monkeypatch.setenv("EVIDENCEGATE_DGA_MODEL", str(ARTIFACT.resolve()))
    from evidencegate.plugins.providers.registry import build_mvp_runtime_registration

    registration = build_mvp_runtime_registration(NOW)
    emitted = []

    async def collect(result, lane):
        emitted.append((result, str(lane)))

    supervisor = RuntimeSupervisor(
        registration.plugins,
        registration.governances,
        collect,
        shard_count=1,
        reorder_policies=registration.reorder_policies,
    )
    supervisor.start_all()
    try:
        plan = await supervisor.ingest_observation(observation("ajdkskqweoiuzx.com"))
        assert set(plan.selected_targets) == {"dga.m1", "dns_tunnelling.t1"}
        for lane in (LaneTarget("dga.m1"), LaneTarget("dns_tunnelling.t1")):
            await supervisor.dispatchers[lane].queue.join()
            await supervisor.shards[lane][0].queue.join()
        dga = next(result for result, lane in emitted if lane == "dga.m1")
        assert dga.evidence.to_value()["dga_labelled_lexical_resemblance_score"] == pytest.approx(
            0.9851716132182514, abs=1e-12
        )
        assert PROMOTION_DECISION_ID in dga.governing_ids
        assert dga.model_refs == (
            "model:DGA-A1-M1-R1",
            "sha256:" + ARTIFACT_SHA256,
        )
    finally:
        await supervisor.stop_all()
