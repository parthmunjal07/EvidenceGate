from evidencegate.domain.enums import AnalyticFamily, ObservationType, OfficialPsCategory, VisibilityCapability
from .common import ProviderShellPlugin

class DdosShellPlugin(ProviderShellPlugin):
    plugin_id = "provider.ddos.shell"
    category = OfficialPsCategory.DDOS
    family = AnalyticFamily.DDOS
    taxonomy = ("Network", "DDoS", "Provider Shell")
    accepted_types = (ObservationType.PACKET, ObservationType.FLOW)
    capabilities_by_type = {ObservationType.PACKET: frozenset({VisibilityCapability.PACKET_FACTS}), ObservationType.FLOW: frozenset({VisibilityCapability.FLOW_FACTS})}
