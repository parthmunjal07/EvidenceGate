from evidencegate.domain.enums import AnalyticFamily, ObservationType, OfficialPsCategory, VisibilityCapability
from .common import ProviderShellPlugin

class DgaShellPlugin(ProviderShellPlugin):
    plugin_id = "provider.dga.shell"
    category = OfficialPsCategory.DGA_AND_DNS_TUNNELLING
    family = AnalyticFamily.DGA
    taxonomy = ("Network", "DGA", "Provider Shell")
    accepted_types = (ObservationType.DNS,)
    capabilities_by_type = {ObservationType.DNS: frozenset({VisibilityCapability.CLEAR_DNS_FIELDS})}

class DnsTunnellingShellPlugin(ProviderShellPlugin):
    plugin_id = "provider.dns_tunnelling.shell"
    category = OfficialPsCategory.DGA_AND_DNS_TUNNELLING
    family = AnalyticFamily.DNS_TUNNELLING
    taxonomy = ("Network", "DNS Tunnelling", "Provider Shell")
    accepted_types = (ObservationType.DNS,)
    capabilities_by_type = {ObservationType.DNS: frozenset({VisibilityCapability.CLEAR_DNS_FIELDS})}
