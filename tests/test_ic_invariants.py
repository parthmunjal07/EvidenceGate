import pytest
from datetime import datetime
from evidencegate.domain.events import NetworkObservationEnvelope, RuntimeControlEvent
from evidencegate.domain.payloads import PacketObservation
from evidencegate.domain.enums import ObservationType, ControlType, ScientificStatus, ResultType
from evidencegate.domain.governance import LaneGovernance
from evidencegate.routing.router import RelevanceRouter
from evidencegate.admission.evaluator import AdmissionEvaluator, AdmissionDecision, AdmissionReason
from evidencegate.plugins.scaffolds.basic_scaffold import BasicScaffoldPlugin
from evidencegate.results.types import ThreatAlert, ResultDraft
from evidencegate.results.validator import ResultValidator
from evidencegate.runtime.shard import compute_shard
from evidencegate.persistence.sqlite import SqliteWriter
import asyncio
import os

@pytest.fixture
def test_observation():
    payload = PacketObservation(
        lengths={"ip": 20}, observed_l2_facts={}, observed_l3_facts={}, observed_l4_facts={},
        src_address="10.0.0.1", dst_address="10.0.0.2", src_port=None, dst_port=None,
        flags=[], sequence_facts=None, fragmentation=None, raw_reference=None
    )
    return NetworkObservationEnvelope(
        observation_id="test_obs_1", schema_version="1", observation_type=ObservationType.PACKET,
        event_time=datetime.now(), causal_available_time=datetime.now(), ingest_time=datetime.now(),
        source_id="test_src", source_kind="test", source_position="0", observation_contract="test",
        wire_direction="fwd", direction_basis="test", finality=True, availability_basis="test",
        provenance_ref="p", quality_ref="q", present_fields=set(), typed_payload=payload
    )

def test_ic_01_router_typing():
    # A control event cannot enter the router, typing prevents it
    # We verify this manually via inspection, but we can verify the router only accepts NetworkObservation
    import inspect
    sig = inspect.signature(RelevanceRouter.route)
    assert sig.parameters['observation'].annotation.__name__ == 'NetworkObservationEnvelope'

def test_ic_02_routing_zero_to_many(test_observation):
    plugin1 = BasicScaffoldPlugin()
    # Plugin1 accepts PACKET, so it should route
    router = RelevanceRouter({"lane1": plugin1, "lane2": plugin1})
    targets = router.route(test_observation)
    assert len(targets) == 2
    assert "lane1" in targets
    assert "lane2" in targets

def test_ic_03_admission_unavailable(test_observation):
    plugin = BasicScaffoldPlugin()
    gov = LaneGovernance(
        analytic_lane="lane1", scientific_status=ScientificStatus.ANALYTIC_UNAVAILABLE,
        scientific_phase="test", scientific_blockers=("missing_data",), claim_ceiling="test",
        governance_version="1", effective_at=datetime.now()
    )
    decision = AdmissionEvaluator.evaluate(test_observation, plugin.manifest(), gov)
    assert not decision.admitted
    assert AdmissionReason.ANALYTIC_UNAVAILABLE in decision.reasons

def test_ic_05_deterministic_sharding():
    shard1 = compute_shard("pluginA", "10.0.0.1", 4)
    shard2 = compute_shard("pluginA", "10.0.0.1", 4)
    assert shard1 == shard2
    # Different key likely routes to different or same, but deterministic
    shard3 = compute_shard("pluginA", "10.0.0.2", 4)
    assert isinstance(shard3, int)

def test_ic_08_scaffold_no_threat_alert():
    gov = LaneGovernance(
        analytic_lane="lane1", scientific_status=ScientificStatus.EVIDENCE_CONSTRUCTION,
        scientific_phase="test", scientific_blockers=(), claim_ceiling="test",
        governance_version="1", effective_at=datetime.now()
    )
    
    alert = ThreatAlert(
        result_id="r1", result_type=ResultType.THREAT_ALERT, created_time=datetime.now(),
        entity_reference="e", taxonomy=("A", "B", "C"), plugin_version="1", analytic_version="1",
        status_snapshot={}, claim_ceiling="1", quality_ref="1", provenance_ref="1",
        evidence_items=(), missing_prerequisites=(), governing_ids=(), confidence="HIGH"
    )
    
    with pytest.raises(ValueError, match="ThreatAlert cannot be emitted from a scaffold"):
        ResultValidator.validate(alert, gov)

@pytest.mark.asyncio
async def test_ic_11_sqlite_idempotence():
    import tempfile
    with tempfile.NamedTemporaryFile(delete=False) as db_file, \
         tempfile.NamedTemporaryFile(delete=False) as schema_file:
         pass
         
    # Generate schema file
    with open("evidencegate/persistence/schema.sql", "r") as f:
        schema_content = f.read()
    with open(schema_file.name, "w") as f:
        f.write(schema_content)
        
    writer = SqliteWriter(db_file.name, schema_file.name)
    writer.connect()
    
    alert = ThreatAlert(
        result_id="r1", result_type=ResultType.THREAT_ALERT, created_time=datetime.now(),
        entity_reference="e", taxonomy=("A", "B", "C"), plugin_version="1", analytic_version="1",
        status_snapshot={}, claim_ceiling="1", quality_ref="1", provenance_ref="1",
        evidence_items=("ev1",), missing_prerequisites=(), governing_ids=(), confidence="HIGH"
    )
    
    await writer.write_result(alert)
    # Second write should be ignored idempotently (no crash)
    await writer.write_result(alert)
    
    cursor = writer._conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM results WHERE result_id='r1'")
    assert cursor.fetchone()[0] == 1
    
    cursor.execute("SELECT COUNT(*) FROM evidence_items WHERE result_id='r1'")
    assert cursor.fetchone()[0] == 1 # Only 1 row because the second insert was ignored
    
    writer.close()
    os.remove(db_file.name)
    os.remove(schema_file.name)
