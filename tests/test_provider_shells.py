"""M6 provider integration shells: structural plumbing only, never detection."""
from datetime import datetime, timezone
from dataclasses import replace

import pytest

from evidencegate.domain.enums import (
    AnalyticFamily, AvailabilityBasis, DirectionBasis, Finality, IdentityBasis,
    IntegrationStatus, ObservationType, OfficialPsCategory, ResultType,
    ScientificStatus, SourceKind, VisibilityCapability, WireDirection,
)
from evidencegate.domain.events import (
    NetworkObservationEnvelope, ObservationIdentity, RoleAssignment,
    VisibilityProfile,
)
from evidencegate.domain.payloads import (
    DNSObservation, FlowObservation, PacketObservation, QUICObservation,
    TLSObservation,
)
from evidencegate.plugins.providers.registry import (
    C2_CONTROLLED_MVP_CAPACITY, DDOS_CONTROLLED_MVP_CAPACITY,
    DDOS_RECON_MVP_ACTIVATION_DECISION_ID, RECON_CONTROLLED_MVP_CAPACITY,
    build_mvp_provider_registry, build_mvp_runtime_registration,
)
from evidencegate.routing.router import RelevanceRouter
from evidencegate.runtime.dispatcher import EventTimeReorderPolicy
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
    value = observation(ObservationType.DNS, DNSObservation(
        "f", True, 1, "example.test", None, None, None, None, "udp", False,
        qname_rendered="example.test", qname_canonical="example.test",
        labels=("example", "test"), representation_version="DNS_NAME_REPRESENTATION_V1",
    ), {VisibilityCapability.CLEAR_DNS_FIELDS})
    return replace(value, present_fields=frozenset({
        "qname", "qname_rendered", "qname_canonical", "labels", "representation_version",
    }))


def tls():
    value = observation(ObservationType.TLS, TLSObservation("f", "complete", "v1", {"version": "1.3"}, None, None, None, None), {VisibilityCapability.TLS_HANDSHAKE_METADATA})
    return replace(value, present_fields=frozenset({"flow_reference", "parser_version", "parsed_handshake_metadata"}))


def quic():
    return observation(ObservationType.QUIC, QUICObservation("f", "1", "initial", 1, [], "v1", 1, NOW, []), {VisibilityCapability.QUIC_OUTER_METADATA})


def registry():
    return build_mvp_provider_registry(NOW)


EXPECTED_TARGETS = {
    "ddos.syn_state", "ddos.udp_demand", "ddos.reflection_victim",
    "ddos.source_diversity", "ddos.icmp_demand", "ddos.fragment_demand",
    "ddos.connection_churn", "c2.r1", "dga.m1", "dns_tunnelling.t1",
    "encrypted_session.enc_a", "recon.h", "recon.v", "recon.2d",
    "recon.tcp", "unusual_transfer.m1",
}


def mixed_tcp_syn():
    initiator, target = "198.51.100.10", "192.0.2.10"
    value = observation(
        ObservationType.PACKET,
        PacketObservation(
            lengths={"ip": 40}, observed_l2_facts={}, observed_l3_facts={},
            observed_l4_facts={}, src_address=initiator, dst_address=target,
            src_port=50000, dst_port=443, flags=["SYN"], sequence_facts=None,
            fragmentation=None, raw_reference="fixture:tcp", protocol=6,
        ),
        {VisibilityCapability.PACKET_FACTS, VisibilityCapability.FORWARD_FACTS},
    )
    return replace(
        value,
        present_fields=frozenset({
            "lengths", "protocol", "src_address", "dst_address", "src_port",
            "dst_port", "flags",
        }),
        visibility=VisibilityProfile(
            available=frozenset({
                VisibilityCapability.PACKET_FACTS,
                VisibilityCapability.FORWARD_FACTS,
            }),
            unavailable=frozenset({VisibilityCapability.REVERSE_FACTS}),
        ),
        identity=ObservationIdentity(
            observed_identifiers=(initiator, target),
            identifier_basis=IdentityBasis.OBSERVED_IDENTIFIER,
            role_assignments=(
                RoleAssignment(initiator, "initiator_id", IdentityBasis.SOURCE_DECLARED_ROLE),
                RoleAssignment(target, "target_id", IdentityBasis.SOURCE_DECLARED_ROLE),
                RoleAssignment("service/https", "service_id", IdentityBasis.SOURCE_DECLARED_ROLE),
            ),
        ),
    )


def test_exact_packages_lanes_mappings_and_governance():
    plugins, governances = registry()
    assert set(plugins) == EXPECTED_TARGETS
    assert "ddos" not in plugins and "recon" not in plugins
    manifests = [plugin.manifest() for plugin in plugins.values()]
    assert len({m.plugin_id for m in manifests}) == 16
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
    dns_t1 = plugins["dns_tunnelling.t1"].manifest()
    assert dns_t1.integration_status is IntegrationStatus.BASELINE_IMPLEMENTED
    assert dns_t1.mechanism_id == "DNS-T1"
    c2_r1 = plugins["c2.r1"].manifest()
    assert c2_r1.mechanism_id == "C2-M1"
    assert c2_r1.state_resource_policy.max_entries == 1024
    assert c2_r1.governing_decision_ids == ("C2-DEC-MVP-CAPACITY-V1",)
    assert governances["c2.r1"].governance_version == "c2-r1-mvp-0.1.0"
    dga_m1 = plugins["dga.m1"].manifest()
    assert dga_m1.mechanism_id == "DGA-A1-M1"
    assert dga_m1.governing_decision_ids == ("C3-DEC-DGA-M1-R1-PROMOTION-V1",)
    activated = tuple(
        plugin for lane, plugin in plugins.items()
        if str(lane).startswith(("ddos.", "recon."))
    )
    assert all(
        plugin.manifest().governing_decision_ids
        == (DDOS_RECON_MVP_ACTIVATION_DECISION_ID,)
        for plugin in activated
    )


def test_structural_zero_to_many_and_protocol_distinction():
    plugins, _ = registry()
    router = RelevanceRouter(plugins)
    assert set(router.route(mixed_tcp_syn())) == {
        "ddos.syn_state", "ddos.source_diversity", "ddos.connection_churn",
        "recon.h", "recon.v", "recon.2d", "recon.tcp",
    }
    assert router.route(flow()) == ()
    assert set(router.route(dns())) == {"dga.m1", "dns_tunnelling.t1"}
    assert router.route(tls()) == ("encrypted_session.enc_a",)
    assert router.route(quic()) == ()


@pytest.mark.asyncio
async def test_remaining_stateless_defaults_emit_only_factual_context():
    plugins, _ = registry()
    for lane in ("dga.m1", "dns_tunnelling.t1", "encrypted_session.enc_a", "unusual_transfer.m1"):
        plugin = plugins[lane]
        candidates = (flow(), dns(), tls(), quic())
        if plugin.manifest().mechanism_id == "CAT6-EX-M1":
            candidates = (replace(
                flow(), present_fields=frozenset({"flow_id_basis", "endpoints", "protocol", "start_time", "end_time", "supplied_directional_counters", "exporter_semantics"}),
                typed_payload=FlowObservation("source-order", ("a", "b"), 6, NOW, NOW, NOW, {"bytes_c2s": 1}, "factual", None, None),
            ),)
        value = next(v for v in candidates if plugin.route(v))
        assert plugin.state_key(value) is None
        outcome = await plugin.process(value, None, None)
        if plugin.manifest().mechanism_id in ("DGA-A1-M1", "ENC-A", "CAT6-EX-M1", "DNS-T1"):
            assert len(outcome.result_drafts) == 1
            assert outcome.state_transition is None
        else:
            assert outcome == PluginProcessOutcome()
        assert await plugin.on_watermark(NOW, None) == PluginProcessOutcome()
        assert await plugin.on_expire(StateKey("unused"), None, None) == PluginProcessOutcome()
        assert await plugin.on_quality_gap(QualityGap("gap", "lane", NOW, NOW, NOW, 1, ("test",), "test"), None, None) == ()


@pytest.mark.asyncio
async def test_runtime_constructs_every_provider_lane_with_implemented_results():
    registration = build_mvp_runtime_registration(NOW)
    plugins, governances = registration.plugins, registration.governances
    results = []
    async def collector(result, lane):
        results.append((result, lane))
    supervisor = RuntimeSupervisor(
        plugins, governances, collector, shard_count=1,
        reorder_policies=registration.reorder_policies,
    )
    assert set(supervisor.dispatchers) == set(plugins) == set(supervisor.state_stores)
    supervisor.start_all()
    try:
        plan = await supervisor.ingest_observation(mixed_tcp_syn())
        assert set(plan.selected_targets) == {
            "ddos.syn_state", "ddos.source_diversity", "ddos.connection_churn",
            "recon.h", "recon.v", "recon.2d", "recon.tcp",
        }
        await supervisor.ingest_observation(tls())
        await supervisor.dispatchers["encrypted_session.enc_a"].queue.join()
        assert len(results) == 1
    finally:
        await supervisor.stop_all()


def test_runtime_registration_has_exact_controlled_mvp_capacity_policies():
    registration = build_mvp_runtime_registration(NOW)
    policies = registration.reorder_policies
    assert set(policies) == {
        "c2.r1", "ddos.syn_state", "ddos.udp_demand",
        "ddos.reflection_victim", "ddos.source_diversity", "ddos.icmp_demand",
        "ddos.fragment_demand", "ddos.connection_churn", "recon.h", "recon.v",
        "recon.2d", "recon.tcp",
    }
    assert policies["ddos.syn_state"] == EventTimeReorderPolicy(16, 2048)
    for lane in (
        "ddos.udp_demand", "ddos.reflection_victim", "ddos.source_diversity",
        "ddos.icmp_demand", "ddos.fragment_demand", "ddos.connection_churn",
    ):
        assert policies[lane] == EventTimeReorderPolicy(256, 2048)
    for lane in ("recon.h", "recon.v", "recon.2d", "recon.tcp"):
        assert policies[lane] == EventTimeReorderPolicy(16, 1024)
    assert DDOS_CONTROLLED_MVP_CAPACITY.decision_id == DDOS_RECON_MVP_ACTIVATION_DECISION_ID
    assert RECON_CONTROLLED_MVP_CAPACITY.decision_id == DDOS_RECON_MVP_ACTIVATION_DECISION_ID
