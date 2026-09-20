"""Explicit, deterministic registration of the M6 provider shells."""
from datetime import datetime

from evidencegate.domain.enums import ResultType, ScientificStatus
from evidencegate.domain.governance import LaneGovernance
from evidencegate.registry.plugin import AnalyticPlugin
from evidencegate.routing.router import LaneTarget
from .c2 import C2ShellPlugin
from .ddos import DdosShellPlugin
from .dns_dga import DgaShellPlugin, DnsTunnellingShellPlugin
from .encrypted import EncryptedSessionShellPlugin
from .exfil import UnusualTransferShellPlugin
from .recon import ReconShellPlugin


def build_mvp_provider_registry(effective_at: datetime) -> tuple[dict[LaneTarget, AnalyticPlugin], dict[LaneTarget, LaneGovernance]]:
    """Return registration inputs; execution remains the RuntimeSupervisor's job."""
    plugins = {
        LaneTarget("ddos"): DdosShellPlugin(),
        LaneTarget("c2"): C2ShellPlugin(),
        LaneTarget("dga"): DgaShellPlugin(),
        LaneTarget("dns_tunnelling"): DnsTunnellingShellPlugin(),
        LaneTarget("encrypted_session"): EncryptedSessionShellPlugin(),
        LaneTarget("recon"): ReconShellPlugin(),
        LaneTarget("unusual_transfer"): UnusualTransferShellPlugin(),
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
    return plugins, governances
