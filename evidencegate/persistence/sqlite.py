"""SQLite repository for immutable, finalized EvidenceGate results."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from evidencegate.domain.enums import (
    AnalyticUnavailableReason, EvidenceReadiness, IntegrationStatus,
    QualityState, ResultType, ScientificStatus, VisibilityCapability,
)
from evidencegate.domain.events import VisibilityProfile
from evidencegate.domain.quality import EvidenceQuality
from evidencegate.results.finalizer import canonical_result_content, result_id_for
from evidencegate.results.types import (
    AnalyticUnavailable, CorrelationFinding, EvidencePayload,
    InsufficientEvidence, PluginStatus, PrerequisiteMissing, QualityDegraded,
    Result, ResultDraft, ResultStatusSnapshot, ReviewFinding, ThreatAlert,
)


class PersistenceError(RuntimeError):
    """Base class for repository-level persistence failures."""


class ResultIdentityConflict(PersistenceError):
    """A result ID is already associated with unverifiable or different content."""


class SchemaMigrationError(PersistenceError):
    """The database could not be brought to the supported schema version."""


_RESULT_CLASSES = {
    ResultType.THREAT_ALERT: ThreatAlert, ResultType.REVIEW_FINDING: ReviewFinding,
    ResultType.ANALYTIC_UNAVAILABLE: AnalyticUnavailable, ResultType.PREREQUISITE_MISSING: PrerequisiteMissing,
    ResultType.INSUFFICIENT_EVIDENCE: InsufficientEvidence, ResultType.QUALITY_DEGRADED: QualityDegraded,
    ResultType.PLUGIN_STATUS: PluginStatus, ResultType.CORRELATION_FINDING: CorrelationFinding,
}


def _time_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise PersistenceError("result datetimes must be timezone-aware")
    return value.isoformat(timespec="microseconds")


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _quality_json(value: EvidenceQuality) -> str:
    return _canonical_json({
        "packet_loss": value.packet_loss.value,
        "sampling": value.sampling.value,
        "parser": value.parser.value,
        "capture_gap": value.capture_gap.value,
    })


def _visibility_json(value: VisibilityProfile) -> str:
    return _canonical_json({
        "available": sorted(item.value for item in value.available),
        "unavailable": sorted(item.value for item in value.unavailable),
        "degraded": sorted(item.value for item in value.degraded),
    })


class SqliteWriter:
    """Application-owned, locked SQLite repository with explicit migrations."""

    def __init__(self, db_path: str | Path, schema_path: str | Path):
        self.db_path, self.schema_path = str(db_path), str(schema_path)
        self._conn: sqlite3.Connection | None = None
        self._lock = asyncio.Lock()

    def connect(self) -> None:
        if self._conn is not None:
            raise PersistenceError("Database is already connected.")
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        try:
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.executescript(Path(self.schema_path).read_text(encoding="utf-8"))
            self._apply_migrations(conn)
            conn.commit()
        except Exception as exc:
            conn.close()
            raise SchemaMigrationError("SQLite schema migration failed") from exc
        self._conn = conn

    def _apply_migrations(self, conn: sqlite3.Connection) -> None:
        migration_dir = Path(__file__).with_name("migrations")
        for version, filename in (
            (2, "002_results_v2.sql"),
            (3, "003_evidence_result_payload.sql"),
        ):
            if conn.execute(
                "SELECT 1 FROM schema_migrations WHERE version = ?", (version,)
            ).fetchone():
                continue
            migration = migration_dir / filename
            try:
                conn.executescript(
                    "BEGIN;\n" + migration.read_text(encoding="utf-8")
                    + f"\nINSERT INTO schema_migrations (version, applied_at) "
                    f"VALUES ({version}, CURRENT_TIMESTAMP);\nCOMMIT;"
                )
            except Exception:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise

    async def write_result(self, result: Result) -> None:
        if isinstance(result, ResultDraft) or not isinstance(result, Result):
            raise TypeError("write_result requires a finalized Result")
        if result.schema_version == "2.0" and (
            result.mechanism_id is not None
            or result.evidence.canonical_json != "{}"
            or result.source_observation_ids
            or result.source_ids
            or result.quality_snapshot != EvidenceQuality()
            or result.visibility_snapshot != VisibilityProfile()
            or result.state_version is not None
            or result.config_hash is not None
            or result.parser_refs
            or result.model_refs
        ):
            raise ResultIdentityConflict("v3 evidence/provenance cannot be hidden in a v2 identity")
        if result.result_id != result_id_for(result):
            raise ResultIdentityConflict("result_id does not match canonical result content")
        async with self._lock:
            self._write_result_sync(result)

    def _write_result_sync(self, result: Result) -> None:
        conn = self._require_connection()
        content_hash = hashlib.sha256(canonical_result_content(result).encode()).hexdigest()
        conn.execute("BEGIN")
        try:
            cursor = conn.cursor()
            existing = cursor.execute("SELECT content_hash FROM results WHERE result_id = ?", (result.result_id,)).fetchone()
            if existing is not None:
                if existing[0] == content_hash:
                    conn.execute("COMMIT")
                    return
                raise ResultIdentityConflict(f"result_id {result.result_id!r} already has different or unverifiable content")
            interval_start, interval_end = result.evidence_interval or (None, None)
            cursor.execute("""INSERT INTO results (
                result_id, content_hash, schema_version, result_type, created_time,
                lane_id, plugin_id, plugin_version, analytic_version, governance_version,
                entity_reference, taxonomy_1, taxonomy_2, taxonomy_3,
                scientific_status, integration_status, readiness, quality_degraded,
                claim_ceiling, confidence, severity, reason_code, evidence_interval_start,
                evidence_interval_end, mechanism_id, evidence_json, quality_snapshot_json,
                visibility_snapshot_json, state_version, config_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (result.result_id, content_hash, result.schema_version, result.result_type.value, _time_text(result.created_time),
                 result.lane_id, result.plugin_id, result.plugin_version, result.analytic_version, result.governance_version,
                 result.entity_reference, *result.taxonomy, result.status_snapshot.scientific_status.value,
                 result.status_snapshot.integration_status.value, result.status_snapshot.readiness.value,
                 int(result.status_snapshot.quality_degraded), result.claim_ceiling, getattr(result, "confidence", None),
                 getattr(result, "severity", None), result.reason_code.value if isinstance(result, AnalyticUnavailable) else None,
                 _time_text(interval_start) if interval_start else None, _time_text(interval_end) if interval_end else None,
                 result.mechanism_id, result.evidence.canonical_json,
                 _quality_json(result.quality_snapshot), _visibility_json(result.visibility_snapshot),
                 result.state_version, result.config_hash))
            self._insert_children(cursor, result)
            conn.execute("COMMIT")
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise

    @staticmethod
    def _insert_children(cursor: sqlite3.Cursor, result: Result) -> None:
        for table, column, values in (
            ("evidence_items", "evidence_ref", result.evidence_items),
            ("provenance_references", "provenance_ref", result.provenance_refs),
            ("quality_references", "quality_ref", result.quality_refs),
            ("governing_references", "governing_id", result.governing_ids),
            ("missing_prerequisites", "prerequisite", result.missing_prerequisites),
            ("source_observation_ids", "source_observation_id", result.source_observation_ids),
            ("result_source_ids", "source_id", result.source_ids),
            ("parser_references", "parser_ref", result.parser_refs),
            ("model_references", "model_ref", result.model_refs),
        ):
            for position, value in enumerate(values):
                cursor.execute(f"INSERT INTO {table} (result_id, {column}, position) VALUES (?, ?, ?)", (result.result_id, value, position))
        if isinstance(result, CorrelationFinding):
            for position, linked_id in enumerate(result.linked_result_ids):
                cursor.execute("INSERT INTO result_links (source_result_id, linked_result_id, position) VALUES (?, ?, ?)", (result.result_id, linked_id, position))

    async def get_result(self, result_id: str) -> Result | None:
        async with self._lock:
            conn = self._require_connection()
            row = conn.execute("SELECT * FROM results WHERE result_id = ?", (result_id,)).fetchone()
            return None if row is None else self._read_result(conn, row)

    async def list_results(self, *, limit: int = 100, cursor: str | None = None, lane_id: str | None = None, result_type: ResultType | None = None) -> tuple[Result, ...]:
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        clauses, params = ["content_hash IS NOT NULL"], []
        if cursor:
            created_time, result_id = self._decode_cursor(cursor)
            clauses.append("(created_time < ? OR (created_time = ? AND result_id < ?))")
            params.extend((created_time, created_time, result_id))
        if lane_id:
            clauses.append("lane_id = ?"); params.append(lane_id)
        if result_type:
            clauses.append("result_type = ?"); params.append(result_type.value)
        params.append(limit)
        sql = "SELECT * FROM results WHERE " + " AND ".join(clauses) + " ORDER BY created_time DESC, result_id DESC LIMIT ?"
        async with self._lock:
            conn = self._require_connection()
            return tuple(self._read_result(conn, row) for row in conn.execute(sql, params).fetchall())

    @staticmethod
    def cursor_for(result: Result) -> str:
        return base64.urlsafe_b64encode(f"{_time_text(result.created_time)}\0{result.result_id}".encode()).decode()

    @staticmethod
    def _decode_cursor(cursor: str) -> tuple[str, str]:
        try:
            return tuple(base64.urlsafe_b64decode(cursor.encode()).decode().split("\0", 1))  # type: ignore[return-value]
        except Exception as exc:
            raise ValueError("invalid result cursor") from exc

    def _read_result(self, conn: sqlite3.Connection, row: tuple) -> Result:
        columns = [item[0] for item in conn.execute("SELECT * FROM results LIMIT 0").description]
        values = dict(zip(columns, row))
        if values["content_hash"] is None:
            raise PersistenceError("legacy v1 result cannot be reconstructed as a v2 Result")
        result_id = values["result_id"]
        def children(table: str, column: str, id_column: str = "result_id") -> tuple[str, ...]:
            return tuple(item[0] for item in conn.execute(f"SELECT {column} FROM {table} WHERE {id_column} = ? ORDER BY position", (result_id,)))
        status = ResultStatusSnapshot(ScientificStatus(values["scientific_status"]), IntegrationStatus(values["integration_status"]), values["governance_version"], EvidenceReadiness(values["readiness"]), bool(values["quality_degraded"]))
        interval = ((datetime.fromisoformat(values["evidence_interval_start"]), datetime.fromisoformat(values["evidence_interval_end"])) if values["evidence_interval_start"] else None)
        is_v3 = values["schema_version"] != "2.0"
        if is_v3:
            if not all(values[name] is not None for name in (
                "mechanism_id", "evidence_json", "quality_snapshot_json",
                "visibility_snapshot_json",
            )):
                raise PersistenceError("v3 result is missing required evidence/provenance fields")
            quality_value = json.loads(values["quality_snapshot_json"])
            quality_snapshot = EvidenceQuality(
                packet_loss=QualityState(quality_value["packet_loss"]),
                sampling=QualityState(quality_value["sampling"]),
                parser=QualityState(quality_value["parser"]),
                capture_gap=QualityState(quality_value["capture_gap"]),
            )
            visibility_value = json.loads(values["visibility_snapshot_json"])
            visibility_snapshot = VisibilityProfile(
                available=frozenset(VisibilityCapability(item) for item in visibility_value["available"]),
                unavailable=frozenset(VisibilityCapability(item) for item in visibility_value["unavailable"]),
                degraded=frozenset(VisibilityCapability(item) for item in visibility_value["degraded"]),
            )
        else:
            quality_snapshot = EvidenceQuality()
            visibility_snapshot = VisibilityProfile()
        common = dict(
            result_id=result_id, schema_version=values["schema_version"],
            result_type=ResultType(values["result_type"]),
            created_time=datetime.fromisoformat(values["created_time"]),
            lane_id=values["lane_id"], plugin_id=values["plugin_id"],
            plugin_version=values["plugin_version"],
            analytic_version=values["analytic_version"],
            governance_version=values["governance_version"],
            entity_reference=values["entity_reference"],
            taxonomy=(values["taxonomy_1"], values["taxonomy_2"], values["taxonomy_3"]),
            status_snapshot=status, claim_ceiling=values["claim_ceiling"],
            evidence_items=children("evidence_items", "evidence_ref"),
            provenance_refs=children("provenance_references", "provenance_ref"),
            quality_refs=children("quality_references", "quality_ref"),
            governing_ids=children("governing_references", "governing_id"),
            missing_prerequisites=children("missing_prerequisites", "prerequisite"),
            evidence_interval=interval,
            mechanism_id=values["mechanism_id"] if is_v3 else None,
            evidence=(EvidencePayload(values["evidence_json"])
                      if is_v3 else EvidencePayload("{}")),
            source_observation_ids=(children("source_observation_ids", "source_observation_id")
                                    if is_v3 else ()),
            source_ids=(children("result_source_ids", "source_id") if is_v3 else ()),
            quality_snapshot=quality_snapshot,
            visibility_snapshot=visibility_snapshot,
            state_version=values["state_version"] if is_v3 else None,
            config_hash=values["config_hash"] if is_v3 else None,
            parser_refs=(children("parser_references", "parser_ref") if is_v3 else ()),
            model_refs=(children("model_references", "model_ref") if is_v3 else ()),
        )
        if common["result_type"] is ResultType.THREAT_ALERT:
            return ThreatAlert(**common, confidence=values["confidence"], severity=values["severity"])
        if common["result_type"] is ResultType.ANALYTIC_UNAVAILABLE:
            return AnalyticUnavailable(**common, reason_code=AnalyticUnavailableReason(values["reason_code"]))
        if common["result_type"] is ResultType.CORRELATION_FINDING:
            return CorrelationFinding(**common, linked_result_ids=children("result_links", "linked_result_id", "source_result_id"))
        return _RESULT_CLASSES[common["result_type"]](**common)

    def _require_connection(self) -> sqlite3.Connection:
        if self._conn is None:
            raise PersistenceError("Database not connected. Call connect() first.")
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
