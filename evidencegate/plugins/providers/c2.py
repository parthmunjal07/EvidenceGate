from evidencegate.domain.enums import AnalyticFamily, ObservationType, OfficialPsCategory, VisibilityCapability
from .common import ProviderShellPlugin

class C2ShellPlugin(ProviderShellPlugin):
    plugin_id = "provider.c2.shell"
    category = OfficialPsCategory.C2_BEACONING
    family = AnalyticFamily.C2
    taxonomy = ("Network", "C2", "Provider Shell")
    accepted_types = (ObservationType.PACKET, ObservationType.FLOW)
    capabilities_by_type = {ObservationType.PACKET: frozenset({VisibilityCapability.PACKET_FACTS}), ObservationType.FLOW: frozenset({VisibilityCapability.FLOW_FACTS})}
