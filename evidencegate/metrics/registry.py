from prometheus_client import Counter, Histogram, Gauge

# Bounded metric labels only (no IPs, domains, flow IDs, result IDs)
# Valid labels: lane, status, observation_type, plugin_id, shard_id

class MetricsRegistry:
    def __init__(self):
        self.input_rate = Counter(
            'evidencegate_input_total', 
            'Total observations ingested', 
            ['observation_type', 'status'] # status: admitted, dropped
        )
        
        self.routed_rate = Counter(
            'evidencegate_routed_total', 
            'Total observations routed to a lane', 
            ['lane', 'observation_type']
        )
        
        self.processed_rate = Counter(
            'evidencegate_processed_total', 
            'Total observations processed by plugins', 
            ['plugin_id', 'status']
        )
        
        self.queue_depth = Gauge(
            'evidencegate_queue_depth',
            'Current depth of lane shard queues',
            ['lane', 'shard_id']
        )
        
        self.queue_full_events = Counter(
            'evidencegate_queue_full_total',
            'Total queue full / saturation events',
            ['lane', 'shard_id']
        )
        
        self.processing_latency = Histogram(
            'evidencegate_processing_latency_seconds',
            'Plugin processing latency',
            ['plugin_id'],
            buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0]
        )
        
        self.processing_errors = Counter(
            'evidencegate_processing_errors_total',
            'Total bounded runtime processing errors',
            ['lane', 'plugin_id']
        )

# Global metrics registry instance
registry = MetricsRegistry()
