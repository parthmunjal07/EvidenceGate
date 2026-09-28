"""Explicit, immutable configuration for the C2-R1 measurement path."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import hashlib
import json

from evidencegate.domain.enums import TimestampSemantics


REFERENCE_WATERMARK_LATENESS = timedelta(seconds=5)


@dataclass(frozen=True, slots=True)
class C2R1Config:
    """Executable C2-R1 parameters; no production defaults are implied."""

    config_id: str
    minimum_history_events: int
    max_retained_events_per_pair: int
    state_ttl: timedelta
    event_basis: TimestampSemantics
    client_role_label: str
    peer_role_label: str
    service_role_label: str

    def __post_init__(self) -> None:
        if not isinstance(self.config_id, str) or not self.config_id.strip():
            raise ValueError("config_id must be a non-empty string")
        for name in ("minimum_history_events", "max_retained_events_per_pair"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be a non-bool integer")
            if value <= 0:
                raise ValueError(f"{name} must be greater than zero")
        if self.max_retained_events_per_pair < self.minimum_history_events:
            raise ValueError(
                "max_retained_events_per_pair cannot be less than minimum_history_events"
            )
        if not isinstance(self.state_ttl, timedelta):
            raise TypeError("state_ttl must be a timedelta")
        if self.state_ttl <= timedelta(0):
            raise ValueError("state_ttl must be positive")
        if self.event_basis is not TimestampSemantics.FLOW_START:
            raise ValueError("C2-R1 currently supports only the FLOW_START event basis")
        labels = (
            self.client_role_label,
            self.peer_role_label,
            self.service_role_label,
        )
        if any(not isinstance(label, str) or not label.strip() for label in labels):
            raise ValueError("role labels must be non-empty strings")
        if len(set(labels)) != len(labels):
            raise ValueError("client, peer, and service role labels must be distinct")

    @property
    def canonical_hash(self) -> str:
        """Hash only executable R1 configuration using canonical JSON."""
        value = {
            "client_role_label": self.client_role_label,
            "event_basis": self.event_basis.value,
            "max_retained_events_per_pair": self.max_retained_events_per_pair,
            "minimum_history_events": self.minimum_history_events,
            "peer_role_label": self.peer_role_label,
            "service_role_label": self.service_role_label,
            "state_ttl_microseconds": int(self.state_ttl.total_seconds() * 1_000_000),
        }
        encoded = json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")
        return "sha256:" + hashlib.sha256(encoded).hexdigest()

    @classmethod
    def reference_engine_v1(cls) -> "C2R1Config":
        """REFERENCE / CONTROLLED MVP CONFIG, never a production default.

        The role labels map the active reference fixture fields into the shared
        trusted RoleAssignment contract.  Gate-E ``k=6`` remains a historical
        warm-up experiment; this helper reflects the later reference execution
        config's R1 minimum of 3.  Neither value is a production threshold.
        """
        return cls(
            config_id="c2-reference-config-v1",
            minimum_history_events=3,
            max_retained_events_per_pair=32,
            state_ttl=timedelta(seconds=3600),
            event_basis=TimestampSemantics.FLOW_START,
            client_role_label="client_id",
            peer_role_label="peer_id",
            service_role_label="peer_port",
        )
