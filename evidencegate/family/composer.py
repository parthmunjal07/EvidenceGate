"""Pure, deterministic views over immutable mechanism Results.

Family views are analyst presentation contracts. They never rewrite Results,
combine claims, or calculate family-level scores.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
import hashlib
from typing import Iterable

from evidencegate.domain.enums import ResultType
from evidencegate.results.types import Result


OFFICIAL_FAMILIES = (
    "DDoS", "C2 / Beaconing", "DGA + DNS", "Encrypted Sessions",
    "Reconnaissance", "Data Transfer",
)

FAMILY_BY_LANE = {
    **{lane: "DDoS" for lane in (
        "ddos.syn_state", "ddos.udp_demand", "ddos.reflection_victim",
        "ddos.source_diversity", "ddos.icmp_demand", "ddos.fragment_demand",
        "ddos.connection_churn",
    )},
    "c2.r1": "C2 / Beaconing",
    "dga.m1": "DGA + DNS",
    "dns_tunnelling.t1": "DGA + DNS",
    "encrypted_session.enc_a": "Encrypted Sessions",
    **{lane: "Reconnaissance" for lane in (
        "recon.h", "recon.v", "recon.2d", "recon.tcp",
    )},
    "unusual_transfer.m1": "Data Transfer",
}

_LIMITATIONS = {
    "NO_MALWARE_CONFIRMATION": "This evidence does not confirm malware.",
    "NO_INFECTION_INFERENCE": "This evidence does not establish infection.",
    "NO_C2_INFERENCE": "This evidence does not establish command-and-control activity.",
    "NO_DNS_TUNNEL_INFERENCE": "This evidence does not establish DNS tunnelling.",
    "NO_EXFILTRATION_INFERENCE": "This evidence does not establish data exfiltration.",
    "NO_DOMAIN_OWNERSHIP_OR_INTENT": "This evidence does not establish domain ownership or intent.",
    "NO_ATTACK_CONFIRMATION": "This evidence does not confirm an attack.",
    "NO_SOURCE_SPOOFING_INFERENCE": "This evidence does not establish source spoofing.",
    "NO_ATTACKER_IDENTITY": "This evidence does not establish attacker identity.",
    "NO_RESOURCE_EXHAUSTION": "This evidence does not establish victim resource exhaustion.",
    "NO_DDOS_CONFIRMED": "This evidence does not confirm a DDoS attack.",
    "NO_SPOOFING_CONFIRMED": "This evidence does not establish source spoofing.",
}

_FINDING_RESULT_TYPES = frozenset({
    ResultType.THREAT_ALERT,
    ResultType.REVIEW_FINDING,
    ResultType.INSUFFICIENT_EVIDENCE,
})

_STATUS_LIMITATION_TEMPLATES = {
    ResultType.ANALYTIC_UNAVAILABLE: "{title} was unavailable and did not produce an observed finding.",
    ResultType.PREREQUISITE_MISSING: "{title} lacked a required prerequisite and did not produce a complete finding.",
    ResultType.QUALITY_DEGRADED: "{title} reported degraded evidence quality rather than an observed finding.",
    ResultType.PLUGIN_STATUS: "{title} reported analytic status rather than an observed finding.",
}

_MISSING_LABELS = {
    "reverse_tcp_state": "Reverse TCP state was not visible.",
    "reverse_direction": "Reverse direction traffic was not visible.",
}


@dataclass(frozen=True, slots=True)
class FamilyFinding:
    source_result_id: str
    title: str
    statements: tuple[str, ...]
    result_type: str


@dataclass(frozen=True, slots=True)
class FamilyEvidenceView:
    family_view_id: str
    family: str
    time_start: datetime
    time_end: datetime
    entity_references: tuple[str, ...]
    source_result_ids: tuple[str, ...]
    source_observation_ids: tuple[str, ...]
    findings: tuple[FamilyFinding, ...]
    limitations: tuple[str, ...]
    missing_evidence: tuple[str, ...]
    visibility_summary: tuple[str, ...]
    quality_summary: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class InvestigationLink:
    link_id: str
    left_family_view_id: str
    right_family_view_id: str
    relation_types: tuple[str, ...]
    shared_source_observation_ids: tuple[str, ...]
    source_result_ids: tuple[str, ...]
    claim_guard: tuple[str, ...] = (
        "FOR_JOINT_INVESTIGATION_ONLY", "NO_CAUSALITY", "NO_COMMON_ATTACKER",
        "NO_ATTACK_CHAIN_CONFIRMATION", "NO_MALICIOUSNESS_PROBABILITY",
    )


def _display_title(result: Result) -> str:
    lane = result.lane_id
    titles = {
        "ddos.syn_state": "TCP initiating activity",
        "ddos.udp_demand": "UDP demand",
        "ddos.reflection_victim": "Reflection-shaped traffic",
        "ddos.source_diversity": "Source diversity",
        "ddos.icmp_demand": "ICMP demand",
        "ddos.fragment_demand": "Fragment demand",
        "ddos.connection_churn": "Connection churn",
        "c2.r1": "Recurring communication pattern",
        "dga.m1": "DGA-labelled lexical resemblance",
        "dns_tunnelling.t1": "DNS structural evidence",
        "encrypted_session.enc_a": "Encrypted session handshake",
        "recon.h": "Host discovery evidence",
        "recon.v": "Service discovery evidence",
        "recon.2d": "Host and service discovery evidence",
        "recon.tcp": "TCP reconnaissance evidence",
        "unusual_transfer.m1": "Transfer magnitude",
    }
    return titles.get(lane, "Mechanism evidence")


def _result_statements(result: Result) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(item).strip() for item in result.evidence_items if str(item).strip()))


def _limitations(results: Iterable[Result]) -> tuple[str, ...]:
    found: list[str] = []
    for result in results:
        status_template = _STATUS_LIMITATION_TEMPLATES.get(result.result_type)
        if status_template:
            found.append(status_template.format(title=_display_title(result)))
        for token in result.claim_ceiling.split(";"):
            phrase = _LIMITATIONS.get(token.strip())
            if phrase:
                found.append(phrase)
    return tuple(dict.fromkeys(found))


def _missing_evidence(results: Iterable[Result]) -> tuple[str, ...]:
    labels: list[str] = []
    for result in results:
        for value in result.missing_prerequisites:
            normalized = value.strip().lower().replace(" ", "_")
            label = _MISSING_LABELS.get(normalized)
            if label is None:
                readable = value.replace("_", " ").strip()
                label = readable[0].upper() + readable[1:] + " was not available." if readable else "Required evidence was not available."
            labels.append(label)
    return tuple(dict.fromkeys(labels))


def _view_id(family: str, results: Iterable[Result]) -> str:
    seed = family + "\0" + "\0".join(sorted(result.result_id for result in results))
    return "family-" + hashlib.sha256(seed.encode()).hexdigest()[:20]


def compose_family_evidence(results: Iterable[Result]) -> tuple[FamilyEvidenceView, ...]:
    """Compose per-family connected components using source-observation overlap."""
    by_family: dict[str, list[Result]] = defaultdict(list)
    for result in results:
        family = FAMILY_BY_LANE.get(result.lane_id)
        if family:
            by_family[family].append(result)

    views: list[FamilyEvidenceView] = []
    for family in OFFICIAL_FAMILIES:
        remaining = {item.result_id: item for item in by_family.get(family, ())}
        observation_to_results: dict[str, set[str]] = defaultdict(set)
        for result in remaining.values():
            for observation_id in result.source_observation_ids:
                observation_to_results[observation_id].add(result.result_id)
        while remaining:
            seed_id = min(remaining)
            component_ids = {seed_id}
            frontier = [seed_id]
            while frontier:
                result_id = frontier.pop()
                for observation_id in remaining[result_id].source_observation_ids:
                    for related_id in observation_to_results[observation_id]:
                        if related_id not in component_ids:
                            component_ids.add(related_id)
                            frontier.append(related_id)
            component = sorted((remaining.pop(item) for item in component_ids), key=lambda r: (r.created_time, r.result_id))
            times = [value for result in component for value in ((result.evidence_interval or (result.created_time, result.created_time)))]
            missing = _missing_evidence(component)
            visibility_values: set[str] = set()
            quality_values: set[str] = set()
            for result in component:
                visibility_values.update(
                    f"{key}:{value}" for key, values in (
                        ("available", result.visibility_snapshot.available),
                        ("unavailable", result.visibility_snapshot.unavailable),
                        ("degraded", result.visibility_snapshot.degraded),
                    ) for value in values
                )
                quality_values.update((
                    f"packet_loss:{result.quality_snapshot.packet_loss.value}",
                    f"sampling:{result.quality_snapshot.sampling.value}",
                    f"parser:{result.quality_snapshot.parser.value}",
                    f"capture_gap:{result.quality_snapshot.capture_gap.value}",
                ))
            views.append(FamilyEvidenceView(
                family_view_id=_view_id(family, component), family=family,
                time_start=min(times), time_end=max(times),
                entity_references=tuple(sorted({result.entity_reference for result in component})),
                source_result_ids=tuple(result.result_id for result in component),
                source_observation_ids=tuple(sorted({
                    item for result in component for item in result.source_observation_ids
                })),
                findings=tuple(FamilyFinding(
                    source_result_id=result.result_id, title=_display_title(result),
                    statements=_result_statements(result), result_type=result.result_type.value,
                ) for result in component if result.result_type in _FINDING_RESULT_TYPES),
                limitations=_limitations(component), missing_evidence=missing,
                visibility_summary=tuple(sorted(visibility_values)),
                quality_summary=tuple(sorted(quality_values)),
            ))
    return tuple(sorted(views, key=lambda view: (view.time_start, view.family, view.family_view_id)))


def index_investigations(views: Iterable[FamilyEvidenceView]) -> tuple[InvestigationLink, ...]:
    """Build only exact shared-observation links via an inverted index."""
    by_observation: dict[str, list[FamilyEvidenceView]] = defaultdict(list)
    for view in views:
        for observation_id in view.source_observation_ids:
            by_observation[observation_id].append(view)
    shared: dict[tuple[str, str], set[str]] = defaultdict(set)
    by_id = {view.family_view_id: view for view in views}
    for observation_id, matching_views in by_observation.items():
        unique = {view.family_view_id: view for view in matching_views}
        ordered = sorted(unique)
        # This enumerates candidates only within a factual observation bucket.
        for left_index, left_id in enumerate(ordered):
            for right_id in ordered[left_index + 1:]:
                if by_id[left_id].family != by_id[right_id].family:
                    shared[(left_id, right_id)].add(observation_id)
    links = []
    for (left_id, right_id), observation_ids in sorted(shared.items()):
        left, right = by_id[left_id], by_id[right_id]
        result_ids = tuple(sorted(set(left.source_result_ids) | set(right.source_result_ids)))
        link_seed = "\0".join((left_id, right_id, *sorted(observation_ids)))
        links.append(InvestigationLink(
            link_id="investigation-" + hashlib.sha256(link_seed.encode()).hexdigest()[:20],
            left_family_view_id=left_id, right_family_view_id=right_id,
            relation_types=("SHARED_SOURCE_OBSERVATION",),
            shared_source_observation_ids=tuple(sorted(observation_ids)),
            source_result_ids=result_ids,
        ))
    return tuple(links)
