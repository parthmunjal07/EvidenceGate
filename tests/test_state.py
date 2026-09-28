"""Focused contract tests for the bounded generic state runtime."""

from datetime import datetime, timedelta, timezone

import pytest

from evidencegate.runtime.state import (
    StateCapacityExceeded,
    StateOperation,
    StateStore,
    StateVersionConflict,
)


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
TTL = timedelta(minutes=5)


def upsert(
    store: StateStore,
    namespace: str,
    key: str,
    payload: object,
    expected_version: int | None = None,
    event_time: datetime = NOW,
):
    return store.transition(
        namespace,
        key,
        expected_version,
        StateOperation.UPSERT,
        payload,
        event_time,
        TTL,
    )


def test_namespace_isolation() -> None:
    store = StateStore(max_entries=2)
    upsert(store, "lane-a", "same-key", {"value": "a"})
    upsert(store, "lane-b", "same-key", {"value": "b"})

    assert store.read("lane-a", "same-key", NOW).payload == {"value": "a"}
    assert store.read("lane-b", "same-key", NOW).payload == {"value": "b"}


def test_missing_read_is_missing() -> None:
    store = StateStore(max_entries=1)

    assert store.read("lane", "absent", NOW) is None


def test_first_upsert_creates_versioned_entry() -> None:
    store = StateStore(max_entries=1)

    result = upsert(store, "lane", "key", {"count": 1})

    assert result.namespace == "lane"
    assert result.key == "key"
    assert result.operation is StateOperation.UPSERT
    assert result.version_before is None
    assert result.version_after == 1
    assert result.expires_at == NOW + TTL
    assert result.exists is True


def test_later_upsert_increments_version() -> None:
    store = StateStore(max_entries=1)
    upsert(store, "lane", "key", {"count": 1})

    result = upsert(store, "lane", "key", {"count": 2}, expected_version=1)

    assert result.version_before == 1
    assert result.version_after == 2
    assert store.read("lane", "key", NOW).payload == {"count": 2}


def test_stale_expected_version_is_rejected_without_overwrite() -> None:
    store = StateStore(max_entries=1)
    upsert(store, "lane", "key", "original")

    with pytest.raises(StateVersionConflict) as error:
        upsert(store, "lane", "key", "replacement", expected_version=None)

    assert error.value.expected_version is None
    assert error.value.actual_version == 1
    assert store.read("lane", "key", NOW).payload == "original"


def test_delete_removes_entry() -> None:
    store = StateStore(max_entries=1)
    upsert(store, "lane", "key", "evidence")

    result = store.transition("lane", "key", 1, StateOperation.DELETE, None, NOW, None)

    assert result.version_before == 1
    assert result.version_after is None
    assert result.exists is False
    assert result.operation is StateOperation.DELETE
    assert store.read("lane", "key", NOW) is None


def test_reset_removes_entry_and_reports_reset() -> None:
    store = StateStore(max_entries=1)
    upsert(store, "lane", "key", "evidence")

    result = store.transition("lane", "key", 1, StateOperation.RESET, None, NOW, None)

    assert result.version_before == 1
    assert result.exists is False
    assert result.operation is StateOperation.RESET
    assert store.read("lane", "key", NOW) is None


def test_ttl_expiry_removes_state_at_boundary() -> None:
    store = StateStore(max_entries=1)
    upsert(store, "lane", "key", "evidence")

    assert store.read("lane", "key", NOW + TTL - timedelta(microseconds=1))
    assert store.read("lane", "key", NOW + TTL) is None
    assert len(store) == 0


def test_finite_capacity_rejects_new_identity_without_eviction() -> None:
    store = StateStore(max_entries=1)
    upsert(store, "lane", "first", "preserved")

    with pytest.raises(StateCapacityExceeded) as error:
        upsert(store, "lane", "second", "rejected")

    assert error.value.max_entries == 1
    assert store.read("lane", "first", NOW).payload == "preserved"
    assert store.read("lane", "second", NOW) is None


def test_expiry_is_deterministic_and_reclaims_capacity() -> None:
    store = StateStore(max_entries=1)
    upsert(store, "lane", "first", "old")
    expiry_time = NOW + TTL

    result = upsert(store, "lane", "second", "new", event_time=expiry_time)

    assert result.version_after == 1
    assert store.read("lane", "first", expiry_time) is None
    assert store.read("lane", "second", expiry_time).payload == "new"


def test_no_change_preserves_payload_version_and_expiry() -> None:
    store = StateStore(max_entries=1)
    original = {"evidence": [1]}
    created = upsert(store, "lane", "key", original)

    result = store.transition("lane", "key", 1, StateOperation.NO_CHANGE, None, NOW, None)

    assert result.version_before == result.version_after == 1
    assert result.expires_at == created.expires_at
    assert store.read("lane", "key", NOW).payload == original


def test_missing_operations_do_not_fabricate_zero_or_benign_state() -> None:
    store = StateStore(max_entries=1)

    unchanged = store.transition("lane", "missing", None, StateOperation.NO_CHANGE, None, NOW, None)
    deleted = store.transition("lane", "missing", None, StateOperation.DELETE, None, NOW, None)
    reset = store.transition("lane", "missing", None, StateOperation.RESET, None, NOW, None)

    assert unchanged.exists is deleted.exists is reset.exists is False
    assert unchanged.version_after is deleted.version_after is reset.version_after is None
    assert store.read("lane", "missing", NOW) is None


def test_reenter_warmup_is_visible_without_mutating_scientific_payload() -> None:
    store = StateStore(max_entries=1)
    upsert(store, "lane", "key", {"evidence": "unchanged"})

    result = store.transition("lane", "key", 1, StateOperation.REENTER_WARMUP, None, NOW, None)

    assert result.operation is StateOperation.REENTER_WARMUP
    assert result.version_before == result.version_after == 1
    assert store.read("lane", "key", NOW).payload == {"evidence": "unchanged"}


def test_read_snapshot_cannot_mutate_stored_payload_invisibly() -> None:
    store = StateStore(max_entries=1)
    upsert(store, "lane", "key", {"items": []})

    snapshot = store.read("lane", "key", NOW)
    snapshot.payload["items"].append("external mutation")

    assert store.read("lane", "key", NOW).payload == {"items": []}
