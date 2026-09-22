"""Typed replay bundle validation and incremental source tests."""
import hashlib
import json
from pathlib import Path

import pytest

from evidencegate.domain.enums import (
    CapabilityState, IdentityBasis, ObservationType, SourceKind,
    VisibilityCapability, WireDirection,
)
from evidencegate.ingest.replay import NdjsonReplaySource, ReplayCanonicalizer, validate_bundle
from evidencegate.ingest.replay_schema import ReplayValidationError


FIXTURES = Path("tests/fixtures/replay")


@pytest.mark.parametrize("name,count", [
    ("dns_forward", 1), ("tls_handshake", 1), ("flow_transfer", 1), ("c2_r1", 3),
    ("mixed_direction", 3),
])
async def test_manifest_and_all_fixture_records_validate(name, count):
    assert await validate_bundle(FIXTURES / name) == count


async def test_source_is_derived_read_only_and_roles_round_trip():
    bundle = FIXTURES / "c2_r1"
    before = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in bundle.iterdir()
    }
    source = NdjsonReplaySource(bundle)
    manifest = await source.open()
    records = [record async for record in source.records()]
    await source.close()
    after = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in bundle.iterdir()
    }
    assert manifest.source_kind is SourceKind.DERIVED
    assert before == after
    assert records[0].role_assignments[0].basis is IdentityBasis.SOURCE_DECLARED_ROLE
    assert records[0].observation_type is ObservationType.FLOW


async def test_records_are_incremental_not_preloaded(tmp_path):
    source_bundle = FIXTURES / "dns_forward"
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "manifest.json").write_bytes((source_bundle / "manifest.json").read_bytes())
    first = (source_bundle / "records.ndjson").read_text(encoding="utf-8")
    (bundle / "records.ndjson").write_text(first + "{malformed\n", encoding="utf-8")
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    manifest.pop("record_count")
    (bundle / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    source = NdjsonReplaySource(bundle)
    await source.open()
    iterator = source.records().__aiter__()
    assert (await iterator.__anext__()).position == 1
    with pytest.raises(ReplayValidationError, match="line 2.*JSONDecodeError"):
        await iterator.__anext__()
    await source.close()


def _mutated_bundle(tmp_path, fixture="dns_forward"):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    manifest = json.loads((FIXTURES / fixture / "manifest.json").read_text(encoding="utf-8"))
    record_lines = (FIXTURES / fixture / "records.ndjson").read_text(encoding="utf-8").splitlines()
    return bundle, manifest, [json.loads(line) for line in record_lines]


@pytest.mark.parametrize("field,value,match", [
    ("timestamp", "2026-01-01T00:00:00", "timezone-aware"),
    ("observation_type", "BOGUS", "unknown observation_type"),
    ("finality", "BOGUS", "unknown finality"),
])
async def test_invalid_timestamp_or_enum_is_visible(tmp_path, field, value, match):
    bundle, manifest, records = _mutated_bundle(tmp_path)
    records[0][field] = value
    (bundle / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (bundle / "records.ndjson").write_text(json.dumps(records[0]) + "\n", encoding="utf-8")
    with pytest.raises(ReplayValidationError, match=match):
        await validate_bundle(bundle)


async def test_unknown_declared_field_and_result_injection_rejected(tmp_path):
    bundle, manifest, records = _mutated_bundle(tmp_path)
    records[0]["declared_observed_fields"].append("invented")
    records[0]["Result"] = {"result_type": "THREAT_ALERT"}
    (bundle / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (bundle / "records.ndjson").write_text(json.dumps(records[0]) + "\n", encoding="utf-8")
    with pytest.raises(ReplayValidationError, match="unknown=.*Result"):
        await validate_bundle(bundle)


async def test_decreasing_event_time_is_rejected_without_sorting(tmp_path):
    bundle, manifest, records = _mutated_bundle(tmp_path, "c2_r1")
    records[1]["timestamp"] = "2025-12-31T23:59:59Z"
    manifest["record_count"] = len(records)
    (bundle / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (bundle / "records.ndjson").write_text(
        "\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8"
    )
    with pytest.raises(ReplayValidationError, match="EventTimeOrderError"):
        await validate_bundle(bundle)


async def test_existing_dns_canonicalization_is_reused():
    source = NdjsonReplaySource(FIXTURES / "dns_forward")
    manifest = await source.open()
    iterator = source.records().__aiter__()
    record = await iterator.__anext__()
    await iterator.aclose()
    result = ReplayCanonicalizer().canonicalize(record, manifest, "quality:1", record.timestamp)
    await source.close()
    payload = result.observations[0].typed_payload
    assert payload.qname_canonical == "demo.example"
    assert payload.representation_version == "DNS_NAME_REPRESENTATION_V1"


async def test_mixed_record_directions_preserve_both_source_visibility():
    source = NdjsonReplaySource(FIXTURES / "mixed_direction")
    manifest = await source.open()
    observations = []
    async for record in source.records():
        result = ReplayCanonicalizer().canonicalize(
            record, manifest, f"quality:{record.position}", record.timestamp,
        )
        observations.extend(result.observations)
    await source.close()
    assert [item.wire_direction for item in observations] == [
        WireDirection.FORWARD, WireDirection.REVERSE, WireDirection.FORWARD,
    ]
    for observation in observations:
        assert observation.visibility.state(
            VisibilityCapability.FORWARD_FACTS,
        ) is CapabilityState.AVAILABLE
        assert observation.visibility.state(
            VisibilityCapability.REVERSE_FACTS,
        ) is CapabilityState.AVAILABLE


@pytest.mark.parametrize("value,match", [
    ("SIDEWAYS", "unknown wire_direction"),
    (1, "wire_direction must be a string"),
])
async def test_record_direction_rejects_unknown_strings_and_wrong_types(tmp_path, value, match):
    bundle, manifest, records = _mutated_bundle(tmp_path)
    records[0]["wire_direction"] = value
    (bundle / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (bundle / "records.ndjson").write_text(json.dumps(records[0]) + "\n", encoding="utf-8")
    with pytest.raises(ReplayValidationError, match=match):
        await validate_bundle(bundle)


async def test_concrete_manifest_record_direction_conflict_fails_closed(tmp_path):
    bundle, manifest, records = _mutated_bundle(tmp_path)
    records[0]["wire_direction"] = "REVERSE"
    (bundle / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (bundle / "records.ndjson").write_text(json.dumps(records[0]) + "\n", encoding="utf-8")
    with pytest.raises(ReplayValidationError, match="DirectionContractError.*contradicts"):
        await validate_bundle(bundle)


@pytest.mark.parametrize("fixture,expected", [
    ("dns_forward", WireDirection.FORWARD),
    ("mixed_direction", WireDirection.FORWARD),
])
async def test_omitted_direction_uses_manifest_and_record_direction_is_explicit(fixture, expected):
    source = NdjsonReplaySource(FIXTURES / fixture)
    manifest = await source.open()
    iterator = source.records().__aiter__()
    record = await iterator.__anext__()
    await iterator.aclose()
    observation = ReplayCanonicalizer().canonicalize(
        record, manifest, "quality", record.timestamp,
    ).observations[0]
    await source.close()
    assert observation.wire_direction is expected


async def test_unknown_manifest_and_omitted_record_stay_unknown(tmp_path):
    bundle, manifest, records = _mutated_bundle(tmp_path)
    manifest["wire_direction"] = "UNKNOWN"
    manifest["direction_basis"] = "UNKNOWN"
    (bundle / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (bundle / "records.ndjson").write_text(json.dumps(records[0]) + "\n", encoding="utf-8")
    source = NdjsonReplaySource(bundle)
    parsed_manifest = await source.open()
    iterator = source.records().__aiter__()
    record = await iterator.__anext__()
    await iterator.aclose()
    observation = ReplayCanonicalizer().canonicalize(
        record, parsed_manifest, "quality", record.timestamp,
    ).observations[0]
    await source.close()
    assert observation.wire_direction is WireDirection.UNKNOWN


async def test_direction_is_not_inferred_from_packet_addresses_ports_or_flags(tmp_path):
    bundle, manifest, records = _mutated_bundle(tmp_path, "mixed_direction")
    records = records[:2]
    records[1]["payload"] = dict(records[0]["payload"])
    records[1]["wire_direction"] = "REVERSE"
    manifest["record_count"] = 2
    (bundle / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (bundle / "records.ndjson").write_text(
        "\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8",
    )
    source = NdjsonReplaySource(bundle)
    parsed_manifest = await source.open()
    observations = []
    async for record in source.records():
        observations.extend(ReplayCanonicalizer().canonicalize(
            record, parsed_manifest, "quality", record.timestamp,
        ).observations)
    await source.close()
    assert observations[0].typed_payload == observations[1].typed_payload
    assert [item.wire_direction for item in observations] == [
        WireDirection.FORWARD, WireDirection.REVERSE,
    ]


@pytest.mark.parametrize("fixture", ["dns_forward", "tls_handshake", "flow_transfer"])
async def test_record_direction_is_generic_across_replay_observation_types(tmp_path, fixture):
    bundle, manifest, records = _mutated_bundle(tmp_path, fixture)
    manifest["wire_direction"] = "UNKNOWN"
    manifest["visibility"] = {
        "available": ["FORWARD_FACTS", "REVERSE_FACTS"],
        "unavailable": [], "degraded": [],
    }
    records[0]["wire_direction"] = "REVERSE"
    (bundle / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (bundle / "records.ndjson").write_text(json.dumps(records[0]) + "\n", encoding="utf-8")
    source = NdjsonReplaySource(bundle)
    parsed_manifest = await source.open()
    iterator = source.records().__aiter__()
    record = await iterator.__anext__()
    await iterator.aclose()
    observation = ReplayCanonicalizer().canonicalize(
        record, parsed_manifest, "quality", record.timestamp,
    ).observations[0]
    await source.close()
    assert observation.wire_direction is WireDirection.REVERSE
