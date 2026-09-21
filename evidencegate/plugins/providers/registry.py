"""Explicit, deterministic registration of the M6 provider shells."""
from datetime import datetime

from evidencegate.domain.enums import ResultType, ScientificStatus
from evidencegate.domain.governance import LaneGovernance
from evidencegate.registry.plugin import AnalyticPlugin
from evidencegate.routing.router import LaneTarget
from .c2 import C2ShellPlugin
from .ddos import DdosShellPlugin
from .dns_dga import DgaShellPlugin, DnsTunnellingShellPlugin
from .encrypted import EncAHandshakePlugin
from .exfil import ExfilM1TransferPlugin
from .recon import ReconShellPlugin


def build_mvp_provider_registry(effective_at: datetime) -> tuple[dict[LaneTarget, AnalyticPlugin], dict[LaneTarget, LaneGovernance]]:
    """Return registration inputs; execution remains the RuntimeSupervisor's job."""
    plugins = {
        LaneTarget("ddos"): DdosShellPlugin(),
        LaneTarget("c2"): C2ShellPlugin(),
        LaneTarget("dga"): DgaShellPlugin(),
        LaneTarget("dns_tunnelling"): DnsTunnellingShellPlugin(),
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
    return plugins, governances
