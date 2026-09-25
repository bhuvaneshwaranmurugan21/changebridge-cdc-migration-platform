"""Durable Stage 3 generation, shard, commit, transition, and proof authority."""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any, NoReturn

from changebridge.contracts import semantic_digest

GENERATION_STATES = frozenset(
    {
        "CREATED",
        "SNAPSHOT_LOADING",
        "CDC_APPLYING",
        "ACTIVE",
        "PUBLISHED",
        "ROLLED_BACK",
        "REJECTED",
        "RETIRED",
    }
)
SHARD_STATES = frozenset({"CLAIMED", "STAGED", "COMMITTED", "RECONCILED"})
TERMINAL_OR_PROTECTED_STATES = frozenset(
    {"CDC_APPLYING", "ACTIVE", "PUBLISHED", "ROLLED_BACK", "REJECTED", "RETIRED"}
)
_NAMESPACE = re.compile(r"^cb_g_[a-f0-9]{16}$")


class GenerationRegistryError(RuntimeError):
    """Stable fail-closed Stage 3 control-store diagnostic."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


def _fail(code: str, detail: str) -> NoReturn:
    raise GenerationRegistryError(code, detail)


def deterministic_generation_id(workload_id: str) -> str:
    """Return the Stage 1-compatible deterministic generation identity."""

    if not re.fullmatch(r"[0-9a-f]{64}", workload_id):
        _fail("CBG001_INVALID_WORKLOAD_ID", workload_id)
    return f"generation-{workload_id[:24]}"


def generation_namespace(generation_id: str) -> str:
    digest = semantic_digest(generation_id, domain="stage23-generation-namespace")
    return f"cb_g_{digest[:16]}"


def generation_warehouse(root: Path, generation_id: str) -> Path:
    """Return a non-aliasing, symlink-safe generation-owned warehouse."""

    if not root.is_absolute():
        _fail("CBG002_WAREHOUSE_ROOT_NOT_ABSOLUTE", str(root))
    if root.exists() and root.is_symlink():
        _fail("CBG003_WAREHOUSE_ROOT_SYMLINK", str(root))
    resolved_root = root.resolve()
    candidate = resolved_root / "generations" / generation_id
    if candidate.exists() and candidate.is_symlink():
        _fail("CBG004_WAREHOUSE_GENERATION_SYMLINK", str(candidate))
    try:
        candidate.resolve().relative_to(resolved_root)
    except ValueError:
        _fail("CBG005_WAREHOUSE_ESCAPE", str(candidate))
    return candidate


class GenerationRegistry:
    """SQLite-backed compare-and-swap authority for one local candidate set."""

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
            CREATE TABLE IF NOT EXISTS generation_registry (
              generation_id TEXT PRIMARY KEY,
              lineage_digest TEXT NOT NULL,
              workload_id TEXT NOT NULL,
              run_id TEXT NOT NULL,
              snapshot_frontier TEXT NOT NULL,
              schema_set_digest TEXT NOT NULL,
              canonicalization_profile TEXT NOT NULL,
              warehouse_path TEXT NOT NULL UNIQUE,
              namespace TEXT NOT NULL UNIQUE,
              table_map_json TEXT NOT NULL,
              state TEXT NOT NULL,
              revision INTEGER NOT NULL,
              CHECK (revision >= 0)
            );
            CREATE TABLE IF NOT EXISTS snapshot_shards (
              generation_id TEXT NOT NULL REFERENCES generation_registry(generation_id),
              shard_id TEXT NOT NULL,
              source_table TEXT NOT NULL,
              input_digest TEXT NOT NULL,
              row_count INTEGER NOT NULL,
              idempotency_key TEXT NOT NULL,
              commit_token TEXT NOT NULL,
              state TEXT NOT NULL,
              attempt INTEGER NOT NULL,
              PRIMARY KEY (generation_id, shard_id),
              UNIQUE (generation_id, idempotency_key),
              UNIQUE (generation_id, commit_token)
            );
            CREATE TABLE IF NOT EXISTS target_commits (
              generation_id TEXT NOT NULL,
              shard_id TEXT NOT NULL,
              commit_token TEXT NOT NULL,
              iceberg_table TEXT NOT NULL,
              physical_snapshot_id TEXT NOT NULL,
              input_digest TEXT NOT NULL,
              row_count INTEGER NOT NULL,
              logical_digest TEXT NOT NULL,
              summary_digest TEXT NOT NULL,
              reconciliation_state TEXT NOT NULL,
              PRIMARY KEY (generation_id, commit_token),
              FOREIGN KEY (generation_id, shard_id)
                REFERENCES snapshot_shards(generation_id, shard_id)
            );
            CREATE TABLE IF NOT EXISTS generation_transitions (
              generation_id TEXT NOT NULL REFERENCES generation_registry(generation_id),
              from_state TEXT NOT NULL,
              to_state TEXT NOT NULL,
              expected_revision INTEGER NOT NULL,
              resulting_revision INTEGER NOT NULL,
              decision_digest TEXT NOT NULL,
              actor TEXT NOT NULL,
              result TEXT NOT NULL,
              PRIMARY KEY (generation_id, resulting_revision)
            );
            CREATE TABLE IF NOT EXISTS snapshot_admission_proofs (
              generation_id TEXT PRIMARY KEY REFERENCES generation_registry(generation_id),
              proof_digest TEXT NOT NULL,
              proof_json TEXT NOT NULL,
              verdict TEXT NOT NULL
            );
            """
        )

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> GenerationRegistry:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @staticmethod
    def lineage_digest(record: Mapping[str, Any]) -> str:
        material = {
            key: record[key]
            for key in (
                "workload_id",
                "run_id",
                "snapshot_frontier",
                "schema_set_digest",
                "canonicalization_profile",
            )
        }
        return semantic_digest(material, domain="stage23-generation-lineage")

    def register_generation(self, record: Mapping[str, Any]) -> dict[str, Any]:
        generation_id = str(record["generation_id"])
        if generation_id != deterministic_generation_id(str(record["workload_id"])):
            _fail("CBG006_GENERATION_ID_MISMATCH", generation_id)
        namespace = str(record["namespace"])
        if _NAMESPACE.fullmatch(namespace) is None or namespace != generation_namespace(
            generation_id
        ):
            _fail("CBG007_NAMESPACE_MISMATCH", namespace)
        warehouse = Path(str(record["warehouse_path"]))
        if (
            not warehouse.is_absolute()
            or warehouse.name != generation_id
            or warehouse.parent.name != "generations"
            or warehouse.resolve() != warehouse
            or (warehouse.exists() and warehouse.is_symlink())
        ):
            _fail("CBG024_WAREHOUSE_OWNERSHIP", str(warehouse))
        table_map = record["table_map"]
        if not isinstance(table_map, Mapping) or set(table_map) != {"order_items", "orders"}:
            _fail("CBG008_TABLE_MAP", repr(table_map))
        values = {
            "generation_id": generation_id,
            "lineage_digest": self.lineage_digest(record),
            "workload_id": str(record["workload_id"]),
            "run_id": str(record["run_id"]),
            "snapshot_frontier": str(record["snapshot_frontier"]),
            "schema_set_digest": str(record["schema_set_digest"]),
            "canonicalization_profile": str(record["canonicalization_profile"]),
            "warehouse_path": str(record["warehouse_path"]),
            "namespace": namespace,
            "table_map_json": json.dumps(table_map, sort_keys=True, separators=(",", ":")),
            "state": "CREATED",
            "revision": 0,
        }
        existing = self.get_generation(generation_id, required=False)
        if existing is not None:
            immutable_keys = tuple(
                key for key in values if key not in {"table_map_json", "state", "revision"}
            )
            comparable = {
                **{key: existing[key] for key in immutable_keys},
                "table_map_json": json.dumps(
                    existing["table_map"], sort_keys=True, separators=(",", ":")
                ),
            }
            expected = {
                **{key: values[key] for key in immutable_keys},
                "table_map_json": values["table_map_json"],
            }
            if comparable != expected:
                _fail("CBG009_GENERATION_REPLAY_CONFLICT", generation_id)
            return existing
        with self.connection:
            try:
                self.connection.execute(
                    """
                    INSERT INTO generation_registry(
                      generation_id, lineage_digest, workload_id, run_id,
                      snapshot_frontier, schema_set_digest, canonicalization_profile,
                      warehouse_path, namespace, table_map_json, state, revision
                    ) VALUES (
                      :generation_id, :lineage_digest, :workload_id, :run_id,
                      :snapshot_frontier, :schema_set_digest, :canonicalization_profile,
                      :warehouse_path, :namespace, :table_map_json, :state, :revision
                    )
                    """,
                    values,
                )
            except sqlite3.IntegrityError as exc:
                _fail("CBG010_PHYSICAL_OWNERSHIP_CONFLICT", str(exc))
        result = self.get_generation(generation_id)
        assert result is not None
        return result

    def get_generation(self, generation_id: str, *, required: bool = True) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM generation_registry WHERE generation_id = ?", (generation_id,)
        ).fetchone()
        if row is None:
            if required:
                _fail("CBG011_GENERATION_NOT_FOUND", generation_id)
            return None
        result = dict(row)
        result["table_map"] = json.loads(result.pop("table_map_json"))
        return result

    def transition(
        self,
        generation_id: str,
        *,
        expected_revision: int,
        to_state: str,
        actor: str,
        decision: Mapping[str, Any],
    ) -> dict[str, Any]:
        if to_state not in GENERATION_STATES:
            _fail("CBG012_UNKNOWN_STATE", to_state)
        generation = self.get_generation(generation_id)
        assert generation is not None
        current_state = str(generation["state"])
        current_revision = int(generation["revision"])
        allowed = {
            ("CREATED", "SNAPSHOT_LOADING"),
            ("SNAPSHOT_LOADING", "CDC_APPLYING"),
        }
        decision_digest = semantic_digest(decision, domain="stage23-generation-transition")
        if current_state == to_state and current_revision == expected_revision + 1:
            return generation
        if current_revision != expected_revision:
            _fail(
                "CBG013_STALE_REVISION",
                f"expected={expected_revision},actual={current_revision}",
            )
        if (current_state, to_state) not in allowed:
            _fail("CBG014_ILLEGAL_TRANSITION", f"{current_state}->{to_state}")
        if to_state == "CDC_APPLYING":
            proof = self.connection.execute(
                "SELECT proof_digest, verdict FROM snapshot_admission_proofs "
                "WHERE generation_id = ?",
                (generation_id,),
            ).fetchone()
            if (
                proof is None
                or proof["verdict"] != "PASS"
                or decision.get("admission_proof_digest") != proof["proof_digest"]
            ):
                _fail("CBG025_ADMISSION_PROOF_REQUIRED", generation_id)
        with self.connection:
            cursor = self.connection.execute(
                """
                UPDATE generation_registry
                   SET state = ?, revision = revision + 1
                 WHERE generation_id = ? AND revision = ? AND state = ?
                """,
                (to_state, generation_id, expected_revision, current_state),
            )
            if cursor.rowcount != 1:
                _fail("CBG013_STALE_REVISION", generation_id)
            self.connection.execute(
                """
                INSERT INTO generation_transitions(
                  generation_id, from_state, to_state, expected_revision,
                  resulting_revision, decision_digest, actor, result
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'PASS')
                """,
                (
                    generation_id,
                    current_state,
                    to_state,
                    expected_revision,
                    expected_revision + 1,
                    decision_digest,
                    actor,
                ),
            )
        result = self.get_generation(generation_id)
        assert result is not None
        return result

    def claim_shard(
        self,
        *,
        generation_id: str,
        shard_id: str,
        source_table: str,
        input_digest: str,
        row_count: int,
        idempotency_key: str,
        commit_token: str,
    ) -> dict[str, Any]:
        generation = self.get_generation(generation_id)
        assert generation is not None
        if generation["state"] != "SNAPSHOT_LOADING":
            _fail("CBG015_GENERATION_NOT_WRITABLE", str(generation["state"]))
        existing = self.get_shard(generation_id, shard_id, required=False)
        proposed = {
            "generation_id": generation_id,
            "shard_id": shard_id,
            "source_table": source_table,
            "input_digest": input_digest,
            "row_count": row_count,
            "idempotency_key": idempotency_key,
            "commit_token": commit_token,
        }
        if existing is not None:
            if any(existing[key] != value for key, value in proposed.items()):
                _fail("CBG016_SHARD_REPLAY_CONFLICT", shard_id)
            return existing
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO snapshot_shards(
                  generation_id, shard_id, source_table, input_digest, row_count,
                  idempotency_key, commit_token, state, attempt
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'CLAIMED', 1)
                """,
                (
                    generation_id,
                    shard_id,
                    source_table,
                    input_digest,
                    row_count,
                    idempotency_key,
                    commit_token,
                ),
            )
        result = self.get_shard(generation_id, shard_id)
        assert result is not None
        return result

    def get_shard(
        self, generation_id: str, shard_id: str, *, required: bool = True
    ) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM snapshot_shards WHERE generation_id = ? AND shard_id = ?",
            (generation_id, shard_id),
        ).fetchone()
        if row is None:
            if required:
                _fail("CBG017_SHARD_NOT_FOUND", shard_id)
            return None
        return dict(row)

    def mark_shard_state(self, generation_id: str, shard_id: str, to_state: str) -> dict[str, Any]:
        if to_state not in SHARD_STATES:
            _fail("CBG018_UNKNOWN_SHARD_STATE", to_state)
        shard = self.get_shard(generation_id, shard_id)
        assert shard is not None
        current = str(shard["state"])
        if current == to_state:
            return shard
        allowed = {
            ("CLAIMED", "STAGED"),
            ("CLAIMED", "COMMITTED"),
            ("STAGED", "COMMITTED"),
            ("COMMITTED", "RECONCILED"),
        }
        if (current, to_state) not in allowed:
            _fail("CBG019_ILLEGAL_SHARD_TRANSITION", f"{current}->{to_state}")
        with self.connection:
            self.connection.execute(
                """
                UPDATE snapshot_shards SET state = ?
                 WHERE generation_id = ? AND shard_id = ? AND state = ?
                """,
                (to_state, generation_id, shard_id, current),
            )
        result = self.get_shard(generation_id, shard_id)
        assert result is not None
        return result

    def record_target_commit(self, record: Mapping[str, Any]) -> dict[str, Any]:
        generation_id = str(record["generation_id"])
        commit_token = str(record["commit_token"])
        existing = self.target_commit(generation_id, commit_token, required=False)
        keys = (
            "generation_id",
            "shard_id",
            "commit_token",
            "iceberg_table",
            "physical_snapshot_id",
            "input_digest",
            "row_count",
            "logical_digest",
            "summary_digest",
            "reconciliation_state",
        )
        proposed = {key: record[key] for key in keys}
        if existing is not None:
            if any(existing[key] != value for key, value in proposed.items()):
                _fail("CBG020_COMMIT_REPLAY_CONFLICT", commit_token)
            return existing
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO target_commits(
                  generation_id, shard_id, commit_token, iceberg_table,
                  physical_snapshot_id, input_digest, row_count, logical_digest,
                  summary_digest, reconciliation_state
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                tuple(proposed[key] for key in keys),
            )
        result = self.target_commit(generation_id, commit_token)
        assert result is not None
        return result

    def target_commit(
        self, generation_id: str, commit_token: str, *, required: bool = True
    ) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM target_commits WHERE generation_id = ? AND commit_token = ?",
            (generation_id, commit_token),
        ).fetchone()
        if row is None:
            if required:
                _fail("CBG021_COMMIT_NOT_FOUND", commit_token)
            return None
        return dict(row)

    def shards(self, generation_id: str) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT * FROM snapshot_shards WHERE generation_id = ? ORDER BY shard_id",
            (generation_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def commits(self, generation_id: str) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT * FROM target_commits WHERE generation_id = ? ORDER BY iceberg_table",
            (generation_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def record_admission_proof(
        self, generation_id: str, proof: Mapping[str, Any]
    ) -> dict[str, Any]:
        verdict = str(proof.get("verdict"))
        if verdict != "PASS":
            _fail("CBG022_ADMISSION_FAILED", verdict)
        shards = self.shards(generation_id)
        table_results = proof.get("table_results")
        complete = (
            proof.get("generation_id") == generation_id
            and proof.get("snapshot_frontier") == {"kind": "postgres_lsn", "value": "0/194FB20"}
            and proof.get("post_s_cdc_applied") == 0
            and proof.get("all_commits_reconciled") is True
            and proof.get("active_or_foreign_mutations") == 0
            and isinstance(table_results, Mapping)
            and {
                table: table_results.get(table, {}).get("row_count")
                for table in ("order_items", "orders")
            }
            == {"order_items": 66, "orders": 6}
            and len(shards) == 2
            and all(row["state"] == "RECONCILED" for row in shards)
        )
        if not complete:
            _fail("CBG026_INCOMPLETE_ADMISSION_PROOF", generation_id)
        proof_json = json.dumps(proof, sort_keys=True, separators=(",", ":"))
        proof_digest = semantic_digest(proof, domain="stage23-snapshot-admission")
        existing = self.connection.execute(
            "SELECT * FROM snapshot_admission_proofs WHERE generation_id = ?",
            (generation_id,),
        ).fetchone()
        if existing is not None:
            if existing["proof_digest"] != proof_digest:
                _fail("CBG023_ADMISSION_REPLAY_CONFLICT", generation_id)
            return dict(existing)
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO snapshot_admission_proofs(
                  generation_id, proof_digest, proof_json, verdict
                ) VALUES (?, ?, ?, 'PASS')
                """,
                (generation_id, proof_digest, proof_json),
            )
        row = self.connection.execute(
            "SELECT * FROM snapshot_admission_proofs WHERE generation_id = ?",
            (generation_id,),
        ).fetchone()
        assert row is not None
        return dict(row)
