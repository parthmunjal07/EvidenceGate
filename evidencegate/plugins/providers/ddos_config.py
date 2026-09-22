"""Immutable controlled-reference configuration for DDOS-A SYN state."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import hashlib
import json


@dataclass(frozen=True, slots=True)
class DdosASynConfig:
    """Executable mechanism parameters; never an activation or attack policy."""

    config_id: str
    syn_state_ttl: timedelta
    target_role_label: str
    service_role_label: str
    tcp_protocol_number: int
    config_status: str
    science_admitted: bool

    def __post_init__(self) -> None:
        if not isinstance(self.config_id, str) or not self.config_id.strip():
            raise ValueError("config_id must be a non-empty string")
        if not isinstance(self.syn_state_ttl, timedelta):
            raise TypeError("syn_state_ttl must be a timedelta")
        if self.syn_state_ttl <= timedelta(0):
            raise ValueError("syn_state_ttl must be positive")
        labels = (self.target_role_label, self.service_role_label)
        if any(not isinstance(label, str) or not label.strip() for label in labels):
            raise ValueError("role labels must be non-empty strings")
        if self.target_role_label == self.service_role_label:
            raise ValueError("target and service role labels must be distinct")
        if isinstance(self.tcp_protocol_number, bool) or not isinstance(
            self.tcp_protocol_number, int
        ):
            raise TypeError("tcp_protocol_number must be a non-bool integer")
        if not 0 <= self.tcp_protocol_number <= 255:
            raise ValueError("tcp_protocol_number must be in the IP protocol range")
        if not isinstance(self.config_status, str) or not self.config_status.strip():
            raise ValueError("config_status must be a non-empty string")
        if not isinstance(self.science_admitted, bool):
            raise TypeError("science_admitted must be bool")

    @property
    def canonical_hash(self) -> str:
        """Hash only executable mechanism parameters using canonical JSON."""
        value = {
            "config_status": self.config_status,
            "science_admitted": self.science_admitted,
            "service_role_label": self.service_role_label,
            "syn_state_ttl_microseconds": int(
                self.syn_state_ttl.total_seconds() * 1_000_000
            ),
            "target_role_label": self.target_role_label,
            "tcp_protocol_number": self.tcp_protocol_number,
        }
        encoded = json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")
        return "sha256:" + hashlib.sha256(encoded).hexdigest()

    @classmethod
    def reference_poc_v1(cls) -> "DdosASynConfig":
        """CONTROLLED POC configuration; the TTL is not an attack threshold."""
        return cls(
            config_id="ddos-a-syn-reference-poc-v1",
            syn_state_ttl=timedelta(seconds=5),
            target_role_label="target_id",
            service_role_label="service_id",
            tcp_protocol_number=6,
            config_status="POC_OR_EXPERIMENT_ONLY",
            science_admitted=False,
        )
