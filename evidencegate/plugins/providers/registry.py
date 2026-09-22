"""Explicit, deterministic controlled-MVP runtime registration."""
from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

from evidencegate.domain.enums import ResultType, ScientificStatus
from evidencegate.domain.governance import LaneGovernance
from evidencegate.registry.plugin import AnalyticPlugin
from evidencegate.routing.router import LaneTarget
from .c2 import C2R1Plugin
from .c2_config import C2R1Config
from .ddos import DDOS_A_CLAIM_CEILING, DdosASynPlugin
from .ddos_config import (
    DdosASynConfig, DdosConnectionChurnConfig, DdosFragmentDemandConfig,
    DdosIcmpDemandConfig, DdosReflectionVictimConfig,
    DdosSourceDiversityConfig, DdosUdpDemandConfig,
)
from .ddos_measurements import (
    DdosConnectionChurnPlugin, DdosFragmentDemandPlugin,
    DdosIcmpDemandPlugin, DdosReflectionVictimPlugin,
    DdosSourceDiversityPlugin, DdosUdpDemandPlugin,
)
from .dns_dga import DgaShellPlugin, DnsT1StructuralPlugin
from .encrypted import EncAHandshakePlugin
from .exfil import ExfilM1TransferPlugin
from .recon import (
    CLAIM_CEILING as RECON_CLAIM_CEILING,
    Recon2DPlugin, ReconHPlugin, ReconTcpPlugin, ReconVPlugin,
)
from .recon_config import ReconConfig
from evidencegate.runtime.dispatcher import EventTimeReorderPolicy


C2_MVP_CAPACITY_DECISION_ID = "C2-DEC-MVP-CAPACITY-V1"
DDOS_RECON_MVP_ACTIVATION_DECISION_ID = "DDOS-RECON-DEC-MVP-ACTIVATION-V1"


@dataclass(frozen=True, slots=True)
class ControlledMvpC2RuntimeCapacity:
    """Human-gated engineering containment bounds, not scientific settings."""

    decision_id: str = C2_MVP_CAPACITY_DECISION_ID
    max_state_entries: int = 1024
    max_buffered_events_per_key: int = 16
    max_buffered_events_total: int = 2048


C2_CONTROLLED_MVP_CAPACITY = ControlledMvpC2RuntimeCapacity()


@dataclass(frozen=True, slots=True)
class ControlledMvpDdosRuntimeCapacity:
    """Human-gated controlled-MVP DDoS engineering containment bounds."""

    decision_id: str = DDOS_RECON_MVP_ACTIVATION_DECISION_ID
    syn_max_state_entries: int = 1024
    syn_max_buffered_events_per_key: int = 16
    syn_max_buffered_events_total: int = 2048
    window_max_state_entries: int = 512
    window_max_buffered_events_per_key: int = 256
    window_max_buffered_events_total: int = 2048
    max_sources_per_window: int = 256
    max_attempts_per_window: int = 256


@dataclass(frozen=True, slots=True)
class ControlledMvpReconRuntimeCapacity:
    """Human-gated controlled-MVP Recon engineering containment bounds."""

    decision_id: str = DDOS_RECON_MVP_ACTIVATION_DECISION_ID
    max_state_entries: int = 1024
    max_buffered_events_per_key: int = 16
    max_buffered_events_total: int = 1024


DDOS_CONTROLLED_MVP_CAPACITY = ControlledMvpDdosRuntimeCapacity()
RECON_CONTROLLED_MVP_CAPACITY = ControlledMvpReconRuntimeCapacity()


@dataclass(frozen=True, slots=True)
class MvpRuntimeRegistration:
    plugins: dict[LaneTarget, AnalyticPlugin]
    governances: dict[LaneTarget, LaneGovernance]
    reorder_policies: Mapping[LaneTarget, EventTimeReorderPolicy]


def build_mvp_provider_registry(effective_at: datetime) -> tuple[dict[LaneTarget, AnalyticPlugin], dict[LaneTarget, LaneGovernance]]:
    """Return the default MVP providers for inspection and isolated tests."""
    ddos_capacity = DDOS_CONTROLLED_MVP_CAPACITY
    recon_capacity = RECON_CONTROLLED_MVP_CAPACITY
    recon_config = ReconConfig.controlled_mvp_v1()
    decision_ids = (DDOS_RECON_MVP_ACTIVATION_DECISION_ID,)
    plugins = {
        LaneTarget("ddos.syn_state"): DdosASynPlugin(
            DdosASynConfig.reference_poc_v1(),
            max_state_entries=ddos_capacity.syn_max_state_entries,
            governing_decision_ids=decision_ids,
        ),
        LaneTarget("ddos.udp_demand"): DdosUdpDemandPlugin(
            DdosUdpDemandConfig.reference_poc_v1(),
            max_state_entries=ddos_capacity.window_max_state_entries,
            governing_decision_ids=decision_ids,
        ),
        LaneTarget("ddos.reflection_victim"): DdosReflectionVictimPlugin(
            DdosReflectionVictimConfig.reference_poc_v1(),
            max_state_entries=ddos_capacity.window_max_state_entries,
            max_sources_per_window=ddos_capacity.max_sources_per_window,
            governing_decision_ids=decision_ids,
        ),
        LaneTarget("ddos.source_diversity"): DdosSourceDiversityPlugin(
            DdosSourceDiversityConfig.reference_poc_v1(),
            max_state_entries=ddos_capacity.window_max_state_entries,
            max_sources_per_window=ddos_capacity.max_sources_per_window,
            governing_decision_ids=decision_ids,
        ),
        LaneTarget("ddos.icmp_demand"): DdosIcmpDemandPlugin(
            DdosIcmpDemandConfig.reference_poc_v1(),
            max_state_entries=ddos_capacity.window_max_state_entries,
            governing_decision_ids=decision_ids,
        ),
        LaneTarget("ddos.fragment_demand"): DdosFragmentDemandPlugin(
            DdosFragmentDemandConfig.reference_poc_v1(),
            max_state_entries=ddos_capacity.window_max_state_entries,
            governing_decision_ids=decision_ids,
        ),
        LaneTarget("ddos.connection_churn"): DdosConnectionChurnPlugin(
            DdosConnectionChurnConfig.reference_poc_v1(),
            max_state_entries=ddos_capacity.window_max_state_entries,
            max_attempts_per_window=ddos_capacity.max_attempts_per_window,
            governing_decision_ids=decision_ids,
        ),
        LaneTarget("c2.r1"): C2R1Plugin(
            C2R1Config.reference_engine_v1(),
            max_state_entries=C2_CONTROLLED_MVP_CAPACITY.max_state_entries,
            governing_decision_ids=(C2_CONTROLLED_MVP_CAPACITY.decision_id,),
        ),
        LaneTarget("dga"): DgaShellPlugin(),
        LaneTarget("dns_tunnelling.t1"): DnsT1StructuralPlugin(),
        LaneTarget("encrypted_session.enc_a"): EncAHandshakePlugin(),
        LaneTarget("recon.h"): ReconHPlugin(
            recon_config, max_state_entries=recon_capacity.max_state_entries,
            governing_decision_ids=decision_ids,
        ),
        LaneTarget("recon.v"): ReconVPlugin(
            recon_config, max_state_entries=recon_capacity.max_state_entries,
            governing_decision_ids=decision_ids,
        ),
        LaneTarget("recon.2d"): Recon2DPlugin(
            recon_config, max_state_entries=recon_capacity.max_state_entries,
            governing_decision_ids=decision_ids,
        ),
        LaneTarget("recon.tcp"): ReconTcpPlugin(
            recon_config, max_state_entries=recon_capacity.max_state_entries,
            governing_decision_ids=decision_ids,
        ),
        LaneTarget("unusual_transfer.m1"): ExfilM1TransferPlugin(),
    }
    governances = {
        lane: LaneGovernance(
            analytic_lane=str(lane), scientific_status=ScientificStatus.EVIDENCE_CONSTRUCTION,
            scientific_phase="provider shell integration", scientific_blockers=("mechanisms not implemented",),
            claim_ceiling="NO_SCIENTIFIC_CLAIMS", governance_version="m6-shell-0.1.0",
            effective_at=effective_at,
            allowed_result_types=(ResultType.QUALITY_DEGRADED, ResultType.PLUGIN_STATUS),
            ingest_permitted=True,
        )
        for lane in plugins
    }
    enc_a_lane = LaneTarget("encrypted_session.enc_a")
    governances[enc_a_lane] = LaneGovernance(
        analytic_lane=str(enc_a_lane), scientific_status=ScientificStatus.EVIDENCE_CONSTRUCTION,
        scientific_phase="visible TLS handshake evidence construction", scientific_blockers=(),
        claim_ceiling=("VISIBLE_CLIENTHELLO_FINGERPRINT_CONTEXT_ONLY; PROHIBITS "
                       "MALWARE_CONFIRMED, COMPROMISE, C2, EXFILTRATION, DECRYPTED_CONTENT"),
        governance_version="enc-a-0.1.0", effective_at=effective_at,
        allowed_result_types=(
            ResultType.REVIEW_FINDING, ResultType.PREREQUISITE_MISSING,
            ResultType.QUALITY_DEGRADED, ResultType.ANALYTIC_UNAVAILABLE,
        ), ingest_permitted=True,
    )
    exfil_m1_lane = LaneTarget("unusual_transfer.m1")
    governances[exfil_m1_lane] = LaneGovernance(
        analytic_lane=str(exfil_m1_lane), scientific_status=ScientificStatus.EVIDENCE_CONSTRUCTION,
        scientific_phase="factual directional transfer magnitude measurement", scientific_blockers=(),
        claim_ceiling=("TRANSFER_MAGNITUDE_ONLY; NO_UNUSUALNESS; NO_AUTHORIZATION_INFERENCE; "
                       "NO_DATA_SENSITIVITY; NO_EXFILTRATION_CONFIRMED; NO_THEFT"),
        governance_version="cat6-ex-m1-0.1.0", effective_at=effective_at,
        allowed_result_types=(ResultType.REVIEW_FINDING,), ingest_permitted=True,
    )
    dns_t1_lane = LaneTarget("dns_tunnelling.t1")
    governances[dns_t1_lane] = LaneGovernance(
        analytic_lane=str(dns_t1_lane), scientific_status=ScientificStatus.EVIDENCE_CONSTRUCTION,
        scientific_phase="factual DNS name structure evidence", scientific_blockers=(),
        claim_ceiling=("RAW_OBSERVATION_ONLY; NO_DNS_TUNNEL_VERDICT; NO_EXFILTRATION; "
                       "NO_C2; NO_MALWARE"),
        governance_version="dns-t1-0.1.0", effective_at=effective_at,
        allowed_result_types=(ResultType.REVIEW_FINDING,), ingest_permitted=True,
    )
    c2_r1_lane = LaneTarget("c2.r1")
    governances[c2_r1_lane] = LaneGovernance(
        analytic_lane=str(c2_r1_lane), scientific_status=ScientificStatus.EVIDENCE_CONSTRUCTION,
        scientific_phase="descriptive recurrence measurement", scientific_blockers=(),
        claim_ceiling=("RECURRENT_COMMUNICATION_MEASUREMENT_ONLY; NOT_C2; NOT_MALWARE; "
                       "NOT_COMPROMISE; NOT_BENIGN"),
        governance_version="c2-r1-mvp-0.1.0", effective_at=effective_at,
        allowed_result_types=(
            ResultType.REVIEW_FINDING, ResultType.INSUFFICIENT_EVIDENCE,
            ResultType.PREREQUISITE_MISSING, ResultType.QUALITY_DEGRADED,
        ), ingest_permitted=True,
    )
    ddos_phases = {
        "ddos.syn_state": "captured TCP SYN/state evidence construction",
        "ddos.udp_demand": "factual UDP demand measurement",
        "ddos.reflection_victim": "protocol-gated victim-side reflection-shape measurement",
        "ddos.source_diversity": "apparent source distribution measurement",
        "ddos.icmp_demand": "factual ICMP demand measurement",
        "ddos.fragment_demand": "factual fragment demand measurement",
        "ddos.connection_churn": "factual TCP initiating-attempt measurement",
    }
    for lane_name, phase in ddos_phases.items():
        lane = LaneTarget(lane_name)
        plugin = plugins[lane]
        claim_ceiling = (
            DDOS_A_CLAIM_CEILING if lane_name == "ddos.syn_state"
            else plugin.claim_ceiling
        )
        governances[lane] = LaneGovernance(
            analytic_lane=lane_name,
            scientific_status=ScientificStatus.EVIDENCE_CONSTRUCTION,
            scientific_phase=phase, scientific_blockers=(),
            claim_ceiling=claim_ceiling,
            governance_version=f"{plugin.manifest().mechanism_id.lower()}-mvp-0.1.0",
            effective_at=effective_at,
            allowed_result_types=plugin.manifest().allowed_result_types,
            ingest_permitted=True,
        )
    recon_phases = {
        "recon.h": "horizontal breadth measurement",
        "recon.v": "target-port breadth measurement",
        "recon.2d": "host x port geometry measurement",
        "recon.tcp": "captured TCP probing-state measurement",
    }
    for lane_name, phase in recon_phases.items():
        lane = LaneTarget(lane_name)
        plugin = plugins[lane]
        governances[lane] = LaneGovernance(
            analytic_lane=lane_name,
            scientific_status=ScientificStatus.EVIDENCE_CONSTRUCTION,
            scientific_phase=phase, scientific_blockers=(),
            claim_ceiling=RECON_CLAIM_CEILING,
            governance_version=f"{plugin.manifest().mechanism_id.lower()}-mvp-0.1.0",
            effective_at=effective_at,
            allowed_result_types=plugin.manifest().allowed_result_types,
            ingest_permitted=True,
        )
    return plugins, governances


def build_mvp_runtime_registration(effective_at: datetime) -> MvpRuntimeRegistration:
    """Return all required default runtime inputs as one atomic registration."""
    plugins, governances = build_mvp_provider_registry(effective_at)
    c2_capacity = C2_CONTROLLED_MVP_CAPACITY
    ddos_capacity = DDOS_CONTROLLED_MVP_CAPACITY
    recon_capacity = RECON_CONTROLLED_MVP_CAPACITY
    policies = {
        LaneTarget("c2.r1"): EventTimeReorderPolicy(
            max_buffered_events_per_key=c2_capacity.max_buffered_events_per_key,
            max_buffered_events_total=c2_capacity.max_buffered_events_total,
        ),
        LaneTarget("ddos.syn_state"): EventTimeReorderPolicy(
            max_buffered_events_per_key=ddos_capacity.syn_max_buffered_events_per_key,
            max_buffered_events_total=ddos_capacity.syn_max_buffered_events_total,
        ),
    }
    for lane_name in (
        "ddos.udp_demand", "ddos.reflection_victim", "ddos.source_diversity",
        "ddos.icmp_demand", "ddos.fragment_demand", "ddos.connection_churn",
    ):
        policies[LaneTarget(lane_name)] = EventTimeReorderPolicy(
            max_buffered_events_per_key=ddos_capacity.window_max_buffered_events_per_key,
            max_buffered_events_total=ddos_capacity.window_max_buffered_events_total,
        )
    for lane_name in ("recon.h", "recon.v", "recon.2d", "recon.tcp"):
        policies[LaneTarget(lane_name)] = EventTimeReorderPolicy(
            max_buffered_events_per_key=recon_capacity.max_buffered_events_per_key,
            max_buffered_events_total=recon_capacity.max_buffered_events_total,
        )
    return MvpRuntimeRegistration(
        plugins=plugins,
        governances=governances,
        reorder_policies=policies,
    )
