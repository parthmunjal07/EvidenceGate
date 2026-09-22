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
from .ddos import DdosShellPlugin
from .dns_dga import DgaShellPlugin, DnsT1StructuralPlugin
from .encrypted import EncAHandshakePlugin
from .exfil import ExfilM1TransferPlugin
from .recon import ReconShellPlugin
from evidencegate.runtime.dispatcher import EventTimeReorderPolicy


C2_MVP_CAPACITY_DECISION_ID = "C2-DEC-MVP-CAPACITY-V1"


@dataclass(frozen=True, slots=True)
class ControlledMvpC2RuntimeCapacity:
    """Human-gated engineering containment bounds, not scientific settings."""

    decision_id: str = C2_MVP_CAPACITY_DECISION_ID
    max_state_entries: int = 1024
    max_buffered_events_per_key: int = 16
    max_buffered_events_total: int = 2048


C2_CONTROLLED_MVP_CAPACITY = ControlledMvpC2RuntimeCapacity()


@dataclass(frozen=True, slots=True)
class MvpRuntimeRegistration:
    plugins: dict[LaneTarget, AnalyticPlugin]
    governances: dict[LaneTarget, LaneGovernance]
    reorder_policies: Mapping[LaneTarget, EventTimeReorderPolicy]


def build_mvp_provider_registry(effective_at: datetime) -> tuple[dict[LaneTarget, AnalyticPlugin], dict[LaneTarget, LaneGovernance]]:
    """Return the default MVP providers for inspection and isolated tests."""
    plugins = {
        LaneTarget("ddos"): DdosShellPlugin(),
        LaneTarget("c2.r1"): C2R1Plugin(
            C2R1Config.reference_engine_v1(),
            max_state_entries=C2_CONTROLLED_MVP_CAPACITY.max_state_entries,
            governing_decision_ids=(C2_CONTROLLED_MVP_CAPACITY.decision_id,),
        ),
        LaneTarget("dga"): DgaShellPlugin(),
        LaneTarget("dns_tunnelling.t1"): DnsT1StructuralPlugin(),
        LaneTarget("encrypted_session.enc_a"): EncAHandshakePlugin(),
        LaneTarget("recon"): ReconShellPlugin(),
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
    return plugins, governances


def build_mvp_runtime_registration(effective_at: datetime) -> MvpRuntimeRegistration:
    """Return all required default runtime inputs as one atomic registration."""
    plugins, governances = build_mvp_provider_registry(effective_at)
    c2_lane = LaneTarget("c2.r1")
    capacity = C2_CONTROLLED_MVP_CAPACITY
    return MvpRuntimeRegistration(
        plugins=plugins,
        governances=governances,
        reorder_policies={
            c2_lane: EventTimeReorderPolicy(
                max_buffered_events_per_key=capacity.max_buffered_events_per_key,
                max_buffered_events_total=capacity.max_buffered_events_total,
            ),
        },
    )
