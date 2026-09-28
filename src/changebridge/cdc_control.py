"""Durable Stage 4 transaction, table-receipt, tombstone, and checkpoint authority."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any, NoReturn

from changebridge.contracts import semantic_digest


class CDCControlError(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


def _fail(code: str, detail: str) -> NoReturn:
    raise CDCControlError(code, detail)


class CDCControlStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA journal_mode = WAL")
        self.connection.execute("PRAGMA synchronous = FULL")
        self._create_schema()

    def _create_schema(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS cdc_checkpoints (
              generation_id TEXT PRIMARY KEY,
              source_frontier TEXT NOT NULL,
              revision INTEGER NOT NULL CHECK (revision >= 0),
              last_transaction_id TEXT,
              last_transaction_digest TEXT
            );
            CREATE TABLE IF NOT EXISTS cdc_transactions (
              generation_id TEXT NOT NULL,
              transaction_id TEXT NOT NULL,
              transaction_digest TEXT NOT NULL,
              commit_lsn TEXT NOT NULL,
              manifest_id TEXT NOT NULL,
              tables_json TEXT NOT NULL,
              state TEXT NOT NULL,
              outcome_json TEXT,
              PRIMARY KEY (generation_id, transaction_id)
            );
            CREATE TABLE IF NOT EXISTS cdc_table_receipts (
              generation_id TEXT NOT NULL,
              transaction_id TEXT NOT NULL,
              source_table TEXT NOT NULL,
              transaction_digest TEXT NOT NULL,
              table_input_digest TEXT NOT NULL,
              commit_token TEXT NOT NULL,
              physical_snapshot_id TEXT NOT NULL,
              logical_digest TEXT NOT NULL,
              state TEXT NOT NULL,
              recovered INTEGER NOT NULL CHECK (recovered IN (0,1)),
              PRIMARY KEY (generation_id, transaction_id, source_table),
              UNIQUE (generation_id, commit_token),
              FOREIGN KEY (generation_id, transaction_id)
                REFERENCES cdc_transactions(generation_id, transaction_id)
            );
            CREATE TABLE IF NOT EXISTS cdc_tombstones (
              generation_id TEXT NOT NULL,
              transaction_id TEXT NOT NULL,
              event_id TEXT NOT NULL,
              source_table TEXT NOT NULL,
              source_key TEXT NOT NULL,
              source_frontier TEXT NOT NULL,
              before_digest TEXT NOT NULL,
              commit_token TEXT NOT NULL,
              PRIMARY KEY (generation_id, event_id)
            );
            """
        )

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> CDCControlStore:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def initialize_checkpoint(self, generation_id: str, source_frontier: str) -> dict[str, Any]:
        with self.connection:
            self.connection.execute(
                "INSERT OR IGNORE INTO cdc_checkpoints"
                "(generation_id,source_frontier,revision) VALUES (?,?,0)",
                (generation_id, source_frontier),
            )
        result = self.checkpoint(generation_id)
        assert result is not None
        if result["source_frontier"] != source_frontier and result["revision"] == 0:
            _fail("CB24C001_CHECKPOINT_CONFLICT", generation_id)
        return result

    def checkpoint(self, generation_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM cdc_checkpoints WHERE generation_id=?", (generation_id,)
        ).fetchone()
        return None if row is None else dict(row)

    def transaction(self, generation_id: str, transaction_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM cdc_transactions WHERE generation_id=? AND transaction_id=?",
            (generation_id, transaction_id),
        ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["tables"] = json.loads(result.pop("tables_json"))
        result["outcome"] = (
            None if result["outcome_json"] is None else json.loads(result.pop("outcome_json"))
        )
        if "outcome_json" in result:
            result.pop("outcome_json")
        return result

    def claim(self, plan: Mapping[str, Any]) -> dict[str, Any]:
        generation_id = str(plan["generation_id"])
        transaction_id = str(plan["transaction_id"])
        digest = str(plan["transaction_digest"])
        existing = self.transaction(generation_id, transaction_id)
        if existing is not None:
            if existing["transaction_digest"] != digest:
                _fail("CB24C002_TRANSACTION_REPLAY_CONFLICT", transaction_id)
            return existing
        with self.connection:
            try:
                self.connection.execute(
                    """INSERT INTO cdc_transactions(
                    generation_id,transaction_id,transaction_digest,commit_lsn,
                    manifest_id,tables_json,state) VALUES (?,?,?,?,?,?,'APPLYING')""",
                    (
                        generation_id,
                        transaction_id,
                        digest,
                        str(plan["commit_lsn"]),
                        str(plan["manifest_id"]),
                        json.dumps(plan["tables"], separators=(",", ":"), sort_keys=True),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                _fail("CB24C003_TRANSACTION_CLAIM", str(exc))
        result = self.transaction(generation_id, transaction_id)
        assert result is not None
        return result

    def record_receipt(self, receipt: Mapping[str, Any]) -> dict[str, Any]:
        keys = (
            "generation_id",
            "transaction_id",
            "source_table",
            "transaction_digest",
            "table_input_digest",
            "commit_token",
            "physical_snapshot_id",
            "logical_digest",
        )
        values = tuple(str(receipt[key]) for key in keys)
        existing = self.receipt(values[0], values[1], values[2])
        if existing is not None:
            if any(str(existing[key]) != str(receipt[key]) for key in keys):
                _fail("CB24C004_RECEIPT_CONFLICT", values[2])
            return existing
        with self.connection:
            try:
                self.connection.execute(
                    f"INSERT INTO cdc_table_receipts({','.join(keys)},state,recovered) "
                    f"VALUES ({','.join('?' for _ in keys)},'DURABLE',?)",
                    (*values, int(bool(receipt.get("recovered", False)))),
                )
            except sqlite3.IntegrityError as exc:
                _fail("CB24C004_RECEIPT_CONFLICT", str(exc))
        result = self.receipt(values[0], values[1], values[2])
        assert result is not None
        return result

    def receipt(
        self, generation_id: str, transaction_id: str, source_table: str
    ) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM cdc_table_receipts WHERE generation_id=? AND transaction_id=? "
            "AND source_table=?",
            (generation_id, transaction_id, source_table),
        ).fetchone()
        return None if row is None else dict(row)

    def receipts(self, generation_id: str, transaction_id: str) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT * FROM cdc_table_receipts WHERE generation_id=? AND transaction_id=? "
            "ORDER BY source_table",
            (generation_id, transaction_id),
        ).fetchall()
        return [dict(row) for row in rows]

    def record_tombstones(
        self, plan: Mapping[str, Any], table_tokens: Mapping[str, str]
    ) -> None:
        values: list[tuple[str, ...]] = []
        for event in plan["events"]:
            if event["operation"] != "delete":
                continue
            table = str(event["source_table"])
            values.append(
                (
                    str(plan["generation_id"]),
                    str(plan["transaction_id"]),
                    str(event["event_id"]),
                    table,
                    str(event["primary_key"][0]["value"]),
                    str(event["source_position"]["value"]),
                    semantic_digest(event["before"], domain=f"stage24-before:{table}"),
                    table_tokens[table],
                )
            )
        with self.connection:
            for row in values:
                self.connection.execute(
                    "INSERT OR IGNORE INTO cdc_tombstones VALUES (?,?,?,?,?,?,?,?)", row
                )

    def tombstones(self, generation_id: str) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT * FROM cdc_tombstones WHERE generation_id=? ORDER BY source_table,source_key",
            (generation_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def finalize(self, plan: Mapping[str, Any], *, expected_revision: int) -> dict[str, Any]:
        generation_id = str(plan["generation_id"])
        transaction_id = str(plan["transaction_id"])
        transaction = self.transaction(generation_id, transaction_id)
        assert transaction is not None
        if transaction["state"] == "CHECKPOINTED":
            checkpoint = self.checkpoint(generation_id)
            assert checkpoint is not None
            return {"transaction": transaction, "checkpoint": checkpoint, "idempotent": True}
        receipts = self.receipts(generation_id, transaction_id)
        expected_tables = list(plan["tables"])
        if [row["source_table"] for row in receipts] != expected_tables:
            _fail("CB24C005_RECEIPTS_INCOMPLETE", transaction_id)
        checkpoint = self.checkpoint(generation_id)
        if checkpoint is None:
            _fail("CB24C006_CHECKPOINT_MISSING", generation_id)
        if int(checkpoint["revision"]) != expected_revision:
            _fail("CB24C007_STALE_CHECKPOINT", generation_id)
        if checkpoint["source_frontier"] != plan["previous_frontier"]:
            _fail("CB24C008_FRONTIER_MISMATCH", generation_id)
        outcome = {
            "receipt_digest": semantic_digest(receipts, domain="stage24-receipts"),
            "tables": expected_tables,
        }
        with self.connection:
            cursor = self.connection.execute(
                "UPDATE cdc_checkpoints SET source_frontier=?,revision=revision+1,"
                "last_transaction_id=?,last_transaction_digest=? "
                "WHERE generation_id=? AND revision=? AND source_frontier=?",
                (
                    str(plan["commit_lsn"]),
                    transaction_id,
                    str(plan["transaction_digest"]),
                    generation_id,
                    expected_revision,
                    str(plan["previous_frontier"]),
                ),
            )
            if cursor.rowcount != 1:
                _fail("CB24C007_STALE_CHECKPOINT", generation_id)
            self.connection.execute(
                "UPDATE cdc_transactions SET state='CHECKPOINTED',outcome_json=? "
                "WHERE generation_id=? AND transaction_id=? AND state='APPLYING'",
                (
                    json.dumps(outcome, sort_keys=True, separators=(",", ":")),
                    generation_id,
                    transaction_id,
                ),
            )
        final_transaction = self.transaction(generation_id, transaction_id)
        final_checkpoint = self.checkpoint(generation_id)
        assert final_transaction is not None and final_checkpoint is not None
        return {
            "transaction": final_transaction,
            "checkpoint": final_checkpoint,
            "idempotent": False,
        }
