"""Explicit, immutable configuration for Category-5 Recon measurements."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import hashlib
import json


@dataclass(frozen=True, slots=True)
class ReconConfig:
    """Executable mechanics parameters; no production defaults are implied."""

    config_id: str
    horizons: tuple[timedelta, ...]
    max_events_per_key: int
    state_ttl: timedelta
    initiator_role_label: str
    target_role_label: str

    def __post_init__(self) -> None:
        if not isinstance(self.config_id, str) or not self.config_id.strip():
            raise ValueError("config_id must be a non-empty string")
        if not isinstance(self.horizons, tuple) or not self.horizons:
            raise TypeError("horizons must be a non-empty tuple")
        if any(not isinstance(item, timedelta) for item in self.horizons):
            raise TypeError("horizons must contain timedelta values")
        if any(item <= timedelta(0) for item in self.horizons):
            raise ValueError("horizons must be positive")
        if tuple(sorted(set(self.horizons))) != self.horizons:
            raise ValueError("horizons must be unique and strictly increasing")
        if isinstance(self.max_events_per_key, bool) or not isinstance(
            self.max_events_per_key, int
        ):
            raise TypeError("max_events_per_key must be a non-bool integer")
        if self.max_events_per_key <= 0:
            raise ValueError("max_events_per_key must be greater than zero")
        if not isinstance(self.state_ttl, timedelta):
            raise TypeError("state_ttl must be a timedelta")
        if self.state_ttl < self.horizons[-1]:
            raise ValueError("state_ttl cannot be shorter than the largest horizon")
        labels = (self.initiator_role_label, self.target_role_label)
        if any(not isinstance(item, str) or not item.strip() for item in labels):
            raise ValueError("role labels must be non-empty strings")
        if len(set(labels)) != len(labels):
            raise ValueError("initiator and target role labels must be distinct")

    @property
    def canonical_hash(self) -> str:
        value = {
            "horizon_microseconds": [
                int(item.total_seconds() * 1_000_000) for item in self.horizons
            ],
            "initiator_role_label": self.initiator_role_label,
            "max_events_per_key": self.max_events_per_key,
            "state_ttl_microseconds": int(self.state_ttl.total_seconds() * 1_000_000),
            "target_role_label": self.target_role_label,
        }
        encoded = json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")
        return "sha256:" + hashlib.sha256(encoded).hexdigest()

    @classmethod
    def controlled_fixture_v1(cls) -> "ReconConfig":
        """TEST/CONTROLLED-REPLAY CONFIG; it is not a production default."""
        return cls(
            config_id="recon-controlled-fixture-v1",
            horizons=(
                timedelta(seconds=10),
                timedelta(seconds=60),
                timedelta(seconds=3600),
            ),
            max_events_per_key=256,
            state_ttl=timedelta(seconds=3600),
            initiator_role_label="initiator_id",
            target_role_label="target_id",
        )

    @classmethod
    def controlled_mvp_v1(cls) -> "ReconConfig":
        """Human-gated controlled-MVP measurement configuration.

        The horizons are observation windows and the retained-event limit is an
        engineering bound.  Neither value is a malicious-scan policy.
        """
        return cls(
            config_id="recon-controlled-mvp-v1",
            horizons=(timedelta(seconds=60), timedelta(seconds=3600)),
            max_events_per_key=16,
            state_ttl=timedelta(seconds=3600),
            initiator_role_label="initiator_id",
            target_role_label="target_id",
        )
