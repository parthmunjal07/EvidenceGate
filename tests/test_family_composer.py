from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta, timezone
from time import perf_counter

from evidencegate.domain.enums import (
    EvidenceReadiness,
    IntegrationStatus,
    ResultType,
    ScientificStatus,
)
from evidencegate.domain.events import VisibilityProfile
from evidencegate.domain.quality import EvidenceQuality
from evidencegate.family.composer import (
    FAMILY_BY_LANE,
    OFFICIAL_FAMILIES,
    compose_family_evidence,
    index_investigations,
)
from evidencegate.results.finalizer import result_id_for
from evidencegate.results.types import EvidencePayload, ResultStatusSnapshot, ReviewFinding


NOW = datetime(2026, 9, 26, tzinfo=timezone.utc)


def result(
    lane: str, suffix: str, observations: tuple[str, ...], *, missing=(), claim="FACTUAL_ONLY"
):
    value = ReviewFinding(
        result_id="",
        schema_version="3.0",
        result_type=ResultType.REVIEW_FINDING,
        created_time=NOW
        + timedelta(seconds=int(suffix.split("-")[-1]) if suffix.split("-")[-1].isdigit() else 0),
        lane_id=lane,
        plugin_id=f"provider.{lane}",
        plugin_version="1",
        analytic_version="1",
        governance_version="gov-1",
        entity_reference="192.0.2.10",
        taxonomy=("network", lane, "evidence"),
        status_snapshot=ResultStatusSnapshot(
            ScientificStatus.EVIDENCE_CONSTRUCTION,
            IntegrationStatus.BASELINE_IMPLEMENTED,
            "gov-1",
            EvidenceReadiness.READY,
            False,
        ),
        claim_ceiling=claim,
        evidence_items=(f"Observed {lane} behaviour.",),
        missing_prerequisites=tuple(missing),
        governing_ids=("decision-1",),
        quality_refs=(),
        provenance_refs=(),
        mechanism_id=lane.upper(),
        evidence=EvidencePayload.from_value({"sample": suffix}),
        source_observation_ids=observations,
        source_ids=(),
        quality_snapshot=EvidenceQuality(),
        visibility_snapshot=VisibilityProfile(),
    )
    return dataclasses.replace(value, result_id=result_id_for(value))


def test_official_family_mapping_is_centralized_and_has_six_groups():
    assert len(OFFICIAL_FAMILIES) == 6
    assert len(FAMILY_BY_LANE) == 16
    assert FAMILY_BY_LANE["dga.m1"] == FAMILY_BY_LANE["dns_tunnelling.t1"] == "DGA + DNS"


def test_ddos_lineage_components_and_unrelated_result_stay_separate():
    source = [
        result("ddos.syn_state", "1", ("obs-1",)),
        result("ddos.source_diversity", "2", ("obs-1",)),
        result("ddos.connection_churn", "3", ("obs-1", "obs-2"), missing=("reverse TCP state",)),
        result("ddos.udp_demand", "4", ("obs-9",)),
    ]
    before = tuple(
        (item.result_id, item.evidence.canonical_json, item.claim_ceiling) for item in source
    )
    views = compose_family_evidence(source)
    ddos = [view for view in views if view.family == "DDoS"]
    assert sorted(len(view.source_result_ids) for view in ddos) == [1, 3]
    component = next(view for view in ddos if len(view.source_result_ids) == 3)
    assert len(component.findings) == 3
    assert component.missing_evidence == ("Reverse TCP state was not visible.",)
    assert not hasattr(component, "score")
    assert before == tuple(
        (item.result_id, item.evidence.canonical_json, item.claim_ceiling) for item in source
    )


def test_dga_dns_and_recon_findings_stay_independent_and_link_factually():
    sources = [
        result("dga.m1", "1", ("obs-dns",)),
        result("dns_tunnelling.t1", "2", ("obs-dns",)),
        result("recon.h", "3", ("obs-mixed",)),
        result("recon.v", "4", ("obs-mixed",)),
        result("ddos.syn_state", "5", ("obs-mixed",)),
    ]
    views = compose_family_evidence(sources)
    dga_dns = next(view for view in views if view.family == "DGA + DNS")
    assert len(dga_dns.findings) == 2
    recon = next(view for view in views if view.family == "Reconnaissance")
    assert len(recon.findings) == 2
    links = index_investigations(views)
    assert len(links) == 1
    link = links[0]
    assert link.relation_types == ("SHARED_SOURCE_OBSERVATION",)
    assert link.shared_source_observation_ids == ("obs-mixed",)
    assert "NO_CAUSALITY" in link.claim_guard
    assert "NO_COMMON_ATTACKER" in link.claim_guard


def test_unavailable_result_stays_in_lineage_but_is_not_an_observed_finding():
    unavailable = result("dga.m1", "1", ("obs-dns",))
    unavailable = dataclasses.replace(
        unavailable,
        result_type=ResultType.ANALYTIC_UNAVAILABLE,
        evidence_items=(),
    )
    unavailable = dataclasses.replace(unavailable, result_id=result_id_for(unavailable))
    dns = result("dns_tunnelling.t1", "2", ("obs-dns",))
    view = next(
        item for item in compose_family_evidence([unavailable, dns]) if item.family == "DGA + DNS"
    )
    assert set(view.source_result_ids) == {unavailable.result_id, dns.result_id}
    assert tuple(item.source_result_id for item in view.findings) == (dns.result_id,)
    assert any("unavailable" in item.lower() for item in view.limitations)


def test_unrelated_families_do_not_link():
    views = compose_family_evidence(
        [
            result("ddos.syn_state", "1", ("obs-a",)),
            result("recon.h", "2", ("obs-b",)),
        ]
    )
    assert index_investigations(views) == ()


def test_indexed_candidate_construction_scales_by_observation_buckets():
    views = compose_family_evidence(
        [result("ddos.syn_state", str(i), (f"obs-{i}",)) for i in range(1200)]
        + [result("recon.h", f"r{i}", (f"obs-{i}",)) for i in range(1200)]
    )
    started = perf_counter()
    links = index_investigations(views)
    elapsed = perf_counter() - started
    assert len(views) == 2400
    assert sum(len(view.source_observation_ids) for view in views) == 2400
    assert len(links) == 1200
    assert elapsed < 3.0
