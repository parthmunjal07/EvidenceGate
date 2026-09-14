import asyncio
import time
import psutil
import json
import statistics
from datetime import datetime
from collections import deque

from evidencegate.domain.events import NetworkObservationEnvelope
from evidencegate.domain.payloads import PacketObservation
from evidencegate.domain.enums import ObservationType, ScientificStatus
from evidencegate.domain.governance import LaneGovernance
from evidencegate.plugins.scaffolds.basic_scaffold import BasicScaffoldPlugin
from evidencegate.runtime.supervisor import RuntimeSupervisor
from evidencegate.persistence.sqlite import SqliteWriter

# We monkey-patch the queue size to a small number to test saturation
import evidencegate.runtime.shard
from evidencegate.runtime.shard import LaneShard

# We need to capture plugin processing latency. We can wrap the basic scaffold's process method.
class BenchmarkPlugin(BasicScaffoldPlugin):
    def __init__(self, latencies: list):
        super().__init__()
        self.latencies = latencies

    async def process(self, observation, context, state):
        start = time.perf_counter()
        # Simulate tiny amount of work
        await asyncio.sleep(0) 
        res = await super().process(observation, context, state)
        self.latencies.append(time.perf_counter() - start)
        return res

async def track_system_health(metrics_q, stop_event):
    p = psutil.Process()
    while not stop_event.is_set():
        start_loop = time.perf_counter()
        await asyncio.sleep(0.01) # target 10ms sleep
        lag = time.perf_counter() - start_loop - 0.01
        
        metrics_q.append({
            'cpu': p.cpu_percent(),
            'rss': p.memory_info().rss / (1024 * 1024), # MB
            'loop_lag_ms': max(0, lag * 1000)
        })
        await asyncio.sleep(0.09) # Poll every 100ms roughly

async def benchmark_run():
    print("Initializing benchmark...")
    
    # 1. Persistence
    db_writer = SqliteWriter(":memory:", "evidencegate/persistence/schema.sql")
    db_writer.connect()
    
    persistence_latencies = []
    
    from evidencegate.results.types import ReviewFinding
    
    async def instrumented_writer(res, target):
        import uuid
        start = time.perf_counter()
        
        # Convert draft to a full Result object so db_writer doesn't crash
        full_res = ReviewFinding(
            result_id=str(uuid.uuid4()),
            result_type=res.result_type,
            created_time=datetime.now(),
            entity_reference=res.entity_reference,
            taxonomy=("A", "B", "C"),
            plugin_version="1",
            analytic_version="1",
            status_snapshot={},
            claim_ceiling="test",
            quality_ref="q",
            provenance_ref="p",
            evidence_items=res.evidence_items,
            missing_prerequisites=res.missing_prerequisites,
            governing_ids=()
        )
        
        await db_writer.write_result(full_res)
        persistence_latencies.append(time.perf_counter() - start)

    # 2. Supervisor Configuration (4 lanes, 4 shards each)
    plugin_latencies = []
    plugins = {
        f"lane_{i}": BenchmarkPlugin(plugin_latencies) for i in range(4)
    }
    governances = {
        f"lane_{i}": LaneGovernance(
            analytic_lane=f"lane_{i}",
            scientific_status=ScientificStatus.EVIDENCE_CONSTRUCTION,
            scientific_phase="test",
            scientific_blockers=(),
            claim_ceiling="test",
            governance_version="1",
            effective_at=datetime.now()
        ) for i in range(4)
    }
    
    supervisor = RuntimeSupervisor(
        plugins=plugins,
        governances=governances,
        result_writer=instrumented_writer,
        shard_count=4
    )
    
    # Override queue maxsize for bounded testing to 100 per shard
    for lane, shards in supervisor.shards.items():
        for shard in shards:
            shard.queue = asyncio.Queue(maxsize=100)
            
    supervisor.start_all()
    
    # 3. Fixture Generation
    TOTAL_ITEMS = 5000
    print(f"Generating {TOTAL_ITEMS} pre-allocated fixtures...")
    payload = PacketObservation(
        lengths={"ip": 20}, observed_l2_facts={}, observed_l3_facts={}, observed_l4_facts={},
        src_address="10.0.0.1", dst_address="10.0.0.2", src_port=None, dst_port=None,
        flags=[], sequence_facts=None, fragmentation=None, raw_reference=None
    )
    
    fixtures = [
        NetworkObservationEnvelope(
            observation_id=f"obs_{i}", schema_version="1", observation_type=ObservationType.PACKET,
            event_time=datetime.now(), causal_available_time=datetime.now(), ingest_time=datetime.now(),
            source_id="s", source_kind="k", source_position=str(i), observation_contract="c",
            wire_direction="fwd", direction_basis="b", finality=True, availability_basis="e",
            provenance_ref="p", quality_ref="q", present_fields=set(), typed_payload=payload
        ) for i in range(TOTAL_ITEMS)
    ]
    
    # 4. Background Monitoring
    sys_metrics = deque()
    stop_event = asyncio.Event()
    monitor_task = asyncio.create_task(track_system_health(sys_metrics, stop_event))
    
    # 5. Inject Workload
    print(f"Starting replay pacing injection...")
    start_time = time.perf_counter()
    
    for obs in fixtures:
        await supervisor.ingest_observation(obs)
        # Yield to event loop periodically to simulate pacing
        if int(obs.source_position) % 50 == 0:
            await asyncio.sleep(0) 
            
    # Wait for queues to drain
    print("Waiting for shards to drain...")
    drain_start = time.perf_counter()
    while True:
        total_qsize = sum(shard.queue.qsize() for shards in supervisor.shards.values() for shard in shards)
        if total_qsize == 0:
            break
        await asyncio.sleep(0.05)
        if time.perf_counter() - drain_start > 10.0:
            print("Drain timeout.")
            break
            
    end_time = time.perf_counter()
    duration = end_time - start_time
    
    # 6. Cleanup
    stop_event.set()
    await monitor_task
    await supervisor.stop_all()
    
    cursor = db_writer._conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM results")
    db_results_count = cursor.fetchone()[0]
    db_writer.close()
    
    # 7. Reporting Calculate
    def calc_pct(data, pct):
        if not data: return 0.0
        return statistics.quantiles(data, n=100)[pct-1] * 1000 # ms
        
    avg_cpu = sum(m['cpu'] for m in sys_metrics) / len(sys_metrics) if sys_metrics else 0
    max_rss = max(m['rss'] for m in sys_metrics) if sys_metrics else 0
    avg_lag = sum(m['loop_lag_ms'] for m in sys_metrics) / len(sys_metrics) if sys_metrics else 0
    
    # Print JSON output for easy capture
    report = {
        "Config": {
            "Total Ingested": TOTAL_ITEMS,
            "Lanes": 4,
            "Shards/Lane": 4,
            "Queue Size": 100
        },
        "Throughput": {
            "Duration (s)": round(duration, 3),
            "Ingest Rate (ops/s)": round(TOTAL_ITEMS / duration, 1),
            "Results Persisted": db_results_count
        },
        "Latency (ms)": {
            "Plugin p50": round(calc_pct(plugin_latencies, 50), 3),
            "Plugin p95": round(calc_pct(plugin_latencies, 95), 3),
            "Plugin p99": round(calc_pct(plugin_latencies, 99), 3),
            "DB Write p50": round(calc_pct(persistence_latencies, 50), 3),
            "DB Write p95": round(calc_pct(persistence_latencies, 95), 3),
            "DB Write p99": round(calc_pct(persistence_latencies, 99), 3),
        },
        "System Health": {
            "Avg CPU %": round(avg_cpu, 1),
            "Peak RSS (MB)": round(max_rss, 1),
            "Avg Loop Lag (ms)": round(avg_lag, 3)
        }
    }
    
    print("\n=== BENCHMARK REPORT SUMMARY ===")
    print(json.dumps(report, indent=2))
    
if __name__ == "__main__":
    asyncio.run(benchmark_run())
