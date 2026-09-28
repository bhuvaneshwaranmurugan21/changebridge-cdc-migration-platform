"""Independent SQLite semantic reference for Stage 4 differential proof."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from changebridge.contracts import semantic_digest


class ReferenceCDCError(RuntimeError):
    pass


class ReferenceCDCStore:
    def __init__(self, path: Path) -> None:
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS rows (
              source_table TEXT NOT NULL,
              source_key TEXT NOT NULL,
              row_json TEXT NOT NULL,
              PRIMARY KEY(source_table,source_key)
            );
            CREATE TABLE IF NOT EXISTS transactions (
              transaction_id TEXT PRIMARY KEY,
              transaction_digest TEXT NOT NULL,
              source_frontier TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tombstones (
              event_id TEXT PRIMARY KEY,
              source_table TEXT NOT NULL,
              source_key TEXT NOT NULL,
              source_frontier TEXT NOT NULL,
              before_digest TEXT NOT NULL
            );
            """
        )

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> ReferenceCDCStore:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @staticmethod
    def _render(value: Mapping[str, Any]) -> str:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    def initialize(self, tables: Mapping[str, Any]) -> None:
        with self.connection:
            for table, material in tables.items():
                rows = (
                    material["rows"]
                    if isinstance(material, Mapping) and "rows" in material
                    else material
                )
                for row in rows:
                    key_name = "order_id" if table == "orders" else "item_id"
                    self.connection.execute(
                        "INSERT OR REPLACE INTO rows VALUES (?,?,?)",
                        (table, str(row[key_name]), self._render(row)),
                    )

    def apply(self, plan: Mapping[str, Any]) -> dict[str, Any]:
        existing = self.connection.execute(
            "SELECT transaction_digest FROM transactions WHERE transaction_id=?",
            (str(plan["transaction_id"]),),
        ).fetchone()
        if existing is not None:
            if existing["transaction_digest"] != plan["transaction_digest"]:
                raise ReferenceCDCError("CB24R001_REPLAY_CONFLICT")
            return {"idempotent_replay": True}
        with self.connection:
            for event in plan["events"]:
                table = str(event["source_table"])
                key = str(event["primary_key"][0]["value"])
                current = self.connection.execute(
                    "SELECT row_json FROM rows WHERE source_table=? AND source_key=?",
                    (table, key),
                ).fetchone()
                operation = event["operation"]
                if operation == "insert":
                    if current is not None:
                        raise ReferenceCDCError("CB24R002_DUPLICATE_INSERT")
                    self.connection.execute(
                        "INSERT INTO rows VALUES (?,?,?)",
                        (table, key, self._render(event["after"])),
                    )
                else:
                    if current is None or json.loads(current["row_json"]) != event["before"]:
                        raise ReferenceCDCError("CB24R003_BEFORE_IMAGE_MISMATCH")
                    if operation == "update":
                        self.connection.execute(
                            "UPDATE rows SET row_json=? WHERE source_table=? AND source_key=?",
                            (self._render(event["after"]), table, key),
                        )
                    elif operation == "delete":
                        self.connection.execute(
                            "DELETE FROM rows WHERE source_table=? AND source_key=?", (table, key)
                        )
                        self.connection.execute(
                            "INSERT INTO tombstones VALUES (?,?,?,?,?)",
                            (
                                str(event["event_id"]),
                                table,
                                key,
                                str(event["source_position"]["value"]),
                                semantic_digest(event["before"], domain=f"stage24-before:{table}"),
                            ),
                        )
            self.connection.execute(
                "INSERT INTO transactions VALUES (?,?,?)",
                (
                    str(plan["transaction_id"]),
                    str(plan["transaction_digest"]),
                    str(plan["commit_lsn"]),
                ),
            )
        return {"idempotent_replay": False}

    def rows(self, table: str) -> list[dict[str, Any]]:
        records = self.connection.execute(
            "SELECT row_json FROM rows WHERE source_table=? ORDER BY source_key", (table,)
        ).fetchall()
        return [json.loads(record["row_json"]) for record in records]

    def table_result(self, table: str) -> dict[str, Any]:
        rows = self.rows(table)
        return {
            "table": table,
            "row_count": len(rows),
            "state_digest": semantic_digest(rows, domain=f"source-table-state:{table}"),
        }
