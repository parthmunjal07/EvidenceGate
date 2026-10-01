"""SQLite repository for immutable, finalized EvidenceGate results."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from evidencegate.correlation.contracts import (
    FACT_DERIVATION_VERSION,
    CorrelationCandidate,
    CorrelationFactSeed,
    EventInterval,
    EventTimeBasis,
    MatchedFact,
    MatchedReason,
)
from evidencegate.correlation.engine import (
    ResultCorrelationContext,
    candidate_for_exact_observation,
    exact_observation_fact,
    merge_candidates,
)
from evidencegate.domain.enums import (
    AnalyticUnavailableReason,
    EvidenceReadiness,
    IntegrationStatus,
    QualityState,
    ResultType,
    ScientificStatus,
    VisibilityCapability,
)
from evidencegate.domain.events import VisibilityProfile
from evidencegate.domain.quality import EvidenceQuality
from evidencegate.persistence.correlation_codec import (
    candidate_from_row,
    candidate_values,
    event_interval_from_values,
    fact_values,
    quality_from_json,
    visibility_from_json,
)
from evidencegate.results.finalizer import canonical_result_content, result_id_for
from evidencegate.results.types import (
    AnalyticUnavailable,
    CorrelationFinding,
    EvidencePayload,
    InsufficientEvidence,
    PluginStatus,
    PrerequisiteMissing,
    QualityDegraded,
    Result,
    ResultDraft,
    ResultStatusSnapshot,
    ReviewFinding,
    ThreatAlert,
)


class PersistenceError(RuntimeError):
    """Base class for repository-level persistence failures."""


class ResultIdentityConflict(PersistenceError):
    """A result ID is already associated with unverifiable or different content."""


class SchemaMigrationError(PersistenceError):
    """The database could not be brought to the supported schema version."""


_RESULT_CLASSES = {
    ResultType.THREAT_ALERT: ThreatAlert,
    ResultType.REVIEW_FINDING: ReviewFinding,
    ResultType.ANALYTIC_UNAVAILABLE: AnalyticUnavailable,
    ResultType.PREREQUISITE_MISSING: PrerequisiteMissing,
    ResultType.INSUFFICIENT_EVIDENCE: InsufficientEvidence,
    ResultType.QUALITY_DEGRADED: QualityDegraded,
    ResultType.PLUGIN_STATUS: PluginStatus,
    ResultType.CORRELATION_FINDING: CorrelationFinding,
}


def _time_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise PersistenceError("result datetimes must be timezone-aware")
    return value.isoformat(timespec="microseconds")


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _quality_json(value: EvidenceQuality) -> str:
    return _canonical_json(
        {
            "packet_loss": value.packet_loss.value,
            "sampling": value.sampling.value,
            "parser": value.parser.value,
            "capture_gap": value.capture_gap.value,
        }
    )


def _visibility_json(value: VisibilityProfile) -> str:
    return _canonical_json(
        {
            "available": sorted(item.value for item in value.available),
            "unavailable": sorted(item.value for item in value.unavailable),
            "degraded": sorted(item.value for item in value.degraded),
        }
    )


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
            (4, "004_correlation_foundation.sql"),
        ):
            if conn.execute(
                "SELECT 1 FROM schema_migrations WHERE version = ?", (version,)
            ).fetchone():
                continue
            migration = migration_dir / filename
            try:
                conn.executescript(
                    "BEGIN;\n"
                    + migration.read_text(encoding="utf-8")
                    + f"\nINSERT INTO schema_migrations (version, applied_at) "
                    f"VALUES ({version}, CURRENT_TIMESTAMP);\nCOMMIT;"
                )
            except Exception:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise

    async def write_result(self, result: Result) -> bool:
        """Persist a finalized result and report whether a new row was inserted."""
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
            return self._write_result_sync(result)

    def _write_result_sync(self, result: Result) -> bool:
        conn = self._require_connection()
        content_hash = hashlib.sha256(canonical_result_content(result).encode()).hexdigest()
        conn.execute("BEGIN")
        try:
            cursor = conn.cursor()
            existing = cursor.execute(
                "SELECT content_hash FROM results WHERE result_id = ?", (result.result_id,)
            ).fetchone()
            if existing is not None:
                if existing[0] == content_hash:
                    cursor.execute(
                        """INSERT OR IGNORE INTO correlation_outbox
                           (source_result_id, source_result_hash, derivation_version, status)
                           VALUES (?, ?, ?, 'PENDING')""",
                        (result.result_id, content_hash, FACT_DERIVATION_VERSION),
                    )
                    conn.execute("COMMIT")
                    return False
                raise ResultIdentityConflict(
                    f"result_id {result.result_id!r} already has different or unverifiable content"
                )
            interval_start, interval_end = result.evidence_interval or (None, None)
            cursor.execute(
                """INSERT INTO results (
                result_id, content_hash, schema_version, result_type, created_time,
                lane_id, plugin_id, plugin_version, analytic_version, governance_version,
                entity_reference, taxonomy_1, taxonomy_2, taxonomy_3,
                scientific_status, integration_status, readiness, quality_degraded,
                claim_ceiling, confidence, severity, reason_code, evidence_interval_start,
                evidence_interval_end, mechanism_id, evidence_json, quality_snapshot_json,
                visibility_snapshot_json, state_version, config_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    result.result_id,
                    content_hash,
                    result.schema_version,
                    result.result_type.value,
                    _time_text(result.created_time),
                    result.lane_id,
                    result.plugin_id,
                    result.plugin_version,
                    result.analytic_version,
                    result.governance_version,
                    result.entity_reference,
                    *result.taxonomy,
                    result.status_snapshot.scientific_status.value,
                    result.status_snapshot.integration_status.value,
                    result.status_snapshot.readiness.value,
                    int(result.status_snapshot.quality_degraded),
                    result.claim_ceiling,
                    getattr(result, "confidence", None),
                    getattr(result, "severity", None),
                    result.reason_code.value if isinstance(result, AnalyticUnavailable) else None,
                    _time_text(interval_start) if interval_start else None,
                    _time_text(interval_end) if interval_end else None,
                    result.mechanism_id,
                    result.evidence.canonical_json,
                    _quality_json(result.quality_snapshot),
                    _visibility_json(result.visibility_snapshot),
                    result.state_version,
                    result.config_hash,
                ),
            )
            self._insert_children(cursor, result)
            cursor.execute(
                """INSERT OR IGNORE INTO correlation_outbox
                   (source_result_id, source_result_hash, derivation_version, status)
                   VALUES (?, ?, ?, 'PENDING')""",
                (result.result_id, content_hash, FACT_DERIVATION_VERSION),
            )
            conn.execute("COMMIT")
            return True
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise

    async def process_correlation_outbox_batch(self, *, limit: int = 1) -> int:
        """Atomically materialize one bounded batch of durable correlation work."""
        if not 1 <= limit <= 500:
            raise ValueError("correlation outbox batch limit must be between 1 and 500")
        async with self._lock:
            conn = self._require_connection()
            operation = asyncio.create_task(
                asyncio.to_thread(self._process_correlation_outbox_batch_sync, conn, limit)
            )
            try:
                return await asyncio.shield(operation)
            except asyncio.CancelledError:
                try:
                    await operation
                except Exception:
                    pass
                raise

    def _process_correlation_outbox_batch_sync(self, conn: sqlite3.Connection, limit: int) -> int:
        conn.execute("BEGIN")
        try:
            outbox = conn.execute(
                """SELECT outbox_id, source_result_id, source_result_hash, derivation_version
                   FROM correlation_outbox WHERE status = 'PENDING'
                   ORDER BY outbox_id LIMIT ?""",
                (limit,),
            ).fetchall()
            if not outbox:
                conn.execute("COMMIT")
                return 0

            result_ids = tuple(dict.fromkeys(row[1] for row in outbox))
            placeholders = ",".join("?" for _ in result_ids)
            source_rows = conn.execute(
                f"""SELECT result_id, content_hash, lane_id, created_time,
                          evidence_interval_start, evidence_interval_end,
                          quality_snapshot_json, visibility_snapshot_json
                   FROM results WHERE result_id IN ({placeholders})""",
                result_ids,
            ).fetchall()
            source_by_id = {row[0]: self._correlation_context_row(row) for row in source_rows}
            for row in outbox:
                context = source_by_id.get(row[1])
                if context is None or context.source_result_hash != row[2]:
                    raise ResultIdentityConflict(
                        "correlation outbox source Result/hash is missing or inconsistent"
                    )
                if row[3] != FACT_DERIVATION_VERSION:
                    raise PersistenceError("unsupported correlation outbox derivation version")

            obs_rows = conn.execute(
                f"""SELECT result_id, source_observation_id
                   FROM source_observation_ids WHERE result_id IN ({placeholders})
                   ORDER BY result_id, position""",
                result_ids,
            ).fetchall()
            observations_by_result: dict[str, list[str]] = {
                result_id: [] for result_id in result_ids
            }
            for result_id, observation_id in obs_rows:
                observations_by_result[result_id].append(observation_id)

            provenance_by_result = self._provenance_for_results(conn, result_ids)
            contexts = {
                result_id: ResultCorrelationContext(
                    result_id=context.result_id,
                    source_result_hash=context.source_result_hash,
                    lane_id=context.lane_id,
                    event_interval=context.event_interval,
                    visibility=context.visibility,
                    quality=context.quality,
                    source_provenance=provenance_by_result.get(result_id, ()),
                )
                for result_id, context in source_by_id.items()
            }

            for outbox_id, source_result_id, source_hash, _ in outbox:
                context = contexts[source_result_id]
                facts = tuple(
                    exact_observation_fact(context, observation_id)
                    for observation_id in observations_by_result[source_result_id]
                )
                for fact in facts:
                    conn.execute(
                        """INSERT OR IGNORE INTO correlation_facts (
                            fact_id, source_result_id, source_result_hash, fact_kind,
                            normalized_value, namespace, scope, role, identity_basis,
                            event_interval_start, event_interval_end, event_time_basis,
                            available_time, source_observation_ids, visibility_basis,
                            quality_basis, source_fields, derivation_basis,
                            normalizer_version, derivation_version
                        ) VALUES ("""
                        + ",".join("?" for _ in fact_values(fact))
                        + ")",
                        fact_values(fact),
                    )

                matched_rows = self._find_matching_facts(conn, facts)
                peer_ids = tuple(
                    sorted(
                        {
                            str(row["source_result_id"])
                            for row in matched_rows
                            if row["source_result_id"] != source_result_id
                        }
                    )
                )
                peer_provenance = self._provenance_for_results(conn, peer_ids)
                matched_by_peer: dict[str, list[MatchedFact]] = {}
                fact_by_value = {fact.normalized_value: fact for fact in facts}
                for row in matched_rows:
                    peer_id = str(row["source_result_id"])
                    if peer_id == source_result_id:
                        continue
                    current_fact = fact_by_value.get(str(row["normalized_value"]))
                    if current_fact is None:
                        continue
                    if str(row["actual_result_hash"]) != str(row["source_result_hash"]):
                        raise ResultIdentityConflict(
                            "indexed correlation fact hash is inconsistent"
                        )
                    matched_by_peer.setdefault(peer_id, []).append(
                        MatchedFact(
                            reason=MatchedReason.EXACT_SHARED_SOURCE_OBSERVATION,
                            fact_kind=current_fact.fact_kind,
                            normalized_value=current_fact.normalized_value,
                            left_fact_id=current_fact.fact_id,
                            right_fact_id=str(row["fact_id"]),
                            source_observation_id=current_fact.normalized_value,
                        )
                    )

                additions: dict[str, CorrelationCandidate] = {}
                peer_contexts: dict[str, ResultCorrelationContext] = {}
                for row in matched_rows:
                    peer_id = str(row["source_result_id"])
                    if peer_id == source_result_id or peer_id in peer_contexts:
                        continue
                    peer_contexts[peer_id] = ResultCorrelationContext(
                        result_id=peer_id,
                        source_result_hash=str(row["source_result_hash"]),
                        lane_id=str(row["lane_id"]),
                        event_interval=event_interval_from_values(
                            str(row["event_interval_start"]),
                            str(row["event_interval_end"]),
                            str(row["event_time_basis"]),
                        ),
                        visibility=visibility_from_json(str(row["visibility_basis"])),
                        quality=quality_from_json(str(row["quality_basis"])),
                        source_provenance=peer_provenance.get(peer_id, ()),
                    )
                for peer_id, reasons in matched_by_peer.items():
                    candidate = candidate_for_exact_observation(
                        context, peer_contexts[peer_id], tuple(reasons)
                    )
                    if candidate is not None:
                        additions[candidate.pair_id] = candidate

                self._merge_and_write_candidates(conn, additions)
                conn.execute(
                    """UPDATE correlation_outbox
                       SET status = 'COMPLETED', completed_at = CURRENT_TIMESTAMP
                       WHERE outbox_id = ? AND status = 'PENDING'""",
                    (outbox_id,),
                )

            conn.execute("COMMIT")
            return len(outbox)
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise

    @staticmethod
    def _correlation_context_row(row: tuple) -> ResultCorrelationContext:
        (
            result_id,
            source_hash,
            lane_id,
            created_time,
            interval_start,
            interval_end,
            quality_json,
            visibility_json,
        ) = row
        if interval_start is not None:
            interval = event_interval_from_values(
                interval_start, interval_end, EventTimeBasis.EVIDENCE_INTERVAL.value
            )
        else:
            interval = EventInterval(
                datetime.fromisoformat(created_time),
                datetime.fromisoformat(created_time),
                EventTimeBasis.RESULT_EVENT_TIME,
            )
        return ResultCorrelationContext(
            result_id=result_id,
            source_result_hash=source_hash,
            lane_id=lane_id,
            event_interval=interval,
            quality=quality_from_json(quality_json) if quality_json else EvidenceQuality(),
            visibility=(
                visibility_from_json(visibility_json) if visibility_json else VisibilityProfile()
            ),
            source_provenance=(),
        )

    @staticmethod
    def _provenance_for_results(
        conn: sqlite3.Connection, result_ids: tuple[str, ...]
    ) -> dict[str, tuple[str, ...]]:
        values: dict[str, list[str]] = {}
        for start in range(0, len(result_ids), 400):
            chunk = result_ids[start : start + 400]
            placeholders = ",".join("?" for _ in chunk)
            rows = conn.execute(
                f"""SELECT result_id, provenance_ref FROM provenance_references
                    WHERE result_id IN ({placeholders}) ORDER BY result_id, position""",
                chunk,
            ).fetchall()
            for result_id, provenance_ref in rows:
                values.setdefault(result_id, []).append(provenance_ref)
        return {result_id: tuple(items) for result_id, items in values.items()}

    @staticmethod
    def _find_matching_facts(
        conn: sqlite3.Connection, facts: tuple[CorrelationFactSeed, ...]
    ) -> list[dict[str, object]]:
        values = tuple(dict.fromkeys(fact.normalized_value for fact in facts))
        matches: list[dict[str, object]] = []
        for start in range(0, len(values), 400):
            chunk = values[start : start + 400]
            if not chunk:
                continue
            placeholders = ",".join("?" for _ in chunk)
            cursor = conn.execute(
                f"""SELECT f.fact_id, f.source_result_id, f.source_result_hash,
                          f.fact_kind, f.normalized_value, f.namespace, f.scope, f.role,
                          f.identity_basis, f.event_interval_start, f.event_interval_end,
                          f.event_time_basis, f.available_time, f.source_observation_ids,
                          f.visibility_basis, f.quality_basis, f.source_fields,
                          f.derivation_basis, f.normalizer_version, f.derivation_version,
                          r.lane_id, r.content_hash AS actual_result_hash
                   FROM correlation_facts f JOIN results r ON r.result_id = f.source_result_id
                   WHERE f.fact_kind = 'EXACT_OBSERVATION'
                     AND f.namespace = 'evidencegate.source_observation'
                     AND f.scope = 'source_observation_id' AND f.role = 'observed'
                     AND f.normalized_value IN ({placeholders})
                   ORDER BY f.normalized_value, f.source_result_id, f.fact_id""",
                chunk,
            )
            columns = [item[0] for item in cursor.description]
            matches.extend(dict(zip(columns, row)) for row in cursor.fetchall())
        return matches

    @staticmethod
    def _merge_and_write_candidates(
        conn: sqlite3.Connection, additions: dict[str, CorrelationCandidate]
    ) -> None:
        if not additions:
            return
        ids = tuple(sorted(additions))
        existing: dict[str, CorrelationCandidate] = {}
        for start in range(0, len(ids), 400):
            chunk = ids[start : start + 400]
            placeholders = ",".join("?" for _ in chunk)
            cursor = conn.execute(
                f"SELECT * FROM correlation_candidates WHERE pair_id IN ({placeholders})", chunk
            )
            columns = [item[0] for item in cursor.description]
            existing.update(
                {row[0]: candidate_from_row(dict(zip(columns, row))) for row in cursor.fetchall()}
            )
        values = []
        for pair_id in ids:
            candidate = additions[pair_id]
            if pair_id in existing:
                candidate = merge_candidates(existing[pair_id], candidate)
            values.append(candidate_values(candidate))
        placeholders = ",".join("?" for _ in values[0])
        conn.executemany(
            """INSERT INTO correlation_candidates (
                pair_id, left_result_id, right_result_id, left_source_result_hash,
                right_source_result_hash, relation_policy, relation_policy_version,
                matched_reasons, matched_fact_ids, source_observation_ids,
                left_event_interval_start, left_event_interval_end, left_event_time_basis,
                right_event_interval_start, right_event_interval_end, right_event_time_basis,
                event_time_relationship, left_visibility, right_visibility, left_quality,
                right_quality, left_source_provenance, right_source_provenance, status,
                claim_guard
            ) VALUES ("""
            + placeholders
            + ") ON CONFLICT(pair_id) DO UPDATE SET matched_reasons=excluded.matched_reasons, "
            + "matched_fact_ids=excluded.matched_fact_ids, "
            + "source_observation_ids=excluded.source_observation_ids",
            values,
        )

    async def list_correlation_candidates(
        self, *, limit: int = 100, source_result_id: str | None = None
    ) -> tuple[CorrelationCandidate, ...]:
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        async with self._lock:
            conn = self._require_connection()
            if source_result_id is None:
                rows = conn.execute(
                    "SELECT * FROM correlation_candidates ORDER BY pair_id LIMIT ?", (limit,)
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM correlation_candidates
                       WHERE left_result_id = ? OR right_result_id = ?
                       ORDER BY pair_id LIMIT ?""",
                    (source_result_id, source_result_id, limit),
                ).fetchall()
            cursor = conn.execute("SELECT * FROM correlation_candidates LIMIT 0")
            columns = [item[0] for item in cursor.description]
            return tuple(candidate_from_row(dict(zip(columns, row))) for row in rows)

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
                cursor.execute(
                    f"INSERT INTO {table} (result_id, {column}, position) VALUES (?, ?, ?)",
                    (result.result_id, value, position),
                )
        if isinstance(result, CorrelationFinding):
            for position, linked_id in enumerate(result.linked_result_ids):
                cursor.execute(
                    "INSERT INTO result_links (source_result_id, linked_result_id, position) VALUES (?, ?, ?)",
                    (result.result_id, linked_id, position),
                )

    async def get_result(self, result_id: str) -> Result | None:
        async with self._lock:
            conn = self._require_connection()
            row = conn.execute("SELECT * FROM results WHERE result_id = ?", (result_id,)).fetchone()
            return None if row is None else self._read_result(conn, row)

    async def list_results(
        self,
        *,
        limit: int = 100,
        cursor: str | None = None,
        lane_id: str | None = None,
        mechanism_id: str | None = None,
        result_type: ResultType | None = None,
        source_id: str | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        direction: str = "before",
    ) -> tuple[Result, ...]:
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        if direction not in {"before", "after"}:
            raise ValueError("direction must be 'before' or 'after'")
        for name, value in (("created_after", created_after), ("created_before", created_before)):
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise ValueError(f"{name} must be timezone-aware")
        clauses, params = ["content_hash IS NOT NULL"], []
        if cursor:
            created_time, result_id = self._decode_cursor(cursor)
            operator = "<" if direction == "before" else ">"
            clauses.append(
                f"(created_time {operator} ? OR (created_time = ? AND result_id {operator} ?))"
            )
            params.extend((created_time, created_time, result_id))
        if lane_id:
            clauses.append("lane_id = ?")
            params.append(lane_id)
        if mechanism_id:
            clauses.append("mechanism_id = ?")
            params.append(mechanism_id)
        if result_type:
            clauses.append("result_type = ?")
            params.append(result_type.value)
        if source_id:
            clauses.append(
                "EXISTS (SELECT 1 FROM result_source_ids source_filter "
                "WHERE source_filter.result_id = results.result_id "
                "AND source_filter.source_id = ?)"
            )
            params.append(source_id)
        if created_after is not None:
            clauses.append("created_time > ?")
            params.append(_time_text(created_after))
        if created_before is not None:
            clauses.append("created_time < ?")
            params.append(_time_text(created_before))
        params.append(limit)
        order = "DESC" if direction == "before" else "ASC"
        sql = (
            "SELECT * FROM results WHERE "
            + " AND ".join(clauses)
            + f" ORDER BY created_time {order}, result_id {order} LIMIT ?"
        )
        async with self._lock:
            conn = self._require_connection()
            # A bounded page can require hundreds of child-row reconstructions.
            # Keep its connection lock, but leave the event loop free for ingest.
            return await asyncio.to_thread(
                lambda: tuple(
                    self._read_result(conn, row) for row in conn.execute(sql, params).fetchall()
                )
            )

    @staticmethod
    def cursor_for(result: Result) -> str:
        return base64.urlsafe_b64encode(
            f"{_time_text(result.created_time)}\0{result.result_id}".encode()
        ).decode()

    @staticmethod
    def _decode_cursor(cursor: str) -> tuple[str, str]:
        try:
            decoded = base64.b64decode(cursor.encode(), altchars=b"-_", validate=True).decode()
            created_time, result_id = decoded.split("\0", 1)
            parsed = datetime.fromisoformat(created_time)
            if parsed.tzinfo is None or parsed.utcoffset() is None or not result_id:
                raise ValueError
            return created_time, result_id
        except Exception as exc:
            raise ValueError("invalid result cursor") from exc

    async def count_results(self) -> int:
        async with self._lock:
            conn = self._require_connection()
            return int(
                conn.execute(
                    "SELECT COUNT(*) FROM results WHERE content_hash IS NOT NULL"
                ).fetchone()[0]
            )

    def _read_result(self, conn: sqlite3.Connection, row: tuple) -> Result:
        columns = [item[0] for item in conn.execute("SELECT * FROM results LIMIT 0").description]
        values = dict(zip(columns, row))
        if values["content_hash"] is None:
            raise PersistenceError("legacy v1 result cannot be reconstructed as a v2 Result")
        result_id = values["result_id"]

        def children(table: str, column: str, id_column: str = "result_id") -> tuple[str, ...]:
            return tuple(
                item[0]
                for item in conn.execute(
                    f"SELECT {column} FROM {table} WHERE {id_column} = ? ORDER BY position",
                    (result_id,),
                )
            )

        status = ResultStatusSnapshot(
            ScientificStatus(values["scientific_status"]),
            IntegrationStatus(values["integration_status"]),
            values["governance_version"],
            EvidenceReadiness(values["readiness"]),
            bool(values["quality_degraded"]),
        )
        interval = (
            (
                datetime.fromisoformat(values["evidence_interval_start"]),
                datetime.fromisoformat(values["evidence_interval_end"]),
            )
            if values["evidence_interval_start"]
            else None
        )
        is_v3 = values["schema_version"] != "2.0"
        if is_v3:
            if not all(
                values[name] is not None
                for name in (
                    "mechanism_id",
                    "evidence_json",
                    "quality_snapshot_json",
                    "visibility_snapshot_json",
                )
            ):
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
                available=frozenset(
                    VisibilityCapability(item) for item in visibility_value["available"]
                ),
                unavailable=frozenset(
                    VisibilityCapability(item) for item in visibility_value["unavailable"]
                ),
                degraded=frozenset(
                    VisibilityCapability(item) for item in visibility_value["degraded"]
                ),
            )
        else:
            quality_snapshot = EvidenceQuality()
            visibility_snapshot = VisibilityProfile()
        common = dict(
            result_id=result_id,
            schema_version=values["schema_version"],
            result_type=ResultType(values["result_type"]),
            created_time=datetime.fromisoformat(values["created_time"]),
            lane_id=values["lane_id"],
            plugin_id=values["plugin_id"],
            plugin_version=values["plugin_version"],
            analytic_version=values["analytic_version"],
            governance_version=values["governance_version"],
            entity_reference=values["entity_reference"],
            taxonomy=(values["taxonomy_1"], values["taxonomy_2"], values["taxonomy_3"]),
            status_snapshot=status,
            claim_ceiling=values["claim_ceiling"],
            evidence_items=children("evidence_items", "evidence_ref"),
            provenance_refs=children("provenance_references", "provenance_ref"),
            quality_refs=children("quality_references", "quality_ref"),
            governing_ids=children("governing_references", "governing_id"),
            missing_prerequisites=children("missing_prerequisites", "prerequisite"),
            evidence_interval=interval,
            mechanism_id=values["mechanism_id"] if is_v3 else None,
            evidence=(EvidencePayload(values["evidence_json"]) if is_v3 else EvidencePayload("{}")),
            source_observation_ids=(
                children("source_observation_ids", "source_observation_id") if is_v3 else ()
            ),
            source_ids=(children("result_source_ids", "source_id") if is_v3 else ()),
            quality_snapshot=quality_snapshot,
            visibility_snapshot=visibility_snapshot,
            state_version=values["state_version"] if is_v3 else None,
            config_hash=values["config_hash"] if is_v3 else None,
            parser_refs=(children("parser_references", "parser_ref") if is_v3 else ()),
            model_refs=(children("model_references", "model_ref") if is_v3 else ()),
        )
        if common["result_type"] is ResultType.THREAT_ALERT:
            return ThreatAlert(
                **common, confidence=values["confidence"], severity=values["severity"]
            )
        if common["result_type"] is ResultType.ANALYTIC_UNAVAILABLE:
            return AnalyticUnavailable(
                **common, reason_code=AnalyticUnavailableReason(values["reason_code"])
            )
        if common["result_type"] is ResultType.CORRELATION_FINDING:
            return CorrelationFinding(
                **common,
                linked_result_ids=children("result_links", "linked_result_id", "source_result_id"),
            )
        return _RESULT_CLASSES[common["result_type"]](**common)

    def _require_connection(self) -> sqlite3.Connection:
        if self._conn is None:
            raise PersistenceError("Database not connected. Call connect() first.")
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
