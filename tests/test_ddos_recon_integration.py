"""Combined DDoS/Recon integration and scientific-firewall regression."""

from datetime import datetime, timedelta, timezone

import pytest

from evidencegate.domain.enums import (
    AvailabilityBasis,
    DirectionBasis,
    Finality,
    IdentityBasis,
    ObservationType,
    QualityState,
    ResultType,
    ScientificStatus,
    SourceKind,
    VisibilityCapability,
    WireDirection,
)
from evidencegate.domain.events import (
    NetworkObservationEnvelope,
    ObservationIdentity,
    RoleAssignment,
    VisibilityProfile,
)
from evidencegate.domain.governance import LaneGovernance
from evidencegate.domain.payloads import PacketObservation
from evidencegate.domain.quality import EvidenceQuality
from evidencegate.persistence.sqlite import SqliteWriter
from evidencegate.plugins.providers.ddos import DdosASynPlugin
from evidencegate.plugins.providers.ddos_config import (
    DdosASynConfig,
    DdosConnectionChurnConfig,
    DdosSourceDiversityConfig,
)
from evidencegate.plugins.providers.ddos_measurements import (
    DdosConnectionChurnPlugin,
    DdosSourceDiversityPlugin,
)
from evidencegate.plugins.providers.recon import (
    CLAIM_CEILING as RECON_CLAIM_CEILING,
    Recon2DPlugin,
    ReconHPlugin,
    ReconTcpPlugin,
    ReconVPlugin,
)
from evidencegate.plugins.providers.recon_config import ReconConfig
from evidencegate.results.types import ThreatAlert
from evidencegate.routing.router import LaneTarget
from evidencegate.runtime.dispatcher import EventTimeReorderPolicy
from evidencegate.runtime.supervisor import RuntimeSupervisor


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
SCHEMA = "evidencegate/persistence/schema.sql"
DECISION_ID = "DDOS-RECON-INTEGRATION-TEST-BOUND"


def _plugins():
    recon_config = ReconConfig(
        config_id="ddos-recon-integration-test",
        horizons=(timedelta(seconds=10), timedelta(seconds=60)),
        max_events_per_key=8,
        state_ttl=timedelta(seconds=60),
        initiator_role_label="initiator_id",
        target_role_label="target_id",
    )
    decision = (DECISION_ID,)
    return {
        LaneTarget("ddos.syn_state"): DdosASynPlugin(
            DdosASynConfig.reference_poc_v1(),
            max_state_entries=16,
            governing_decision_ids=decision,
        ),
        LaneTarget("ddos.source_diversity"): DdosSourceDiversityPlugin(
            DdosSourceDiversityConfig.reference_poc_v1(),
            max_state_entries=16,
            max_sources_per_window=8,
            governing_decision_ids=decision,
        ),
        LaneTarget("ddos.connection_churn"): DdosConnectionChurnPlugin(
            DdosConnectionChurnConfig.reference_poc_v1(),
            max_state_entries=16,
            max_attempts_per_window=8,
            governing_decision_ids=decision,
        ),
        LaneTarget("recon.h"): ReconHPlugin(
            recon_config,
            max_state_entries=16,
            governing_decision_ids=decision,
        ),
        LaneTarget("recon.v"): ReconVPlugin(
            recon_config,
            max_state_entries=16,
            governing_decision_ids=decision,
        ),
        LaneTarget("recon.2d"): Recon2DPlugin(
            recon_config,
            max_state_entries=16,
            governing_decision_ids=decision,
        ),
        LaneTarget("recon.tcp"): ReconTcpPlugin(
            recon_config,
            max_state_entries=16,
            governing_decision_ids=decision,
        ),
    }


def _governance(lane, plugin):
    return LaneGovernance(
        analytic_lane=str(lane),
        scientific_status=ScientificStatus.EVIDENCE_CONSTRUCTION,
        scientific_phase="combined factual integration test",
        scientific_blockers=("default activation requires human gate",),
        claim_ceiling=getattr(plugin, "claim_ceiling", RECON_CLAIM_CEILING),
        governance_version="ddos-recon-integration-test-v1",
        effective_at=NOW,
        allowed_result_types=(
            ResultType.REVIEW_FINDING,
            ResultType.INSUFFICIENT_EVIDENCE,
            ResultType.QUALITY_DEGRADED,
        ),
        ingest_permitted=True,
    )


def _packet(milliseconds: int) -> NetworkObservationEnvelope:
    event_time = NOW + timedelta(milliseconds=milliseconds)
    initiator, target = "198.51.100.10", "10.0.0.2"
    payload = PacketObservation(
        lengths={"ip": 40},
        observed_l2_facts={},
        observed_l3_facts={},
        observed_l4_facts={},
        src_address=initiator,
        dst_address=target,
        src_port=51000,
        dst_port=443,
        flags=["SYN"],
        sequence_facts=None,
        fragmentation=None,
        raw_reference=f"mixed:{milliseconds}",
        protocol=6,
    )
    return NetworkObservationEnvelope(
        observation_id=f"mixed-packet-{milliseconds}",
        schema_version="1.1",
        observation_type=ObservationType.PACKET,
        event_time=event_time,
        causal_available_time=event_time,
        ingest_time=event_time,
        source_id="ddos-recon-mixed-fixture",
        source_kind=SourceKind.DERIVED,
        source_position=str(milliseconds),
        observation_contract="REPLAY_TYPED_V1",
        wire_direction=WireDirection.FORWARD,
        direction_basis=DirectionBasis.CAPTURE_INTERFACE,
        finality=Finality.CURRENT,
        availability_basis=AvailabilityBasis.IMMEDIATE,
        provenance_ref=f"prov:mixed:{milliseconds}",
        quality_ref=f"quality:mixed:{milliseconds}",
        present_fields=frozenset(
            {
                "lengths",
                "protocol",
                "src_address",
                "dst_address",
                "src_port",
                "dst_port",
                "flags",
                "raw_reference",
            }
        ),
        typed_payload=payload,
        visibility=VisibilityProfile(
            available=frozenset(
                {
                    VisibilityCapability.PACKET_FACTS,
                    VisibilityCapability.FORWARD_FACTS,
                    VisibilityCapability.REVERSE_FACTS,
                }
            )
        ),
        quality=EvidenceQuality(
            packet_loss=QualityState.CLEAR,
            sampling=QualityState.CLEAR,
            parser=QualityState.CLEAR,
            capture_gap=QualityState.CLEAR,
        ),
        identity=ObservationIdentity(
            observed_identifiers=(initiator, target),
            identifier_basis=IdentityBasis.OBSERVED_IDENTIFIER,
            role_assignments=(
                RoleAssignment(
                    initiator,
                    "initiator_id",
                    IdentityBasis.SOURCE_DECLARED_ROLE,
                ),
                RoleAssignment(
                    target,
                    "target_id",
                    IdentityBasis.SOURCE_DECLARED_ROLE,
                ),
                RoleAssignment(
                    "tcp/443",
                    "service_id",
                    IdentityBasis.SOURCE_DECLARED_ROLE,
                ),
            ),
        ),
    )


@pytest.mark.asyncio
async def test_mixed_zero_to_many_firewall_immutability_and_sqlite(tmp_path):
    plugins = _plugins()
    governances = {lane: _governance(lane, plugin) for lane, plugin in plugins.items()}
    results = []
    writer = SqliteWriter(tmp_path / "ddos-recon.db", SCHEMA)
    writer.connect()

    async def persist(result, lane):
        results.append((lane, result))
        await writer.write_result(result)

    supervisor = RuntimeSupervisor(
        plugins,
        governances,
        persist,
        shard_count=2,
        reorder_policies={lane: EventTimeReorderPolicy(16, 128) for lane in plugins},
    )
    supervisor.start_all()
    try:
        first = _packet(0)
        plan = await supervisor.ingest_observation(first)
        assert set(plan.selected_targets) == set(plugins)
        for lane in plugins:
            await supervisor.advance_watermark(lane, NOW + timedelta(milliseconds=1))
            await supervisor.dispatchers[lane].queue.join()

        assert all(len(store) == 1 for store in supervisor.state_stores.values())
        for lane, store in supervisor.state_stores.items():
            payload_name = type(next(iter(store._state.values())).payload).__name__
            assert (
                payload_name.startswith("Ddos")
                if str(lane).startswith("ddos.")
                else payload_name.startswith("Recon")
            )

        prior_snapshots = tuple(
            (result.result_id, result.evidence.canonical_json, result.state_version)
            for _, result in results
        )
        assert len(prior_snapshots) == 5

        second = _packet(100)
        second_plan = await supervisor.ingest_observation(second)
        assert set(second_plan.selected_targets) == set(plugins)
        for lane in plugins:
            await supervisor.advance_watermark(lane, NOW + timedelta(milliseconds=101))
            await supervisor.dispatchers[lane].queue.join()

        assert prior_snapshots == tuple(
            (result.result_id, result.evidence.canonical_json, result.state_version)
            for _, result in results[:5]
        )

        for lane in plugins:
            await supervisor.advance_watermark(lane, NOW + timedelta(seconds=2))
            await supervisor.dispatchers[lane].queue.join()

        assert {result.mechanism_id for _, result in results} == {
            "DDOS-A-B0",
            "DDOS-D-B0",
            "DDOS-E3-B0",
            "RECON-H",
            "RECON-V",
            "RECON-2D",
            "RECON-TCP",
        }
        assert not any(isinstance(result, ThreatAlert) for _, result in results)

        result_ids = {result.result_id for _, result in results}
        for _, result in results:
            other_ids = result_ids - {result.result_id}
            assert not any(value in result.evidence.canonical_json for value in other_ids)
            stored = await writer.get_result(result.result_id)
            assert stored == result
            assert stored.mechanism_id and stored.config_hash
            assert stored.claim_ceiling and stored.governing_ids == (DECISION_ID,)
            assert stored.source_observation_ids
            assert stored.quality_snapshot == result.quality_snapshot
            assert stored.visibility_snapshot == result.visibility_snapshot
    finally:
        await supervisor.stop_all()
        writer.close()
