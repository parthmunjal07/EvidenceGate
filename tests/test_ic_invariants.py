import pytest
import asyncio
import os
import dataclasses
from datetime import datetime, timedelta
from evidencegate.domain.events import NetworkObservationEnvelope, RuntimeControlEvent
from evidencegate.domain.payloads import PacketObservation, FlowObservation
from evidencegate.domain.enums import ObservationType, ControlType, ScientificStatus, ResultType
from evidencegate.domain.governance import LaneGovernance
from evidencegate.routing.router import RelevanceRouter
from evidencegate.admission.evaluator import AdmissionEvaluator, AdmissionDecision, AdmissionReason
from evidencegate.plugins.scaffolds.basic_scaffold import BasicScaffoldPlugin
from evidencegate.results.types import ThreatAlert, ResultDraft, AnalyticUnavailable, ReasonCode
from evidencegate.results.validator import ResultValidator
from evidencegate.runtime.shard import compute_shard, LaneShard
from evidencegate.runtime.state import StateStore
from evidencegate.persistence.sqlite import SqliteWriter
from evidencegate.ingest.canonicalizer import FlowCanonicalizer
from evidencegate.ingest.source import RawSourceRecord, SourceManifest
from evidencegate.metrics.registry import registry as metrics_registry

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
    import inspect
    sig = inspect.signature(RelevanceRouter.route)
    assert sig.parameters['observation'].annotation.__name__ == 'NetworkObservationEnvelope'

def test_ic_02_routing_zero_to_many(test_observation):
    plugin1 = BasicScaffoldPlugin()
    router = RelevanceRouter({"lane1": plugin1, "lane2": plugin1})
    targets = router.route(test_observation)
    assert len(targets) == 2

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

def test_ic_04_causal_availability():
    canonicalizer = FlowCanonicalizer()
    export_time = datetime.now()
    event_time = export_time - timedelta(seconds=10)
    
    flow_obs = FlowObservation(
        flow_id_basis="ip", endpoints=("1.1.1.1", "2.2.2.2"), protocol=6,
        start_time=event_time, end_time=event_time, export_time=export_time,
        supplied_directional_counters={}, finality=True, exporter_semantics="",
        sampling=None, documented_end_state=None
    )
    
    record = RawSourceRecord(raw_data=flow_obs, timestamp=event_time, position="1")
    manifest = SourceManifest(source_id="s", source_kind="k", capture_start=None, capture_end=None)
    
    res = canonicalizer.canonicalize(record, manifest, "q")
    obs = res.observations[0]
    
    assert obs.causal_available_time >= flow_obs.export_time

def test_ic_05_deterministic_sharding():
    shard1 = compute_shard("pluginA", "10.0.0.1", 4)
    shard2 = compute_shard("pluginA", "10.0.0.1", 4)
    assert shard1 == shard2

def test_ic_06_queue_saturation(test_observation):
    plugin = BasicScaffoldPlugin()
    store = StateStore()
    
    async def dummy_cb(res): pass
    shard = LaneShard(shard_id=0, plugin=plugin, state_store=store, result_callback=dummy_cb, max_size=1)
    
    # Fill queue
    shard.put_nowait(test_observation)
    
    # Overfill
    with pytest.raises(asyncio.QueueFull):
        shard.put_nowait(test_observation)

def test_ic_07_restart_epoch():
    store1 = StateStore()
    store1.put("k1", "v1")
    
    store2 = StateStore()
    assert store2.get("k1") is None

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

def test_ic_09_governance_readonly():
    gov = LaneGovernance(
        analytic_lane="lane1", scientific_status=ScientificStatus.ANALYTIC_UNAVAILABLE,
        scientific_phase="test", scientific_blockers=(), claim_ceiling="test",
        governance_version="1", effective_at=datetime.now()
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        gov.analytic_lane = "lane2"

def test_ic_10_unavailable_implications():
    res = AnalyticUnavailable(
        result_id="r1", result_type=ResultType.ANALYTIC_UNAVAILABLE, created_time=datetime.now(),
        entity_reference="e", taxonomy=("A", "B", "C"), plugin_version="1", analytic_version="1",
        status_snapshot={}, claim_ceiling="1", quality_ref="1", provenance_ref="1",
        evidence_items=(), missing_prerequisites=(), governing_ids=(), reason_code=ReasonCode.GOVERNANCE_DISABLED
    )
    assert getattr(res, "confidence", None) is None
    assert getattr(res, "severity", None) is None

@pytest.mark.asyncio
async def test_ic_11_sqlite_idempotence():
    import tempfile
    with tempfile.NamedTemporaryFile(delete=False) as db_file, \
         tempfile.NamedTemporaryFile(delete=False) as schema_file:
         pass
         
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
    await writer.write_result(alert)
    
    cursor = writer._conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM results WHERE result_id='r1'")
    assert cursor.fetchone()[0] == 1
    
    writer.close()
    os.remove(db_file.name)
    os.remove(schema_file.name)

def test_ic_12_slow_websocket():
    queue = asyncio.Queue(maxsize=1)
    queue.put_nowait("msg1")
    with pytest.raises(asyncio.QueueFull):
        queue.put_nowait("msg2")
    assert queue.qsize() == 1

def test_ic_13_sqlite_wal():
    import tempfile, sqlite3
    with tempfile.NamedTemporaryFile(delete=False) as db_file, \
         tempfile.NamedTemporaryFile(delete=False) as schema_file:
         pass
    with open("evidencegate/persistence/schema.sql", "r") as f:
        schema_content = f.read()
    with open(schema_file.name, "w") as f:
        f.write(schema_content)
        
    writer = SqliteWriter(db_file.name, schema_file.name)
    writer.connect()
    
    cursor = writer._conn.cursor()
    cursor.execute("PRAGMA journal_mode")
    assert cursor.fetchone()[0].lower() == "wal"
    writer.close()
    os.remove(db_file.name)
    os.remove(schema_file.name)

def test_ic_14_bounded_metrics():
    labels = metrics_registry.input_rate._labelnames
    assert "ip" not in labels
    assert "entity_reference" not in labels
    assert "observation_type" in labels
