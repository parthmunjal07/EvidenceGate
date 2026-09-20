"""M6 provider integration shells: structural plumbing only, never detection."""
from datetime import datetime, timezone
from dataclasses import replace

import pytest

from evidencegate.domain.enums import (
    AnalyticFamily, AvailabilityBasis, DirectionBasis, Finality, IntegrationStatus,
    ObservationType, OfficialPsCategory, ResultType, ScientificStatus, SourceKind,
    VisibilityCapability, WireDirection,
)
from evidencegate.domain.events import NetworkObservationEnvelope, VisibilityProfile
from evidencegate.domain.payloads import DNSObservation, FlowObservation, QUICObservation, TLSObservation
from evidencegate.plugins.providers.registry import build_mvp_provider_registry
from evidencegate.routing.router import RelevanceRouter
from evidencegate.runtime.supervisor import RuntimeSupervisor
from evidencegate.registry.plugin import PluginProcessOutcome, StateKey
from evidencegate.domain.quality import QualityGap

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def observation(kind, payload, visibility):
    return NetworkObservationEnvelope(
        observation_id=f"m6-{kind.value}", schema_version="1.1", observation_type=kind,
        event_time=NOW, causal_available_time=NOW, ingest_time=NOW, source_id="m6",
        source_kind=SourceKind.PCAP, source_position="1", observation_contract="any-v1",
        wire_direction=WireDirection.FORWARD, direction_basis=DirectionBasis.CAPTURE_INTERFACE,
        finality=Finality.CURRENT, availability_basis=AvailabilityBasis.IMMEDIATE,
        provenance_ref="prov:m6", quality_ref="", present_fields=frozenset(),
        typed_payload=payload, visibility=VisibilityProfile(available=frozenset(visibility)),
    )


def flow():
    value = observation(ObservationType.FLOW, FlowObservation("source-order", ("a", "b"), 6, NOW, NOW, NOW, {}, "factual", None, None), {VisibilityCapability.FLOW_FACTS, VisibilityCapability.FORWARD_FACTS})
    return replace(value, visibility=VisibilityProfile(
        available=frozenset({VisibilityCapability.FLOW_FACTS, VisibilityCapability.FORWARD_FACTS}),
        unavailable=frozenset({VisibilityCapability.REVERSE_FACTS}),
    ))


def dns():
    value = observation(ObservationType.DNS, DNSObservation("f", True, 1, "example.test", None, None, None, None, "udp", False), {VisibilityCapability.CLEAR_DNS_FIELDS})
    return replace(value, present_fields=frozenset({"qname"}))


def tls():
    value = observation(ObservationType.TLS, TLSObservation("f", "complete", "v1", {"version": "1.3"}, None, None, None, None), {VisibilityCapability.TLS_HANDSHAKE_METADATA})
    return replace(value, present_fields=frozenset({"flow_reference", "parser_version", "parsed_handshake_metadata"}))


def quic():
    return observation(ObservationType.QUIC, QUICObservation("f", "1", "initial", 1, [], "v1", 1, NOW, []), {VisibilityCapability.QUIC_OUTER_METADATA})


def registry():
    return build_mvp_provider_registry(NOW)


def test_exact_packages_lanes_mappings_and_governance():
    plugins, governances = registry()
    assert set(plugins) == {"ddos", "c2", "dga", "dns_tunnelling", "encrypted_session.enc_a", "recon", "unusual_transfer"}
    manifests = [plugin.manifest() for plugin in plugins.values()]
    assert len({m.plugin_id for m in manifests}) == 7
    assert {m.official_ps_category for m in manifests} == set(OfficialPsCategory)
    assert {m.analytic_family for m in manifests} == set(AnalyticFamily)
    assert [m.analytic_family for m in manifests if m.official_ps_category is OfficialPsCategory.DGA_AND_DNS_TUNNELLING] == [AnalyticFamily.DGA, AnalyticFamily.DNS_TUNNELLING]
    for lane, governance in governances.items():
        assert governance.analytic_lane == lane
        assert governance.scientific_status is ScientificStatus.EVIDENCE_CONSTRUCTION
        assert governance.ingest_permitted
        assert governance.allowed_result_types and ResultType.THREAT_ALERT not in governance.allowed_result_types and ResultType.CORRELATION_FINDING not in governance.allowed_result_types
    assert all(m.integration_status is IntegrationStatus.RUNTIME_SCAFFOLD_READY for m in manifests if m.mechanism_id is None)
    enc_a = plugins["encrypted_session.enc_a"].manifest()
    assert enc_a.integration_status is IntegrationStatus.BASELINE_IMPLEMENTED
    assert enc_a.mechanism_id == "ENC-A"


def test_structural_zero_to_many_and_protocol_distinction():
    plugins, _ = registry()
    router = RelevanceRouter(plugins)
    assert set(router.route(flow())) == {"ddos", "c2", "recon", "unusual_transfer"}
    assert set(router.route(dns())) == {"dga", "dns_tunnelling"}
    assert router.route(tls()) == ("encrypted_session.enc_a",)
    assert router.route(quic()) == ()


@pytest.mark.asyncio
async def test_shells_remain_stateless_and_enc_a_only_emits_factual_review_context():
    plugins, _ = registry()
    for plugin in plugins.values():
        value = next(v for v in (flow(), dns(), tls(), quic()) if plugin.route(v))
        assert plugin.state_key(value) is None
        outcome = await plugin.process(value, None, None)
        if plugin.manifest().mechanism_id == "ENC-A":
            assert len(outcome.result_drafts) == 1
            assert outcome.state_transition is None
        else:
            assert outcome == PluginProcessOutcome()
        assert await plugin.on_watermark(NOW, None) == PluginProcessOutcome()
        assert await plugin.on_expire(StateKey("unused"), None, None) == PluginProcessOutcome()
        assert await plugin.on_quality_gap(QualityGap("gap", "lane", NOW, NOW, NOW, 1, ("test",), "test"), None, None) == ()


@pytest.mark.asyncio
async def test_runtime_constructs_every_provider_lane_with_only_enc_a_results():
    plugins, governances = registry()
    results = []
    async def collector(result, lane):
        results.append((result, lane))
    supervisor = RuntimeSupervisor(plugins, governances, collector, shard_count=1)
    assert set(supervisor.dispatchers) == set(plugins) == set(supervisor.state_stores)
    supervisor.start_all()
    try:
        assert set((await supervisor.ingest_observation(flow())).selected_targets) == {"ddos", "c2", "recon", "unusual_transfer"}
        for lane in ("ddos", "c2", "recon", "unusual_transfer"):
            await supervisor.dispatchers[lane].queue.join()
        assert all(len(store) == 0 for store in supervisor.state_stores.values())
        await supervisor.ingest_observation(tls())
        await supervisor.dispatchers["encrypted_session.enc_a"].queue.join()
        assert len(results) == 1
    finally:
        await supervisor.stop_all()
