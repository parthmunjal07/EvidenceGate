from dataclasses import replace
from datetime import datetime, timezone

import pytest

from evidencegate.domain.enums import (
    AnalyticFamily, CapabilityState, DirectionBasis, EvidenceReadiness, IntegrationStatus, ObservationType,
    OfficialPsCategory, QualityState, ResultType, SourceKind, TimestampSemantics,
    VisibilityCapability, WireDirection,
)
from evidencegate.domain.events import VisibilityProfile
from evidencegate.domain.payloads import DNSObservation
from evidencegate.domain.quality import EvidenceQuality
from evidencegate.ingest.builders import DNSCanonicalBuilder
from evidencegate.ingest.source import RawSourceRecord, SourceManifest
from evidencegate.persistence.sqlite import SqliteWriter
from evidencegate.plugins.providers.registry import build_mvp_provider_registry, build_mvp_runtime_registration
from evidencegate.results.finalizer import ResultEmissionContext, ResultFinalizer
from evidencegate.results.types import ReviewFinding
from evidencegate.routing.router import RelevanceRouter
from evidencegate.runtime.provenance import parser_refs_from_observation
from evidencegate.runtime.supervisor import RuntimeSupervisor


NOW = datetime(2026, 9, 21, tzinfo=timezone.utc)
SCHEMA = "evidencegate/persistence/schema.sql"


def canonical_observation(
    qname="A1.Xn--Exmple-Cua.UNKNOWN.", *, direction=WireDirection.FORWARD,
    qtype="TXT", qclass="IN", rcode=None, answers=None,
    parser_status="PARTIAL", quality=EvidenceQuality(parser=QualityState.DEGRADED),
):
    payload = DNSObservation(
        flow_reference="flow-1", qr_state_decoded=True, transaction_id=7, qname=qname,
        qtype=qtype, qclass=qclass, rcode=rcode, answers=answers, transport="UDP",
        truncation=True, raw_qname_ref="pcap:17:q0", parser_version="dns-parser-2",
        parser_status=parser_status, message_length=91,
    )
    fields = {
        "flow_reference", "qr_state_decoded", "transaction_id", "qname", "qtype",
        "qclass", "transport", "truncation", "raw_qname_ref", "parser_version",
        "parser_status", "message_length",
    }
    if qtype is None:
        fields.remove("qtype")
    if qclass is None:
        fields.remove("qclass")
    manifest = SourceManifest(
        source_id="dns-source", source_kind=SourceKind.PCAP, capture_start=None,
        capture_end=None, timestamp_semantics=TimestampSemantics.SOURCE_EVENT_TIME,
        input_observation_contract="dns_v1", direction_basis=DirectionBasis.CAPTURE_INTERFACE,
        wire_direction=direction, quality=quality,
    )
    return DNSCanonicalBuilder().canonicalize(
        RawSourceRecord(payload, NOW, 17), manifest, "quality:dns-source", NOW,
        fields, clear_dns_fields=True,
    )


def t1_parts():
    registration = build_mvp_runtime_registration(NOW)
    plugins, governances = registration.plugins, registration.governances
    lane = next(key for key in plugins if str(key) == "dns_tunnelling.t1")
    return plugins[lane], governances[lane]


async def finalized(observation):
    plugin, governance = t1_parts()
    draft = (await plugin.process(observation, None, None)).result_drafts[0]
    context = ResultEmissionContext(
        lane_id="dns_tunnelling.t1", causal_result_time=observation.causal_available_time,
        quality_refs=(observation.quality_ref,), provenance_refs=(observation.provenance_ref,),
        readiness=EvidenceReadiness.READY, quality_degraded=True,
        trigger_reference=observation.observation_id, source_ids=(observation.source_id,),
        source_observation_ids=(observation.observation_id,), quality_snapshot=observation.quality,
        visibility_snapshot=observation.visibility,
        parser_refs=parser_refs_from_observation(observation),
    )
    return ResultFinalizer.finalize(draft, plugin.manifest(), governance, context)


def test_manifest_identity_route_and_zero_to_many_boundary():
    plugin, governance = t1_parts()
    manifest = plugin.manifest()
    assert manifest.plugin_id == "provider.dns_tunnelling.t1"
    assert manifest.mechanism_id == "DNS-T1"
    assert manifest.official_ps_category is OfficialPsCategory.DGA_AND_DNS_TUNNELLING
    assert manifest.analytic_family is AnalyticFamily.DNS_TUNNELLING
    assert manifest.integration_status is IntegrationStatus.BASELINE_IMPLEMENTED
    assert manifest.allowed_result_types == (ResultType.REVIEW_FINDING,)
    assert "NO_DNS_TUNNEL_VERDICT" in governance.claim_ceiling
    assert plugin.state_key(canonical_observation()) is None

    plugins, _ = build_mvp_provider_registry(NOW)
    assert set(RelevanceRouter(plugins).route(canonical_observation())) == {
        "dga", "dns_tunnelling.t1",
    }
    assert RelevanceRouter(plugins).route(canonical_observation(".")) == ("dga",)
    assert set(RelevanceRouter(plugins).route(canonical_observation(direction=WireDirection.REVERSE))) == {
        "dga", "dns_tunnelling.t1",
    }


@pytest.mark.asyncio
async def test_one_way_partial_observation_emits_one_factual_review_finding():
    observation = canonical_observation()
    plugin, _ = t1_parts()
    assert observation.visibility.state(VisibilityCapability.FORWARD_FACTS) is CapabilityState.AVAILABLE
    assert observation.visibility.state(VisibilityCapability.REVERSE_FACTS) is CapabilityState.UNAVAILABLE
    outcome = await plugin.process(observation, None, None)
    assert len(outcome.result_drafts) == 1
    draft = outcome.result_drafts[0]
    assert draft.result_type is ResultType.REVIEW_FINDING
    value = (await finalized(observation)).evidence.to_value()
    assert value["evidence_kind"] == "DNS_NAME_STRUCTURE"
    assert value["qname_rendered"] == "A1.Xn--Exmple-Cua.UNKNOWN."
    assert value["qname_canonical"] == "a1.xn--exmple-cua.unknown"
    assert value["raw_qname_ref"] == "pcap:17:q0"
    assert value["labels"] == ["a1", "xn--exmple-cua", "unknown"]
    assert value["label_lengths"] == [2, 14, 7]
    assert value["label_count"] == 3 and value["max_label_length"] == 14
    assert value["leftmost_label_length"] == 2
    assert value["full_qname_length"] == 25
    assert value["character_class_counts"] == {"letters": 19, "digits": 1, "hyphens": 3, "other": 0}
    assert value["character_class_denominator"] == 23
    assert value["digit_fraction"] == pytest.approx(1 / 23)
    assert value["hyphen_fraction"] == pytest.approx(3 / 23)
    assert value["qtype"] == "TXT" and value["qclass"] == "IN"
    assert value["message_length"] == 91
    assert value["parser_status"] == "PARTIAL"
    assert value["truncation"] is True and value["transport"] == "UDP"
    assert value["quality"]["parser"] == "DEGRADED"
    assert "rcode" not in value and "answers" not in value


@pytest.mark.asyncio
async def test_alphabet_descriptors_are_membership_only_and_optional_facts_stay_missing():
    result = await finalized(canonical_observation("MZXW6YTBOI.example", qtype=None, qclass=None))
    evidence = result.evidence.to_value()
    descriptors = evidence["alphabet_compatibility_descriptors"]
    assert descriptors["base32_like_compatible"] is True
    assert descriptors["base64_like_compatible"] is True
    assert descriptors["successful_decode_implied"] is False
    assert "qtype" not in evidence and "qclass" not in evidence


@pytest.mark.asyncio
async def test_runtime_provenance_determinism_case_distinction_and_sqlite_v3_round_trip(tmp_path):
    first_observation = canonical_observation("Example.COM.")
    second_observation = canonical_observation("example.com.")
    first = await finalized(first_observation)
    again = await finalized(first_observation)
    second = await finalized(second_observation)
    assert isinstance(first, ReviewFinding)
    assert first == again
    assert first.result_id != second.result_id
    assert first.parser_refs == ("DNS:dns-parser-2",)
    assert first.quality_snapshot.parser is QualityState.DEGRADED
    assert first.visibility_snapshot == first_observation.visibility
    assert first.mechanism_id == "DNS-T1"
    assert first.model_refs == () and first.config_hash is None and first.state_version is None

    writer = SqliteWriter(tmp_path / "dns-t1.db", SCHEMA)
    writer.connect()
    await writer.write_result(first)
    assert await writer.get_result(first.result_id) == first
    assert writer._conn.execute("SELECT COUNT(*) FROM schema_migrations WHERE version=3").fetchone()[0] == 1
    writer.close()


@pytest.mark.asyncio
async def test_runtime_routes_dga_and_t1_but_only_t1_emits():
    registration = build_mvp_runtime_registration(NOW)
    plugins, governances = registration.plugins, registration.governances
    emitted = []

    async def collect(result, lane):
        emitted.append((result, str(lane)))

    supervisor = RuntimeSupervisor(
        plugins, governances, collect, shard_count=1,
        reorder_policies=registration.reorder_policies,
    )
    supervisor.start_all()
    try:
        plan = await supervisor.ingest_observation(canonical_observation())
        assert set(plan.selected_targets) == {"dga", "dns_tunnelling.t1"}
        for lane in plan.selected_targets:
            await supervisor.dispatchers[lane].queue.join()
            for shard in supervisor.shards[lane]:
                await shard.queue.join()
        assert len(emitted) == 1
        result, lane = emitted[0]
        assert lane == "dns_tunnelling.t1"
        assert isinstance(result, ReviewFinding)
        assert result.mechanism_id == "DNS-T1"
        assert result.parser_refs == ("DNS:dns-parser-2",)
    finally:
        await supervisor.stop_all()
