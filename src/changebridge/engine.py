"""SQLite-backed reference implementation of ChangeBridge invariants."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from changebridge.canonical import canonical_json, digest
from changebridge.model import CdcBatch, Generation, Operation


class ChangeBridgeError(RuntimeError):
    """Base class for correctness failures that must stop publication."""


class FrontierGap(ChangeBridgeError):
    pass


class ReplayConflict(ChangeBridgeError):
    pass


class CompareAndSwapConflict(ChangeBridgeError):
    pass


class InvalidGenerationState(ChangeBridgeError):
    pass


class ChangeBridgeEngine:
    """Executable correctness oracle; production adapters preserve the same contract."""

    def __init__(self, database: str | Path = ":memory:") -> None:
        self.connection = sqlite3.connect(str(database), isolation_level=None)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self._create_schema()

    def close(self) -> None:
        self.connection.close()

    def _create_schema(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS generations (
                generation_id TEXT PRIMARY KEY,
                snapshot_lsn INTEGER NOT NULL,
                current_lsn INTEGER NOT NULL,
                schema_version TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('loading', 'candidate', 'ready', 'retired')),
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS records (
                generation_id TEXT NOT NULL REFERENCES generations(generation_id),
                table_name TEXT NOT NULL,
                record_key TEXT NOT NULL,
                payload_json TEXT,
                source_lsn INTEGER NOT NULL,
                deleted INTEGER NOT NULL CHECK(deleted IN (0, 1)),
                PRIMARY KEY (generation_id, table_name, record_key)
            );
            CREATE TABLE IF NOT EXISTS applied_transactions (
                generation_id TEXT NOT NULL REFERENCES generations(generation_id),
                transaction_id TEXT NOT NULL,
                payload_digest TEXT NOT NULL,
                commit_lsn INTEGER NOT NULL,
                PRIMARY KEY (generation_id, transaction_id)
            );
            CREATE TABLE IF NOT EXISTS applied_batches (
                generation_id TEXT NOT NULL REFERENCES generations(generation_id),
                batch_id TEXT NOT NULL,
                payload_digest TEXT NOT NULL,
                start_lsn INTEGER NOT NULL,
                end_lsn INTEGER NOT NULL,
                PRIMARY KEY (generation_id, batch_id)
            );
            CREATE TABLE IF NOT EXISTS active_pointer (
                singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                generation_id TEXT REFERENCES generations(generation_id),
                pointer_version INTEGER NOT NULL
            );
            INSERT OR IGNORE INTO active_pointer(singleton, generation_id, pointer_version)
            VALUES (1, NULL, 0);
            """
        )

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            yield
        except Exception:
            self.connection.execute("ROLLBACK")
            raise
        else:
            self.connection.execute("COMMIT")

    def create_generation(self, generation_id: str, snapshot_lsn: int, schema_version: str) -> None:
        if snapshot_lsn < 0:
            raise ValueError("snapshot LSN must be non-negative")
        self.connection.execute(
            """INSERT INTO generations
               (generation_id, snapshot_lsn, current_lsn, schema_version, status, created_at)
               VALUES (?, ?, ?, ?, 'loading', ?)""",
            (generation_id, snapshot_lsn, snapshot_lsn, schema_version, datetime.now(UTC).isoformat()),
        )

    def load_snapshot(
        self,
        generation_id: str,
        tables: Mapping[str, Mapping[str, Mapping[str, Any]]],
    ) -> None:
        generation = self.get_generation(generation_id)
        if generation.status != "loading":
            raise InvalidGenerationState("snapshot can only be loaded into a loading generation")
        existing = self.connection.execute(
            "SELECT COUNT(*) AS count FROM records WHERE generation_id = ?", (generation_id,)
        ).fetchone()["count"]
        if existing:
            raise InvalidGenerationState("snapshot is immutable once loaded")
        with self._transaction():
            for table_name, rows in sorted(tables.items()):
                for record_key, payload in sorted(rows.items()):
                    self.connection.execute(
                        """INSERT INTO records
                           (generation_id, table_name, record_key, payload_json, source_lsn, deleted)
                           VALUES (?, ?, ?, ?, ?, 0)""",
                        (
                            generation_id,
                            table_name,
                            record_key,
                            canonical_json(payload),
                            generation.snapshot_lsn,
                        ),
                    )
            self.connection.execute(
                "UPDATE generations SET status = 'candidate' WHERE generation_id = ?",
                (generation_id,),
            )

    def apply_batch(
        self,
        generation_id: str,
        batch: CdcBatch,
        *,
        fail_before_commit: bool = False,
    ) -> str:
        """Apply a contiguous batch atomically; return applied or replayed."""

        generation = self.get_generation(generation_id)
        if generation.status not in {"candidate", "ready"}:
            raise InvalidGenerationState("CDC requires a candidate or ready generation")
        batch_digest = digest(batch.as_dict())
        prior_batch = self.connection.execute(
            """SELECT payload_digest FROM applied_batches
               WHERE generation_id = ? AND batch_id = ?""",
            (generation_id, batch.batch_id),
        ).fetchone()
        if prior_batch:
            if prior_batch["payload_digest"] != batch_digest:
                raise ReplayConflict(f"batch {batch.batch_id} was replayed with different content")
            return "replayed"
        if batch.start_lsn_exclusive != generation.current_lsn:
            raise FrontierGap(
                f"expected start LSN {generation.current_lsn}, got {batch.start_lsn_exclusive}"
            )
        previous_lsn = batch.start_lsn_exclusive
        for transaction in batch.transactions:
            if not previous_lsn < transaction.commit_lsn <= batch.end_lsn_inclusive:
                raise FrontierGap("transactions must be ordered inside the declared frontier")
            previous_lsn = transaction.commit_lsn

        with self._transaction():
            for transaction in batch.transactions:
                transaction_digest = digest(transaction.as_dict())
                prior = self.connection.execute(
                    """SELECT payload_digest FROM applied_transactions
                       WHERE generation_id = ? AND transaction_id = ?""",
                    (generation_id, transaction.transaction_id),
                ).fetchone()
                if prior:
                    if prior["payload_digest"] != transaction_digest:
                        raise ReplayConflict(
                            f"transaction {transaction.transaction_id} changed during replay"
                        )
                    continue
                for event in transaction.events:
                    payload = None if event.after is None else canonical_json(event.after)
                    self.connection.execute(
                        """INSERT INTO records
                           (generation_id, table_name, record_key, payload_json, source_lsn, deleted)
                           VALUES (?, ?, ?, ?, ?, ?)
                           ON CONFLICT(generation_id, table_name, record_key) DO UPDATE SET
                             payload_json = excluded.payload_json,
                             source_lsn = excluded.source_lsn,
                             deleted = excluded.deleted""",
                        (
                            generation_id,
                            event.table,
                            event.key,
                            payload,
                            transaction.commit_lsn,
                            int(event.operation is Operation.DELETE),
                        ),
                    )
                self.connection.execute(
                    """INSERT INTO applied_transactions
                       (generation_id, transaction_id, payload_digest, commit_lsn)
                       VALUES (?, ?, ?, ?)""",
                    (
                        generation_id,
                        transaction.transaction_id,
                        transaction_digest,
                        transaction.commit_lsn,
                    ),
                )
            self.connection.execute(
                """INSERT INTO applied_batches
                   (generation_id, batch_id, payload_digest, start_lsn, end_lsn)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    generation_id,
                    batch.batch_id,
                    batch_digest,
                    batch.start_lsn_exclusive,
                    batch.end_lsn_inclusive,
                ),
            )
            self.connection.execute(
                "UPDATE generations SET current_lsn = ? WHERE generation_id = ?",
                (batch.end_lsn_inclusive, generation_id),
            )
            if fail_before_commit:
                raise RuntimeError("injected crash before commit")
        return "applied"

    def get_generation(self, generation_id: str) -> Generation:
        row = self.connection.execute(
            "SELECT * FROM generations WHERE generation_id = ?", (generation_id,)
        ).fetchone()
        if row is None:
            raise KeyError(generation_id)
        return Generation(
            generation_id=row["generation_id"],
            snapshot_lsn=row["snapshot_lsn"],
            current_lsn=row["current_lsn"],
            schema_version=row["schema_version"],
            status=row["status"],
        )

    def state(self, generation_id: str) -> dict[str, dict[str, dict[str, Any]]]:
        rows = self.connection.execute(
            """SELECT table_name, record_key, payload_json FROM records
               WHERE generation_id = ? AND deleted = 0
               ORDER BY table_name, record_key""",
            (generation_id,),
        )
        result: dict[str, dict[str, dict[str, Any]]] = {}
        for row in rows:
            result.setdefault(row["table_name"], {})[row["record_key"]] = json.loads(
                row["payload_json"]
            )
        return result

    def tombstones(self, generation_id: str) -> Sequence[sqlite3.Row]:
        return self.connection.execute(
            """SELECT table_name, record_key, source_lsn FROM records
               WHERE generation_id = ? AND deleted = 1 ORDER BY table_name, record_key""",
            (generation_id,),
        ).fetchall()

    def mark_ready(self, generation_id: str) -> None:
        generation = self.get_generation(generation_id)
        if generation.status != "candidate":
            raise InvalidGenerationState("only a candidate can become ready")
        self.connection.execute(
            "UPDATE generations SET status = 'ready' WHERE generation_id = ?", (generation_id,)
        )

    def active_pointer(self) -> tuple[str | None, int]:
        row = self.connection.execute(
            "SELECT generation_id, pointer_version FROM active_pointer WHERE singleton = 1"
        ).fetchone()
        return row["generation_id"], row["pointer_version"]

    def activate(self, generation_id: str, expected_version: int) -> int:
        generation = self.get_generation(generation_id)
        if generation.status != "ready":
            raise InvalidGenerationState("only a proof-gated ready generation can be activated")
        with self._transaction():
            result = self.connection.execute(
                """UPDATE active_pointer
                   SET generation_id = ?, pointer_version = pointer_version + 1
                   WHERE singleton = 1 AND pointer_version = ?""",
                (generation_id, expected_version),
            )
            if result.rowcount != 1:
                raise CompareAndSwapConflict("active pointer changed concurrently")
        return expected_version + 1
