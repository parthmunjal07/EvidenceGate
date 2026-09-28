"""M7-01 ENC-A admitted visible TLS handshake context."""

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from evidencegate.domain.enums import (
    AvailabilityBasis,
    DirectionBasis,
    Finality,
    IntegrationStatus,
    ObservationType,
    OfficialPsCategory,
    QualityState,
    ResultType,
    SourceKind,
    VisibilityCapability,
    WireDirection,
)
from evidencegate.domain.events import NetworkObservationEnvelope, VisibilityProfile
from evidencegate.domain.payloads import QUICObservation, TLSObservation
from evidencegate.domain.quality import EvidenceQuality
from evidencegate.persistence.sqlite import SqliteWriter
from evidencegate.plugins.providers.registry import (
    build_mvp_runtime_registration,
)
from evidencegate.routing.router import RelevanceRouter
from evidencegate.runtime.supervisor import RuntimeSupervisor

NOW = datetime(2026, 3, 1, tzinfo=timezone.utc)
LANE = "encrypted_session.enc_a"


def tls(
    *,
    metadata={"sni": "example.test", "ja4": "t13d", "alpn": ["h2"]},
    present=frozenset({"flow_reference", "parser_version", "parsed_handshake_metadata"}),
    visibility=None,
    quality=EvidenceQuality(),
    wire=WireDirection.FORWARD,
):
    return NetworkObservationEnvelope(
        observation_id="tls-1",
        schema_version="1.1",
        observation_type=ObservationType.TLS,
        event_time=NOW,
        causal_available_time=NOW,
        ingest_time=NOW,
        source_id="pcap-a",
        source_kind=SourceKind.PCAP,
        source_position="1",
        observation_contract="tls-v1",
        wire_direction=wire,
        direction_basis=DirectionBasis.CAPTURE_INTERFACE,
        finality=Finality.CURRENT,
        availability_basis=AvailabilityBasis.IMMEDIATE,
        provenance_ref="prov:tls-1",
        quality_ref="quality:tls-1" if quality.parser is QualityState.DEGRADED else "",
        present_fields=present,
        typed_payload=TLSObservation(
            "flow-1", "complete", "parser-7", metadata, None, None, None, ["gap-a"]
        ),
        visibility=visibility
        or VisibilityProfile(
            available=frozenset(
                {
                    VisibilityCapability.TLS_HANDSHAKE_METADATA,
                    VisibilityCapability.FORWARD_FACTS,
                }
            )
        ),
        quality=quality,
    )


def registry():
    registration = build_mvp_runtime_registration(NOW)
    return registration.plugins, registration.governances, registration.reorder_policies


def test_manifest_and_structural_routing_boundaries():
    plugins, _, _ = registry()
    plugin = plugins[LANE]
    manifest = plugin.manifest()
    assert manifest.plugin_id == "provider.encrypted_session.enc_a"
    assert manifest.official_ps_category is OfficialPsCategory.ENCRYPTED_SESSIONS
    assert manifest.mechanism_id == "ENC-A"
    assert manifest.integration_status is IntegrationStatus.BASELINE_IMPLEMENTED
    router = RelevanceRouter(plugins)
    assert router.route(tls()) == (LANE,)
    assert (
        router.plan(replace(tls(), present_fields=frozenset({"flow_reference", "parser_version"})))
        .decisions[-1]
        .reasons[0]
        .value
        == "REQUIRED_FIELD_MISSING"
    )
    record_only = replace(
        tls(),
        typed_payload=TLSObservation(
            "flow-1", "complete", "parser-7", None, {"length": 10}, None, None, None
        ),
        present_fields=frozenset({"flow_reference", "parser_version", "parsed_record_metadata"}),
        visibility=VisibilityProfile(
            available=frozenset({VisibilityCapability.TLS_RECORD_METADATA})
        ),
    )
    assert router.route(record_only) == ()
    assert (
        router.plan(replace(tls(), visibility=VisibilityProfile())).decisions[-1].reasons[0].value
        == "REQUIRED_CAPABILITY_UNAVAILABLE"
    )
    quic = NetworkObservationEnvelope(
        "quic-1",
        "1.1",
        ObservationType.QUIC,
        NOW,
        NOW,
        NOW,
        "pcap-a",
        SourceKind.PCAP,
        "2",
        "quic-v1",
        WireDirection.FORWARD,
        DirectionBasis.CAPTURE_INTERFACE,
        Finality.CURRENT,
        AvailabilityBasis.IMMEDIATE,
        "prov:q",
        "",
        frozenset({"parser_version"}),
        QUICObservation("flow-q", "1", "initial", 1, [], "q", 0, NOW, []),
    )
    assert router.route(quic) == ()


@pytest.mark.asyncio
async def test_end_to_end_factual_context_provenance_identity_and_persistence(tmp_path):
    plugins, governances, reorder_policies = registry()
    results = []

    async def collect(result, lane):
        results.append((result, lane))

    supervisor = RuntimeSupervisor(
        plugins, governances, collect, shard_count=1, reorder_policies=reorder_policies
    )
    supervisor.start_all()
    try:
        observation = replace(
            tls(),
            present_fields=frozenset(
                {
                    "flow_reference",
                    "parser_version",
                    "parsed_handshake_metadata",
                    "tcp_reassembly_state",
                    "gaps",
                }
            ),
        )
        assert (await supervisor.ingest_observation(observation)).selected_targets == (LANE,)
        await supervisor.dispatchers[LANE].queue.join()
        result, lane = results.pop()
        assert lane == LANE and result.result_type is ResultType.REVIEW_FINDING
        assert result.mechanism_id == "ENC-A" and result.state_version is None
        assert result.evidence.to_value() == {
            "evidence_kind": "ENCRYPTED_HANDSHAKE_CONTEXT",
            "protocol": "TLS",
            "flow_reference": "flow-1",
            "parser_version": "parser-7",
            "parsed_handshake_metadata": {"sni": "example.test", "ja4": "t13d", "alpn": ["h2"]},
            "tcp_reassembly_state": "complete",
            "gaps": ["gap-a"],
        }
        assert (
            result.parser_refs == ("TLS:parser-7",)
            and result.model_refs == ()
            and result.config_hash is None
        )
        assert (
            result.source_observation_ids == ("tls-1",)
            and result.visibility_snapshot == observation.visibility
        )
        assert "MALWARE_CONFIRMED" in result.claim_ceiling
        await supervisor.ingest_observation(observation)
        await supervisor.dispatchers[LANE].queue.join()
        replay, _ = results.pop()
        assert replay.result_id == result.result_id
        changed = replace(
            observation,
            typed_payload=replace(
                observation.typed_payload, parsed_handshake_metadata={"sni": "other.test"}
            ),
        )
        await supervisor.ingest_observation(changed)
        await supervisor.dispatchers[LANE].queue.join()
        assert results.pop()[0].result_id != result.result_id
        changed_parser = replace(
            observation, typed_payload=replace(observation.typed_payload, parser_version="parser-8")
        )
        await supervisor.ingest_observation(changed_parser)
        await supervisor.dispatchers[LANE].queue.join()
        assert results.pop()[0].result_id != result.result_id
        changed_visibility = replace(
            observation,
            visibility=VisibilityProfile(
                available=frozenset({VisibilityCapability.TLS_HANDSHAKE_METADATA})
            ),
        )
        await supervisor.ingest_observation(changed_visibility)
        await supervisor.dispatchers[LANE].queue.join()
        assert results.pop()[0].result_id != result.result_id
        changed_quality = replace(
            observation,
            quality=EvidenceQuality(parser=QualityState.DEGRADED),
            quality_ref="quality:tls-1",
        )
        await supervisor.ingest_observation(changed_quality)
        await supervisor.dispatchers[LANE].queue.join()
        assert results.pop()[0].result_id != result.result_id
        writer = SqliteWriter(tmp_path / "enc-a.db", "evidencegate/persistence/schema.sql")
        writer.connect()
        await writer.write_result(result)
        assert await writer.get_result(result.result_id) == result
        writer.close()
    finally:
        await supervisor.stop_all()


@pytest.mark.asyncio
async def test_client_only_survives_server_only_and_degraded_quality_are_factual():
    plugins, governances, reorder_policies = registry()
    collected = []

    async def collect(result, lane):
        collected.append(result)

    supervisor = RuntimeSupervisor(
        plugins, governances, collect, shard_count=1, reorder_policies=reorder_policies
    )
    supervisor.start_all()
    try:
        client_only = tls()
        assert (await supervisor.ingest_observation(client_only)).selected_targets == (LANE,)
        await supervisor.dispatchers[LANE].queue.join()
        assert len(collected) == 1
        assert plugins[LANE].state_key(client_only) is None
        server_only = replace(
            tls(),
            wire_direction=WireDirection.REVERSE,
            visibility=VisibilityProfile(
                available=frozenset({VisibilityCapability.REVERSE_FACTS}),
                unavailable=frozenset({VisibilityCapability.TLS_HANDSHAKE_METADATA}),
            ),
        )
        assert (await supervisor.ingest_observation(server_only)).selected_targets == ()
        degraded = tls(quality=EvidenceQuality(parser=QualityState.DEGRADED))
        await supervisor.ingest_observation(degraded)
        await supervisor.dispatchers[LANE].queue.join()
        assert collected[-1].quality_snapshot == degraded.quality
        assert collected[-1].status_snapshot.quality_degraded is False
    finally:
        await supervisor.stop_all()
