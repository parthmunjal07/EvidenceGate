from evidencegate.domain.enums import AnalyticFamily, ObservationType, OfficialPsCategory, VisibilityCapability
from .common import ProviderShellPlugin

class UnusualTransferShellPlugin(ProviderShellPlugin):
    plugin_id = "provider.unusual_transfer.shell"
    category = OfficialPsCategory.DATA_EXFILTRATION
    family = AnalyticFamily.UNUSUAL_TRANSFER
    taxonomy = ("Network", "Unusual Transfer", "Provider Shell")
    accepted_types = (ObservationType.PACKET, ObservationType.FLOW)
    capabilities_by_type = {ObservationType.PACKET: frozenset({VisibilityCapability.PACKET_FACTS}), ObservationType.FLOW: frozenset({VisibilityCapability.FLOW_FACTS})}
