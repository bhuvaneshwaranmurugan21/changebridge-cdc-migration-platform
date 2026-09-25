"""Generation-scoped Stage 3 snapshot load protocol and recovery decisions."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any, NoReturn

from changebridge.contracts import semantic_digest
from changebridge.generation_registry import GenerationRegistry
from changebridge.iceberg_snapshot import IcebergSnapshotAdapter
from changebridge.snapshot_handoff import EXPECTED_COUNTS, EXPECTED_FRONTIER

EXPECTED_CONTRACTS = {
    "orders": {
        "source_contract_id": "orders_source_contract_v1_1",
        "source_contract_version": "1.1.0",
        "source_contract_digest": (
            "3797f8a7959cffb6ea5759246d5bdb961a9c34f9e7983999662b22ae88fe9ca0"
        ),
        "source_schema_version": "orders/1.1.0",
        "source_schema_digest": "3797f8a7959cffb6ea5759246d5bdb961a9c34f9e7983999662b22ae88fe9ca0",
    },
    "order_items": {
        "source_contract_id": "order_items_source_contract",
        "source_contract_version": "1.0.0",
        "source_contract_digest": (
            "a3a0f107c60ac6a8dd9f9caa1937ed7e24f90540923c4f3cf7361c5072141b84"
        ),
        "source_schema_version": "order_items/1.0.0",
        "source_schema_digest": "a3a0f107c60ac6a8dd9f9caa1937ed7e24f90540923c4f3cf7361c5072141b84",
    },
}


class SnapshotLoadError(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


def _fail(code: str, detail: str) -> NoReturn:
    raise SnapshotLoadError(code, detail)


def validate_snapshot_events(
    events: list[dict[str, Any]],
    *,
    generation_id: str,
    table: str,
    expected_run_id: str | None = None,
) -> None:
    if not events:
        _fail("CBL001_EMPTY_SHARD", table)
    keys: set[str] = set()
    for event in events:
        if event.get("operation") != "snapshot":
            _fail("CBL002_NON_SNAPSHOT_RECORD", str(event.get("operation")))
        if event.get("generation_id") != generation_id:
            _fail("CBL003_GENERATION_MISMATCH", str(event.get("generation_id")))
        if event.get("source_table") != table:
            _fail("CBL004_TABLE_MISMATCH", str(event.get("source_table")))
        lineage = {
            "source_system": "postgresql",
            "source_database": "changebridge",
            "source_schema": "public",
            **EXPECTED_CONTRACTS.get(table, {}),
        }
        if any(event.get(key) != value for key, value in lineage.items()):
            _fail("CBL018_LINEAGE_MISMATCH", str(event.get("event_id")))
        if expected_run_id is not None and event.get("run_id") != expected_run_id:
            _fail("CBL019_RUN_MISMATCH", str(event.get("run_id")))
        if event.get("source_position") != {
            "kind": "postgres_lsn",
            "value": EXPECTED_FRONTIER,
        }:
            _fail("CBL005_FRONTIER_MISMATCH", repr(event.get("source_position")))
        if event.get("before") is not None or not isinstance(event.get("after"), Mapping):
            _fail("CBL006_IMAGE_MISMATCH", str(event.get("event_id")))
        primary_key = event.get("primary_key")
        if not isinstance(primary_key, list) or len(primary_key) != 1:
            _fail("CBL007_PRIMARY_KEY", repr(primary_key))
        key = str(primary_key[0].get("value"))
        if key in keys:
            _fail("CBL008_DUPLICATE_KEY", key)
        keys.add(key)


def shard_identity(
    *, generation_id: str, table: str, events: list[dict[str, Any]]
) -> dict[str, str]:
    material = {
        "generation_id": generation_id,
        "source_table": table,
        "event_ids": [event["event_id"] for event in events],
        "payload_digests": [event["payload_digest"] for event in events],
        "snapshot_frontier": EXPECTED_FRONTIER,
    }
    input_digest = semantic_digest(material, domain="stage23-snapshot-shard-input")
    shard_id = f"snapshot-{table}-001"
    idempotency_key = semantic_digest(
        {"generation_id": generation_id, "shard_id": shard_id, "input_digest": input_digest},
        domain="stage23-shard-idempotency",
    )
    commit_token = semantic_digest(
        {"generation_id": generation_id, "shard_id": shard_id, "input_digest": input_digest},
        domain="stage23-target-commit-token",
    )
    return {
        "shard_id": shard_id,
        "input_digest": input_digest,
        "idempotency_key": idempotency_key,
        "commit_token": commit_token,
    }


class SnapshotLoader:
    def __init__(self, registry: GenerationRegistry, iceberg: IcebergSnapshotAdapter) -> None:
        self.registry = registry
        self.iceberg = iceberg

    def load_shard(
        self,
        *,
        generation_id: str,
        table: str,
        events: list[dict[str, Any]],
        fault: str | None = None,
    ) -> dict[str, Any]:
        generation = self.registry.get_generation(generation_id)
        assert generation is not None
        validate_snapshot_events(
            events,
            generation_id=generation_id,
            table=table,
            expected_run_id=str(generation["run_id"]),
        )
        identity = shard_identity(generation_id=generation_id, table=table, events=events)
        shard = self.registry.claim_shard(
            generation_id=generation_id,
            shard_id=identity["shard_id"],
            source_table=table,
            input_digest=identity["input_digest"],
            row_count=len(events),
            idempotency_key=identity["idempotency_key"],
            commit_token=identity["commit_token"],
        )
        if shard["state"] == "RECONCILED":
            committed = self.iceberg.snapshot_for_token(table, identity["commit_token"])
            if committed is None:
                _fail("CBL009_LEDGER_WITHOUT_ICEBERG", identity["commit_token"])
            result = self.registry.target_commit(generation_id, identity["commit_token"])
            assert result is not None
            return {**result, "idempotent_replay": True}
        if fault == "before_staging":
            raise SnapshotLoadError("CBL010_INJECTED_BEFORE_STAGING", table)
        if shard["state"] == "CLAIMED":
            self.registry.mark_shard_state(generation_id, identity["shard_id"], "STAGED")
        if fault == "during_staging":
            raise SnapshotLoadError("CBL011_INJECTED_DURING_STAGING", table)

        committed = self.iceberg.append_snapshot(
            table=table,
            events=events,
            shard_id=identity["shard_id"],
            commit_token=identity["commit_token"],
            input_digest=identity["input_digest"],
        )
        if fault == "process_exit_after_commit":
            os._exit(86)
        if fault == "after_commit":
            raise SnapshotLoadError("CBL012_INJECTED_AFTER_COMMIT", table)

        table_result = self.iceberg.verify_table(table)
        primary_key_name = str(events[0]["primary_key"][0]["name"])
        expected_rows = [event["after"] for event in events]
        expected_rows.sort(key=lambda row: str(row[primary_key_name]))
        expected_digest = semantic_digest(expected_rows, domain=f"source-table-state:{table}")
        if (
            table_result["row_count"] != len(events)
            or table_result["state_digest"] != expected_digest
        ):
            _fail("CBL013_TARGET_MISMATCH", repr(table_result))
        summary_digest = semantic_digest(
            committed["summary"], domain="stage23-iceberg-snapshot-summary"
        )
        record = self.registry.record_target_commit(
            {
                "generation_id": generation_id,
                "shard_id": identity["shard_id"],
                "commit_token": identity["commit_token"],
                "iceberg_table": self.iceberg.identifier(table),
                "physical_snapshot_id": committed["snapshot_id"],
                "input_digest": identity["input_digest"],
                "row_count": len(events),
                "logical_digest": table_result["state_digest"],
                "summary_digest": summary_digest,
                "reconciliation_state": "VERIFIED",
            }
        )
        self.registry.mark_shard_state(generation_id, identity["shard_id"], "COMMITTED")
        if fault == "after_ledger":
            raise SnapshotLoadError("CBL014_INJECTED_AFTER_LEDGER", table)
        self.registry.mark_shard_state(generation_id, identity["shard_id"], "RECONCILED")
        return {**record, "idempotent_replay": bool(committed["recovered"])}

    def admit_snapshot(
        self,
        *,
        generation_id: str,
        expected_table_digests: Mapping[str, str],
    ) -> dict[str, Any]:
        shards = self.registry.shards(generation_id)
        if len(shards) != 2 or any(row["state"] != "RECONCILED" for row in shards):
            _fail("CBL015_INCOMPLETE_SHARD_SET", repr(shards))
        table_results = {
            table: self.iceberg.verify_table(table) for table in sorted(EXPECTED_COUNTS)
        }
        for table, expected_count in EXPECTED_COUNTS.items():
            actual = table_results[table]
            if actual["row_count"] != expected_count:
                _fail("CBL016_COUNT_MISMATCH", f"{table}:{actual['row_count']}")
            if actual["state_digest"] != expected_table_digests[table]:
                _fail("CBL017_DIGEST_MISMATCH", table)
        proof = {
            "contract_version": "snapshot-admission-proof/1.0.0",
            "generation_id": generation_id,
            "snapshot_frontier": {
                "kind": "postgres_lsn",
                "value": EXPECTED_FRONTIER,
            },
            "table_results": table_results,
            "post_s_cdc_applied": 0,
            "all_commits_reconciled": True,
            "active_or_foreign_mutations": 0,
            "verdict": "PASS",
        }
        receipt = self.registry.record_admission_proof(generation_id, proof)
        generation = self.registry.get_generation(generation_id)
        assert generation is not None
        transitioned = self.registry.transition(
            generation_id,
            expected_revision=int(generation["revision"]),
            to_state="CDC_APPLYING",
            actor="stage23-snapshot-loader",
            decision={"admission_proof_digest": receipt["proof_digest"]},
        )
        return {"proof": proof, "receipt": receipt, "generation": transitioned}
