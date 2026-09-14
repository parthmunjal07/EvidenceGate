"""
persistence/sqlite.py — Atomic SQLite persistence for EvidenceGate results.

IC-18 / contract §9:
  result row + mandatory evidence items + provenance references + result links
  are written atomically in ONE transaction.

  On any child-write failure:
    - ROLLBACK the complete transaction
    - Leave no partial result row in the database

  For a repeated immutable result_id: idempotent no-op (INSERT OR IGNORE +
  rowcount check). Never allow divergent records.

WAL mode (IC-13): journal_mode=WAL is set on every connection before schema load.
"""
import sqlite3
import json
import asyncio
from pathlib import Path
from evidencegate.results.types import Result, ThreatAlert, AnalyticUnavailable, CorrelationFinding


class SqliteWriter:
    """
    Single application-owned SQLite writer in WAL mode.
    All writes use a single asyncio lock to serialise access from
    the async runtime.
    """

    def __init__(self, db_path: str | Path, schema_path: str | Path):
        self.db_path = str(db_path)
        self.schema_path = str(schema_path)
        self._conn: sqlite3.Connection | None = None
        self._lock = asyncio.Lock()

    def connect(self) -> None:
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        # IC-13: WAL mode must be enabled on every new connection
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA synchronous=NORMAL;")
        with open(self.schema_path, "r") as f:
            self._conn.executescript(f.read())
        self._conn.commit()

    async def write_result(self, result: Result) -> None:
        """
        IC-18: Write result + evidence_items + provenance_references + result_links
        atomically in one transaction.

        If the result_id already exists: idempotent no-op (INSERT OR IGNORE).
        If any child-write fails: ROLLBACK everything — no partial row left.
        """
        async with self._lock:
            if not self._conn:
                raise RuntimeError("Database not connected. Call connect() first.")
            self._write_result_sync(result)

    def _write_result_sync(self, result: Result) -> None:
        """
        Synchronous inner write wrapped in a single SQLite transaction.
        Raises on failure after rolling back.
        """
        conn = self._conn
        assert conn is not None

        # Disable autocommit by using explicit BEGIN
        conn.execute("BEGIN")
        try:
            cursor = conn.cursor()

            # ── Parent row (result) ─────────────────────────────────────────
            cursor.execute(
                """
                INSERT OR IGNORE INTO results (
                    result_id, result_type, created_time, entity_reference,
                    taxonomy_1, taxonomy_2, taxonomy_3,
                    plugin_version, analytic_version,
                    status_snapshot, claim_ceiling, quality_ref, provenance_ref,
                    confidence, severity, reason_code,
                    evidence_interval_start, evidence_interval_end
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.result_id,
                    result.result_type.value,
                    result.created_time.isoformat(),
                    result.entity_reference,
                    result.taxonomy[0] if result.taxonomy else None,
                    result.taxonomy[1] if len(result.taxonomy) > 1 else None if result.taxonomy else None,
                    result.taxonomy[2] if len(result.taxonomy) > 2 else None if result.taxonomy else None,
                    result.plugin_version,
                    result.analytic_version,
                    json.dumps(result.status_snapshot),
                    result.claim_ceiling,
                    result.quality_ref,
                    result.provenance_ref,
                    getattr(result, "confidence", None),
                    getattr(result, "severity", None),
                    getattr(result, "reason_code", None).value
                    if getattr(result, "reason_code", None) is not None
                    else None,
                    result.evidence_interval[0].isoformat()
                    if result.evidence_interval
                    else None,
                    result.evidence_interval[1].isoformat()
                    if result.evidence_interval
                    else None,
                ),
            )

            # If INSERT OR IGNORE fired (row already exists), rowcount == 0 →
            # idempotent no-op: skip children, commit, done.
            if cursor.rowcount == 0:
                conn.execute("COMMIT")
                return

            # ── Mandatory child: evidence_items ─────────────────────────────
            # Any exception here triggers full rollback (no partial result).
            for item in result.evidence_items:
                cursor.execute(
                    "INSERT INTO evidence_items (result_id, evidence_ref) VALUES (?, ?)",
                    (result.result_id, item),
                )

            # ── Mandatory child: provenance_references ──────────────────────
            if result.provenance_ref:
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO provenance_references
                        (result_id, provenance_ref)
                    VALUES (?, ?)
                    """,
                    (result.result_id, result.provenance_ref),
                )

            # ── Mandatory child: missing_prerequisites ──────────────────────
            for prereq in result.missing_prerequisites:
                cursor.execute(
                    "INSERT INTO missing_prerequisites (result_id, prerequisite) VALUES (?, ?)",
                    (result.result_id, prereq),
                )

            # ── Optional child: result_links (CorrelationFinding only) ──────
            if isinstance(result, CorrelationFinding):
                for linked_id in result.linked_result_ids:
                    cursor.execute(
                        "INSERT INTO result_links (source_result_id, linked_result_id) VALUES (?, ?)",
                        (result.result_id, linked_id),
                    )

            conn.execute("COMMIT")

        except Exception:
            # IC-18: On any child-write failure, ROLLBACK completely.
            # No partial result row remains.
            conn.execute("ROLLBACK")
            raise

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
