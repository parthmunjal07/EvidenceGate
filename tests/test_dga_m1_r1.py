"""M14 contract tests: verified artifact must remain fail-closed on divergence."""
from datetime import datetime, timezone
from pathlib import Path

import pytest

from evidencegate.domain.enums import DirectionBasis, ResultType, SourceKind, TimestampSemantics, WireDirection
from evidencegate.domain.payloads import DNSObservation
from evidencegate.ingest.builders import DNSCanonicalBuilder
from evidencegate.ingest.source import RawSourceRecord, SourceManifest
from evidencegate.plugins.providers.dga_m1 import (
    ARTIFACT_BYTES, ARTIFACT_SHA256, CLAIM_CEILING, DgaM1ArtifactVerifier,
    DgaM1Plugin, DgaM1RepresentationAdapter, dga_m1_config_hash,
)

NOW = datetime(2026, 9, 23, tzinfo=timezone.utc)
ARTIFACT = Path("artifacts/dga/local/DGA_M1_R1_SERIALIZED_MODEL.joblib")


def observation(qname: str):
    payload = DNSObservation("flow", True, 1, qname, "A", "IN", None, None, "UDP", False,
        raw_qname_ref="fixture:qname", parser_version="fixture")
    manifest = SourceManifest("dns", SourceKind.PCAP, None, None, TimestampSemantics.SOURCE_EVENT_TIME,
        "dns_v1", DirectionBasis.CAPTURE_INTERFACE, WireDirection.FORWARD)
    return DNSCanonicalBuilder().canonicalize(RawSourceRecord(payload, NOW, 1), manifest, "quality", NOW,
        {"qname", "qtype", "qclass", "raw_qname_ref", "parser_version"}, clear_dns_fields=True)


def test_m1_artifact_identity_then_embedded_contract_fail_closed():
    assert ARTIFACT.stat().st_size == ARTIFACT_BYTES
    verifier = DgaM1ArtifactVerifier()
    value = verifier.verify_and_load(ARTIFACT)
    # The byte identity is accepted before joblib.load; the frozen class order is not.
    assert value.available is False
    assert value.failure_reason == "CLASS_ORDER_MISMATCH"


def test_missing_and_wrong_path_never_deserialize():
    verifier = DgaM1ArtifactVerifier()
    assert verifier.verify_and_load(None).failure_reason == "MODEL_PATH_MISSING"
    assert verifier.verify_and_load("not-the-artifact.joblib").failure_reason == "MODEL_PATH_OR_FILENAME_INVALID"


@pytest.mark.parametrize(("qname", "status", "model_input"), [
    ("Example.COM.", "AVAILABLE", "example.com"),
    ("a.b.example.co.uk", "AVAILABLE", "example.co.uk"),
    ("localhost", "ANALYTIC_UNAVAILABLE", None),
    ("example.unknown", "ANALYTIC_UNAVAILABLE", None),
    ("xn--exmple-cua.example", "ANALYTIC_UNAVAILABLE", None),
])
def test_gate_b_representation_is_explicit_and_no_last_two_label_fallback(qname, status, model_input):
    result = DgaM1RepresentationAdapter().adapt(observation(qname))
    assert result.status == status
    assert result.model_input == model_input


@pytest.mark.asyncio
async def test_plugin_emits_typed_unavailability_with_model_provenance():
    plugin = DgaM1Plugin(model_path=str(ARTIFACT))
    outcome = await plugin.process(observation("example.com"), None, None)
    draft = outcome.result_drafts[0]
    assert draft.result_type is ResultType.ANALYTIC_UNAVAILABLE
    evidence = draft.evidence
    assert evidence["failure_reason"] == "CLASS_ORDER_MISMATCH"
    assert evidence["claim_ceiling"] == CLAIM_CEILING
    assert "score" not in evidence
    assert "sha256:" + ARTIFACT_SHA256 in plugin.model_refs()
    assert len(dga_m1_config_hash()) == 64
