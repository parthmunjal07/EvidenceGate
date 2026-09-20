from dataclasses import replace
from datetime import datetime, timezone

import pytest

from evidencegate.admission.evaluator import AdmissionEvaluator
from evidencegate.domain.enums import (
    AvailabilityBasis, CapabilityState, DirectionBasis, Finality, GapAction,
    IntegrationStatus, ObservationType, QualityFact, QualityState, ResultType,
    RouteReason, ScientificStatus, SourceKind, VisibilityCapability, WireDirection,
)
from evidencegate.domain.events import NetworkObservationEnvelope, VisibilityProfile
from evidencegate.domain.governance import LaneGovernance
from evidencegate.domain.payloads import PacketObservation
from evidencegate.domain.quality import EvidenceQuality, QualityRequirement
from evidencegate.metrics.registry import registry
from evidencegate.plugins.scaffolds.basic_scaffold import BasicScaffoldPlugin
from evidencegate.routing.router import LaneTarget, RelevanceRouter
from evidencegate.runtime.supervisor import RuntimeSupervisor


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def observation(**changes):
    values = dict(
        observation_id="router-1", schema_version="1.1", observation_type=ObservationType.PACKET,
        event_time=NOW, causal_available_time=NOW, ingest_time=NOW, source_id="source",
        source_kind=SourceKind.PCAP, source_position="1", observation_contract="packet_v1",
        wire_direction=WireDirection.UNKNOWN, direction_basis=DirectionBasis.UNKNOWN,
        finality=Finality.CURRENT, availability_basis=AvailabilityBasis.IMMEDIATE,
        provenance_ref="prov:test", quality_ref="", present_fields=frozenset({"src_address"}),
        typed_payload=PacketObservation({}, {}, {}, {}, "10.0.0.1", None, None, None, None, None, None, None),
    )
    values.update(changes)
    return NetworkObservationEnvelope(**values)


class Plugin(BasicScaffoldPlugin):
    def __init__(self, **manifest_changes):
        self.manifest_changes = manifest_changes
        self.calls = 0
        self.answer = True
        self.error = None

    def manifest(self):
        return replace(super().manifest(), **self.manifest_changes)

    def route(self, value):
        self.calls += 1
        if self.error:
            raise self.error
        return self.answer


def plugin(name, **changes):
    changes.setdefault("accepted_observation_types", (ObservationType.PACKET,))
    return Plugin(plugin_id=name, **changes)


def test_zero_one_many_and_deterministic_registration_order():
    a, b, c = plugin("a"), plugin("b"), plugin("c")
    c.answer = False
    router = RelevanceRouter({LaneTarget("a"): a, LaneTarget("b"): b, LaneTarget("c"): c})
    first = router.plan(observation())
    assert first.selected_targets == (LaneTarget("a"), LaneTarget("b"))
    assert first.decisions[-1].reasons == (RouteReason.PREDICATE_FALSE,)
    assert router.plan(observation()) == first
    assert RelevanceRouter({LaneTarget("dns"): plugin("dns", accepted_observation_types=(ObservationType.DNS,))}).plan(observation()).selected_targets == ()


def test_one_way_and_strict_visibility_capabilities():
    forward = plugin("forward", required_visibility_capabilities=frozenset({VisibilityCapability.FORWARD_FACTS}))
    reverse = plugin("reverse", required_visibility_capabilities=frozenset({VisibilityCapability.REVERSE_FACTS}))
    both = plugin("both", required_visibility_capabilities=frozenset({VisibilityCapability.FORWARD_FACTS, VisibilityCapability.REVERSE_FACTS}))
    agnostic = plugin("agnostic")
    router = RelevanceRouter({LaneTarget("forward"): forward, LaneTarget("reverse"): reverse, LaneTarget("agnostic"): agnostic, LaneTarget("both"): both})
    value = observation(visibility=VisibilityProfile(available=frozenset({VisibilityCapability.FORWARD_FACTS}), unavailable=frozenset({VisibilityCapability.REVERSE_FACTS})))
    plan = router.plan(value)
    assert plan.selected_targets == (LaneTarget("forward"), LaneTarget("agnostic"))
    assert plan.decisions[1].reasons == (RouteReason.REQUIRED_CAPABILITY_UNAVAILABLE,)
    assert plan.decisions[3].reasons == (RouteReason.REQUIRED_CAPABILITY_UNAVAILABLE,)
    dns = plugin("dns", required_visibility_capabilities=frozenset({VisibilityCapability.CLEAR_DNS_FIELDS}))
    assert RelevanceRouter({LaneTarget("dns"): dns}).plan(observation()).decisions[0].reasons == (RouteReason.REQUIRED_CAPABILITY_UNAVAILABLE,)
    degraded = observation(visibility=VisibilityProfile(degraded=frozenset({VisibilityCapability.CLEAR_DNS_FIELDS})))
    assert RelevanceRouter({LaneTarget("dns"): dns}).plan(degraded).selected_targets == ()


@pytest.mark.parametrize("changes,reason", [
    ({"required_observation_contracts": ("dns_v1",)}, RouteReason.CONTRACT_MISMATCH),
    ({"required_fields": ("src_port",)}, RouteReason.REQUIRED_FIELD_MISSING),
    ({"allowed_finality": (Finality.TERMINAL,)}, RouteReason.FINALITY_UNSUPPORTED),
    ({"allowed_availability_basis": (AvailabilityBasis.FLOW_END_ONLY,)}, RouteReason.AVAILABILITY_UNSUPPORTED),
])
def test_structural_filters_do_not_call_predicate(changes, reason):
    candidate = plugin("candidate", **changes)
    decision = RelevanceRouter({LaneTarget("candidate"): candidate}).plan(observation()).decisions[0]
    assert not decision.selected and reason in decision.reasons and candidate.calls == 0


def test_predicate_false_and_error_are_isolated():
    bad, good = plugin("bad"), plugin("good")
    bad.error = RuntimeError("broken predicate")
    good.answer = True
    plan = RelevanceRouter({LaneTarget("bad"): bad, LaneTarget("good"): good}).plan(observation())
    assert plan.selected_targets == (LaneTarget("good"),)
    assert plan.decisions[0].reasons == (RouteReason.PREDICATE_ERROR,)
    good.answer = False
    assert RelevanceRouter({LaneTarget("good"): good}).plan(observation()).decisions[0].reasons == (RouteReason.PREDICATE_FALSE,)


def test_quality_is_not_a_routing_filter_but_admission_rejects():
    candidate = plugin("quality", required_quality=(QualityRequirement(QualityFact.SAMPLING, frozenset({QualityState.CLEAR})),))
    value = observation(quality_ref="quality:test", quality=EvidenceQuality(sampling=QualityState.DEGRADED))
    assert RelevanceRouter({LaneTarget("quality"): candidate}).plan(value).selected_targets == (LaneTarget("quality"),)
    governance = LaneGovernance("quality", ScientificStatus.EVIDENCE_CONSTRUCTION, "test", (), "REVIEW", "v1", NOW, (ResultType.REVIEW_FINDING,), True)
    assert not AdmissionEvaluator.evaluate(value, candidate.manifest(), governance).admitted


def test_duplicate_plugin_ids_fail_at_registration():
    with pytest.raises(ValueError, match="duplicate plugin_id"):
        RelevanceRouter({LaneTarget("one"): plugin("same"), LaneTarget("two"): plugin("same")})


@pytest.mark.asyncio
async def test_supervisor_emits_router_error_routes_independent_lane_and_counts_metric():
    bad, good = plugin("bad"), plugin("good")
    bad.error = ValueError("bad route")
    controls, delivered = [], []
    governance = LaneGovernance("good", ScientificStatus.EVIDENCE_CONSTRUCTION, "test", (), "REVIEW", "v1", NOW, (ResultType.REVIEW_FINDING,), True)
    supervisor = RuntimeSupervisor({LaneTarget("bad"): bad, LaneTarget("good"): good}, {LaneTarget("good"): governance}, lambda result, target: delivered.append((result, target)), shard_count=1, control_sink=lambda event: controls.append(event))
    # The router metric is incremented at selection, before dispatch work.
    metric = registry.routed_rate.labels(lane="good", observation_type="PACKET")
    before = metric._value.get()
    plan = await supervisor.ingest_observation(observation())
    assert plan.selected_targets == (LaneTarget("good"),)
    assert metric._value.get() == before + 1
    assert controls[0].typed_payload["component"] == "router"
    assert controls[0].typed_payload["plugin_id"] == "bad"
    assert supervisor.dispatchers[LaneTarget("good")].queue.qsize() == 1
