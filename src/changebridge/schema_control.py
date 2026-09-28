"""Durable schema decisions, quarantine barriers, and apply receipts."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any, NoReturn

from changebridge.schema_policy import SchemaDecision


class SchemaControlError(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


def _fail(code: str, detail: str) -> NoReturn:
    raise SchemaControlError(code, detail)


class SchemaControlStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode = WAL")
        self.connection.execute("PRAGMA synchronous = FULL")
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_decisions (
              decision_id TEXT PRIMARY KEY,
              decision_digest TEXT NOT NULL UNIQUE,
              generation_id TEXT NOT NULL,
              source_table TEXT NOT NULL,
              previous_digest TEXT NOT NULL,
              candidate_digest TEXT NOT NULL,
              policy_digest TEXT NOT NULL,
              verdict TEXT NOT NULL,
              decision_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS schema_quarantines (
              quarantine_id TEXT PRIMARY KEY,
              generation_id TEXT NOT NULL,
              source_table TEXT NOT NULL,
              decision_id TEXT NOT NULL REFERENCES schema_decisions(decision_id),
              frontier TEXT NOT NULL,
              target_metadata_location TEXT NOT NULL,
              status TEXT NOT NULL,
              reason_codes_json TEXT NOT NULL,
              UNIQUE(generation_id, source_table, decision_id)
            );
            CREATE TABLE IF NOT EXISTS schema_apply_receipts (
              receipt_id TEXT PRIMARY KEY,
              apply_token TEXT NOT NULL UNIQUE,
              generation_id TEXT NOT NULL,
              source_table TEXT NOT NULL,
              decision_id TEXT NOT NULL REFERENCES schema_decisions(decision_id),
              candidate_digest TEXT NOT NULL,
              policy_digest TEXT NOT NULL,
              iceberg_schema_id INTEGER NOT NULL,
              metadata_location TEXT NOT NULL,
              recovered INTEGER NOT NULL CHECK (recovered IN (0,1)),
              UNIQUE(generation_id, source_table, candidate_digest, policy_digest)
            );
            CREATE TABLE IF NOT EXISTS schema_generation_rejections (
              generation_id TEXT PRIMARY KEY,
              decision_id TEXT NOT NULL REFERENCES schema_decisions(decision_id),
              quarantine_id TEXT NOT NULL REFERENCES schema_quarantines(quarantine_id),
              predecessor_state TEXT NOT NULL,
              state TEXT NOT NULL CHECK (state='REJECTED'),
              revision INTEGER NOT NULL,
              rejection_digest TEXT NOT NULL UNIQUE
            );
            """
        )

    def __enter__(self) -> SchemaControlStore:
        return self

    def __exit__(self, *_: object) -> None:
        self.connection.close()

    def decision(self, decision_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM schema_decisions WHERE decision_id=?", (decision_id,)
        ).fetchone()
        return None if row is None else dict(row)

    def record_decision(self, decision: SchemaDecision) -> dict[str, Any]:
        value = decision.record()
        payload = json.dumps(value, sort_keys=True, separators=(",", ":"))
        existing = self.decision(decision.decision_id)
        if existing is not None:
            if (
                existing["decision_digest"] != decision.decision_digest
                or existing["decision_json"] != payload
            ):
                _fail("CB25C001_DECISION_CONFLICT", decision.decision_id)
            return existing
        with self.connection:
            self.connection.execute(
                "INSERT INTO schema_decisions VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    decision.decision_id,
                    decision.decision_digest,
                    decision.generation_id,
                    decision.source_table,
                    decision.previous.digest,
                    decision.candidate.digest,
                    decision.policy_digest,
                    decision.verdict,
                    payload,
                ),
            )
        result = self.decision(decision.decision_id)
        assert result is not None
        return result

    def open_quarantine(
        self,
        decision: SchemaDecision,
        *,
        frontier: str,
        target_metadata_location: str,
    ) -> dict[str, Any]:
        if decision.verdict == "COMPATIBLE":
            _fail("CB25C002_COMPATIBLE_QUARANTINE", decision.decision_id)
        quarantine_id = f"schema-quarantine-{decision.decision_digest[:24]}"
        existing = self.connection.execute(
            "SELECT * FROM schema_quarantines WHERE quarantine_id=?", (quarantine_id,)
        ).fetchone()
        reasons = json.dumps(decision.reason_codes, separators=(",", ":"))
        if existing is not None:
            result = dict(existing)
            if (
                result["decision_id"] != decision.decision_id
                or result["target_metadata_location"] != target_metadata_location
            ):
                _fail("CB25C003_QUARANTINE_CONFLICT", quarantine_id)
            return result
        with self.connection:
            self.connection.execute(
                "INSERT INTO schema_quarantines VALUES (?,?,?,?,?,?,?,?)",
                (
                    quarantine_id,
                    decision.generation_id,
                    decision.source_table,
                    decision.decision_id,
                    frontier,
                    target_metadata_location,
                    "OPEN",
                    reasons,
                ),
            )
        row = self.connection.execute(
            "SELECT * FROM schema_quarantines WHERE quarantine_id=?", (quarantine_id,)
        ).fetchone()
        assert row is not None
        return dict(row)

    def open_quarantines(self, generation_id: str) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT * FROM schema_quarantines WHERE generation_id=? AND status='OPEN' "
            "ORDER BY quarantine_id",
            (generation_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def reject_generation(
        self,
        decision: SchemaDecision,
        *,
        quarantine_id: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        if decision.verdict != "INCOMPATIBLE":
            _fail("CB25C007_REJECTION_REQUIRES_INCOMPATIBLE", decision.decision_id)
        from changebridge.contracts import semantic_digest

        material = {
            "generation_id": decision.generation_id,
            "decision_id": decision.decision_id,
            "decision_digest": decision.decision_digest,
            "quarantine_id": quarantine_id,
            "predecessor_state": "CDC_APPLYING",
            "state": "REJECTED",
            "revision": expected_revision + 1,
        }
        digest = semantic_digest(material, domain="stage25-generation-rejection")
        existing = self.connection.execute(
            "SELECT * FROM schema_generation_rejections WHERE generation_id=?",
            (decision.generation_id,),
        ).fetchone()
        if existing is not None:
            result = dict(existing)
            if result["rejection_digest"] != digest:
                _fail("CB25C008_GENERATION_REJECTION_CONFLICT", decision.generation_id)
            return result
        with self.connection:
            self.connection.execute(
                "INSERT INTO schema_generation_rejections VALUES (?,?,?,?,?,?,?)",
                (
                    decision.generation_id,
                    decision.decision_id,
                    quarantine_id,
                    "CDC_APPLYING",
                    "REJECTED",
                    expected_revision + 1,
                    digest,
                ),
            )
        row = self.connection.execute(
            "SELECT * FROM schema_generation_rejections WHERE generation_id=?",
            (decision.generation_id,),
        ).fetchone()
        assert row is not None
        return dict(row)

    def receipt_for_token(self, token: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM schema_apply_receipts WHERE apply_token=?", (token,)
        ).fetchone()
        return None if row is None else dict(row)

    def record_apply_receipt(self, receipt: Mapping[str, Any]) -> dict[str, Any]:
        token = str(receipt["apply_token"])
        existing = self.receipt_for_token(token)
        keys = (
            "receipt_id",
            "apply_token",
            "generation_id",
            "source_table",
            "decision_id",
            "candidate_digest",
            "policy_digest",
            "iceberg_schema_id",
            "metadata_location",
            "recovered",
        )
        values = tuple(receipt[key] for key in keys)
        if existing is not None:
            immutable = tuple(key for key in keys if key != "recovered")
            if any(str(existing[key]) != str(receipt[key]) for key in immutable):
                _fail("CB25C004_RECEIPT_CONFLICT", token)
            return existing
        with self.connection:
            columns = ",".join(keys)
            placeholders = ",".join("?" for _ in keys)
            self.connection.execute(
                f"INSERT INTO schema_apply_receipts({columns}) VALUES ({placeholders})",
                values,
            )
        result = self.receipt_for_token(token)
        assert result is not None
        return result

    def require_admission(
        self,
        *,
        generation_id: str,
        source_table: str,
        candidate_digest: str,
        policy_digest: str,
    ) -> dict[str, Any]:
        rejection = self.connection.execute(
            "SELECT state FROM schema_generation_rejections WHERE generation_id=?",
            (generation_id,),
        ).fetchone()
        if rejection is not None:
            _fail("CB25C009_GENERATION_REJECTED", generation_id)
        if self.open_quarantines(generation_id):
            _fail("CB25C005_GENERATION_QUARANTINED", generation_id)
        row = self.connection.execute(
            """SELECT r.* FROM schema_apply_receipts r
               JOIN schema_decisions d ON d.decision_id=r.decision_id
              WHERE r.generation_id=? AND r.source_table=? AND r.candidate_digest=?
                AND r.policy_digest=? AND d.verdict='COMPATIBLE'""",
            (generation_id, source_table, candidate_digest, policy_digest),
        ).fetchone()
        if row is None:
            _fail("CB25C006_ADMISSION_REQUIRED", f"{generation_id}:{source_table}")
        return dict(row)
