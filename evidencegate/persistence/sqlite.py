import sqlite3
import json
import asyncio
from pathlib import Path
from evidencegate.results.types import Result, ThreatAlert, AnalyticUnavailable, CorrelationFinding

class SqliteWriter:
    """
    A single application-owned SQLite writer in WAL mode.
    Handles result persistence idempotently.
    """
    def __init__(self, db_path: str | Path, schema_path: str | Path):
        self.db_path = str(db_path)
        self.schema_path = str(schema_path)
        self._conn = None
        self._lock = asyncio.Lock()

    def connect(self):
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA synchronous=NORMAL;")
        
        with open(self.schema_path, "r") as f:
            self._conn.executescript(f.read())
        self._conn.commit()

    async def write_result(self, result: Result):
        async with self._lock:
            if not self._conn:
                raise RuntimeError("Database not connected.")
                
            cursor = self._conn.cursor()
            
            try:
                # Use REPLACE or IGNORE to ensure idempotence
                # We use IGNORE because results are immutable (IC-11)
                cursor.execute('''
                    INSERT OR IGNORE INTO results (
                        result_id, result_type, created_time, entity_reference,
                        taxonomy_1, taxonomy_2, taxonomy_3, plugin_version, analytic_version,
                        status_snapshot, claim_ceiling, quality_ref, provenance_ref,
                        confidence, severity, reason_code, evidence_interval_start, evidence_interval_end
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    result.result_id,
                    result.result_type.value,
                    result.created_time.isoformat(),
                    result.entity_reference,
                    result.taxonomy[0] if result.taxonomy else None,
                    result.taxonomy[1] if result.taxonomy else None,
                    result.taxonomy[2] if result.taxonomy else None,
                    result.plugin_version,
                    result.analytic_version,
                    json.dumps(result.status_snapshot),
                    result.claim_ceiling,
                    result.quality_ref,
                    result.provenance_ref,
                    getattr(result, "confidence", None),
                    getattr(result, "severity", None),
                    getattr(result, "reason_code", None).value if hasattr(result, "reason_code") and getattr(result, "reason_code", None) is not None else None,
                    result.evidence_interval[0].isoformat() if result.evidence_interval else None,
                    result.evidence_interval[1].isoformat() if result.evidence_interval else None
                ))
                
                # If the insert was ignored (already exists), rowcount is 0, skip children to remain idempotent
                if cursor.rowcount > 0:
                    for item in result.evidence_items:
                        cursor.execute('INSERT INTO evidence_items (result_id, evidence_ref) VALUES (?, ?)', (result.result_id, item))
                        
                    for prereq in result.missing_prerequisites:
                        cursor.execute('INSERT INTO missing_prerequisites (result_id, prerequisite) VALUES (?, ?)', (result.result_id, prereq))
                        
                    if isinstance(result, CorrelationFinding):
                        for linked in result.linked_result_ids:
                            cursor.execute('INSERT INTO result_links (source_result_id, linked_result_id) VALUES (?, ?)', (result.result_id, linked))

                self._conn.commit()
            except Exception as e:
                self._conn.rollback()
                raise e

    def close(self):
        if self._conn:
            self._conn.close()
