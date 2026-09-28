"""Durable, recoverable Stage 6 proof ledger."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from changebridge.contracts import semantic_digest
from changebridge.proof_gates import assemble_manifest, validate_gate


class ProofControlStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=FULL")
        self.connection.executescript("""
        CREATE TABLE IF NOT EXISTS generations(
          generation_id TEXT PRIMARY KEY, frontier TEXT NOT NULL,
          schema_set_digest TEXT NOT NULL, state TEXT NOT NULL,
          revision INTEGER NOT NULL,
          seal_json TEXT, manifest_json TEXT);
        CREATE TABLE IF NOT EXISTS attempts(
          attempt_id TEXT PRIMARY KEY, generation_id TEXT NOT NULL,
          input_revision INTEGER NOT NULL, state TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS gates(attempt_id TEXT NOT NULL, gate_id TEXT NOT NULL,
          gate_json TEXT NOT NULL, PRIMARY KEY(attempt_id,gate_id));
        """)

    def __enter__(self) -> ProofControlStore:
        return self

    def __exit__(self, *_: object) -> None:
        self.connection.close()

    def register_candidate(
        self, generation_id: str, *, frontier: str, schema_set_digest: str
    ) -> None:
        with self.connection:
            self.connection.execute(
                "INSERT OR IGNORE INTO generations VALUES (?,?,?,?,?,?,?)",
                (generation_id, frontier, schema_set_digest, "CDC_APPLYING", 0, None, None),
            )

    def generation(self, generation_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM generations WHERE generation_id=?", (generation_id,)
        ).fetchone()
        return None if row is None else dict(row)

    def seal(self, generation_id: str, seal: Mapping[str, Any]) -> dict[str, Any]:
        row = self.generation(generation_id)
        if row is None or row["state"] not in {"CDC_APPLYING", "SEALED"}:
            raise RuntimeError("CB26C001_INVALID_SEAL_STATE")
        payload = json.dumps(seal, sort_keys=True, separators=(",", ":"))
        if row["seal_json"] is not None and row["seal_json"] != payload:
            raise RuntimeError("CB26C002_SEAL_CONFLICT")
        with self.connection:
            self.connection.execute(
                "UPDATE generations SET state='SEALED',revision=1,seal_json=? "
                "WHERE generation_id=?",
                (payload, generation_id),
            )
        return dict(seal)

    def begin_proof(self, generation_id: str) -> dict[str, Any]:
        row = self.generation(generation_id)
        if row is None or row["state"] not in {"SEALED", "PROVING"}:
            raise RuntimeError("CB26C003_INVALID_PROOF_STATE")
        attempt_id = semantic_digest(
            {"generation_id": generation_id, "revision": row["revision"]},
            domain="stage26-proof-attempt",
        )
        with self.connection:
            self.connection.execute(
                "INSERT OR IGNORE INTO attempts VALUES (?,?,?,?)",
                (attempt_id, generation_id, row["revision"], "OPEN"),
            )
            self.connection.execute(
                "UPDATE generations SET state='PROVING' WHERE generation_id=?", (generation_id,)
            )
        return {"attempt_id": attempt_id, "input_revision": row["revision"]}

    def record_gate(self, attempt_id: str, gate: Mapping[str, Any]) -> None:
        validate_gate(gate)
        payload = json.dumps(gate, sort_keys=True, separators=(",", ":"))
        row = self.connection.execute(
            "SELECT gate_json FROM gates WHERE attempt_id=? AND gate_id=?",
            (attempt_id, gate["gate_id"]),
        ).fetchone()
        if row is not None and row[0] != payload:
            raise RuntimeError("CB26C004_GATE_CONFLICT")
        with self.connection:
            self.connection.execute(
                "INSERT OR IGNORE INTO gates VALUES (?,?,?)", (attempt_id, gate["gate_id"], payload)
            )

    def seal_manifest(self, attempt_id: str) -> dict[str, Any]:
        attempt = self.connection.execute(
            "SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)
        ).fetchone()
        if attempt is None:
            raise RuntimeError("CB26C005_UNKNOWN_ATTEMPT")
        generation = self.generation(attempt["generation_id"])
        assert generation is not None and generation["seal_json"] is not None
        seal = json.loads(generation["seal_json"])
        gates = [
            json.loads(row[0])
            for row in self.connection.execute(
                "SELECT gate_json FROM gates WHERE attempt_id=? ORDER BY gate_id", (attempt_id,)
            ).fetchall()
        ]
        manifest = assemble_manifest(
            gates,
            generation_id=generation["generation_id"],
            frontier=generation["frontier"],
            schema_set_digest=generation["schema_set_digest"],
            input_revision=attempt["input_revision"],
            seal_digest=seal["seal_digest"],
        )
        payload = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
        with self.connection:
            self.connection.execute(
                "UPDATE attempts SET state='SEALED' WHERE attempt_id=?", (attempt_id,)
            )
            self.connection.execute(
                "UPDATE generations SET state='PROVEN',revision=2,manifest_json=? "
                "WHERE generation_id=?",
                (payload, generation["generation_id"]),
            )
        return manifest
