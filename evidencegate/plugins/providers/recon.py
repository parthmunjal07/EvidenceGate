from evidencegate.domain.enums import AnalyticFamily, ObservationType, OfficialPsCategory, VisibilityCapability
from .common import ProviderShellPlugin

class ReconShellPlugin(ProviderShellPlugin):
    plugin_id = "provider.recon.shell"
    category = OfficialPsCategory.RECONNAISSANCE_AND_PORT_SCANNING
    family = AnalyticFamily.RECON
    taxonomy = ("Network", "Reconnaissance", "Provider Shell")
    accepted_types = (ObservationType.PACKET, ObservationType.FLOW)
    capabilities_by_type = {ObservationType.PACKET: frozenset({VisibilityCapability.PACKET_FACTS}), ObservationType.FLOW: frozenset({VisibilityCapability.FLOW_FACTS})}
