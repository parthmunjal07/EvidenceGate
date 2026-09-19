"""Bounded, namespaced runtime state with explicit tagged transitions."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from evidencegate.registry.plugin import StateKey


DEFAULT_MAX_ENTRIES = 10_000


class StateOperation(str, Enum):
    NO_CHANGE = "NO_CHANGE"
    UPSERT = "UPSERT"
    DELETE = "DELETE"
    RESET = "RESET"
    REENTER_WARMUP = "REENTER_WARMUP"


class StateStoreError(Exception):
    """Base class for explicit state-store failures."""


class StateVersionConflict(StateStoreError):
    def __init__(
        self,
        namespace: str,
        key: StateKey,
        expected_version: int | None,
        actual_version: int | None,
    ) -> None:
        self.namespace = namespace
        self.key = key
        self.expected_version = expected_version
        self.actual_version = actual_version
        super().__init__(
            f"state version conflict for ({namespace!r}, {key!r}): "
            f"expected {expected_version!r}, found {actual_version!r}"
        )


class StateCapacityExceeded(StateStoreError):
    def __init__(self, max_entries: int) -> None:
        self.max_entries = max_entries
        super().__init__(f"state capacity of {max_entries} entries exceeded")


@dataclass(frozen=True, slots=True)
class StateEntry:
    namespace: str
    key: StateKey
    payload: Any
    version: int
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class StateTransitionResult:
    namespace: str
    key: StateKey
    operation: StateOperation
    version_before: int | None
    version_after: int | None
    expires_at: datetime | None
    exists: bool


class StateStore:
    """
    Runtime-owned bounded state.

    Time is always supplied by the caller, so expiry is deterministic and is
    kept separate from any plugin-defined scientific history window.
    """

    def __init__(self, max_entries: int = DEFAULT_MAX_ENTRIES) -> None:
        if isinstance(max_entries, bool) or not isinstance(max_entries, int):
            raise TypeError("max_entries must be an integer")
        if max_entries <= 0:
            raise ValueError("max_entries must be greater than zero")
        self._max_entries = max_entries
        self._state: dict[tuple[str, StateKey], StateEntry] = {}

    @property
    def max_entries(self) -> int:
        return self._max_entries

    def __len__(self) -> int:
        return len(self._state)

    def read(
        self,
        namespace: str,
        key: StateKey | str,
        at_time: datetime,
    ) -> StateEntry | None:
        """Return an immutable snapshot, or ``None`` when state is missing."""
        identity = self._identity(namespace, key)
        self._validate_time(at_time, "at_time")
        entry = self._state.get(identity)
        if entry is None:
            return None
        if entry.expires_at <= at_time:
            del self._state[identity]
            return None
        return self._snapshot(entry)

    def expire(self, at_time: datetime) -> tuple[StateEntry, ...]:
        """Remove and return all entries expired at or before ``at_time``."""
        self._validate_time(at_time, "at_time")
        expired_identities = sorted(
            (
                identity
                for identity, entry in self._state.items()
                if entry.expires_at <= at_time
            ),
            key=lambda identity: (identity[0], str(identity[1])),
        )
        return tuple(
            self._snapshot(self._state.pop(identity))
            for identity in expired_identities
        )

    def transition(
        self,
        namespace: str,
        key: StateKey | str,
        expected_version: int | None,
        operation: StateOperation,
        payload: Any,
        event_time: datetime,
        ttl: timedelta | None,
    ) -> StateTransitionResult:
        """Validate and atomically apply one generic state transition."""
        identity = self._identity(namespace, key)
        self._validate_time(event_time, "event_time")
        try:
            operation = StateOperation(operation)
        except ValueError as exc:
            raise ValueError(f"unsupported state operation: {operation!r}") from exc

        self.expire(event_time)
        before = self._state.get(identity)
        version_before = before.version if before is not None else None
        if expected_version != version_before:
            raise StateVersionConflict(
                namespace, identity[1], expected_version, version_before
            )

        if operation is StateOperation.UPSERT:
            if not isinstance(ttl, timedelta) or ttl <= timedelta(0):
                raise ValueError("UPSERT requires a positive timedelta ttl")
            if before is None and len(self._state) >= self._max_entries:
                raise StateCapacityExceeded(self._max_entries)
            version_after = 1 if before is None else before.version + 1
            entry = StateEntry(
                namespace=namespace,
                key=identity[1],
                payload=deepcopy(payload),
                version=version_after,
                expires_at=event_time + ttl,
            )
            self._state[identity] = entry
            return self._result(operation, version_before, entry)

        if payload is not None or ttl is not None:
            raise ValueError(f"{operation.value} does not accept payload or ttl")

        if operation is StateOperation.NO_CHANGE:
            if before is None:
                return self._missing_result(namespace, identity[1], operation)
            return self._result(operation, version_before, before)

        if operation is StateOperation.REENTER_WARMUP:
            if before is None:
                return self._missing_result(namespace, identity[1], operation)
            return self._result(operation, version_before, before)

        if before is not None:
            del self._state[identity]
        return self._missing_result(
            namespace,
            identity[1],
            operation,
            version_before,
        )

    @staticmethod
    def _identity(namespace: str, key: StateKey | str) -> tuple[str, StateKey]:
        if not isinstance(namespace, str) or not namespace:
            raise ValueError("namespace must be a non-empty string")
        if not isinstance(key, str) or not key:
            raise ValueError("key must be a non-empty string")
        return namespace, StateKey(key)

    @staticmethod
    def _validate_time(value: datetime, name: str) -> None:
        if not isinstance(value, datetime):
            raise TypeError(f"{name} must be a datetime")
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{name} must be timezone-aware")

    @staticmethod
    def _snapshot(entry: StateEntry) -> StateEntry:
        return StateEntry(
            namespace=entry.namespace,
            key=entry.key,
            payload=deepcopy(entry.payload),
            version=entry.version,
            expires_at=entry.expires_at,
        )

    @staticmethod
    def _result(
        operation: StateOperation,
        version_before: int | None,
        entry: StateEntry,
    ) -> StateTransitionResult:
        return StateTransitionResult(
            namespace=entry.namespace,
            key=entry.key,
            operation=operation,
            version_before=version_before,
            version_after=entry.version,
            expires_at=entry.expires_at,
            exists=True,
        )

    @staticmethod
    def _missing_result(
        namespace: str,
        key: StateKey,
        operation: StateOperation,
        version_before: int | None = None,
    ) -> StateTransitionResult:
        return StateTransitionResult(
            namespace=namespace,
            key=key,
            operation=operation,
            version_before=version_before,
            version_after=None,
            expires_at=None,
            exists=False,
        )
