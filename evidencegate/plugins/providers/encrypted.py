from evidencegate.domain.enums import AnalyticFamily, ObservationType, OfficialPsCategory, VisibilityCapability
from .common import ProviderShellPlugin

class EncryptedSessionShellPlugin(ProviderShellPlugin):
    plugin_id = "provider.encrypted_session.shell"
    category = OfficialPsCategory.ENCRYPTED_SESSIONS
    family = AnalyticFamily.ENCRYPTED_SESSION
    taxonomy = ("Network", "Encrypted Session", "Provider Shell")
    accepted_types = (ObservationType.TLS, ObservationType.QUIC)
    capabilities_by_type = {ObservationType.TLS: frozenset({VisibilityCapability.TLS_HANDSHAKE_METADATA, VisibilityCapability.TLS_RECORD_METADATA}), ObservationType.QUIC: frozenset({VisibilityCapability.QUIC_OUTER_METADATA})}
