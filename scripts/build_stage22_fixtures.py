#!/usr/bin/env python3
"""Build deterministic synthetic Stage 2 JSON/JSONL/Parquet fixtures."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]

from changebridge.contracts import CANONICALIZATION_VERSION, schema_digest, semantic_digest
from changebridge.source_workload import materialize_workload, replay_workload

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests/fixtures/part2-stage2/valid"
OBJECTS = OUT / "objects"
BUILDER_VERSION = "changebridge-stage22-fixture-builder/1.0.0"


def render(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def advance_lsn(value: str, amount: int) -> str:
    high, low = (int(part, 16) for part in value.split("/"))
    combined = (high << 32) + low + amount
    return f"{combined >> 32:X}/{combined & 0xFFFFFFFF:X}"


def source_contract(table: str, version: str) -> tuple[str, str, dict[str, Any]]:
    if table == "orders" and version == "1.0.0":
        contract_id, path = "orders_source_contract", ROOT / "contracts/orders-v1.json"
    elif table == "orders" and version == "1.1.0":
        contract_id, path = "orders_source_contract_v1_1", ROOT / "contracts/orders-v1.1.json"
    else:
        contract_id, path = "order_items_source_contract", ROOT / "contracts/order-items-v1.json"
    schema = json.loads(path.read_text(encoding="utf-8"))
    return contract_id, schema_digest(schema), schema


def raw_record(
    event: dict[str, Any],
    *,
    operation: str,
    transaction_id: str,
    transaction_sequence: int,
    commit_lsn: str,
    generation_id: str,
    run_id: str,
    timestamp: str,
) -> dict[str, Any]:
    version = event["schema_version"].split("/")[-1]
    contract_id, digest, _ = source_contract(event["table"], version)
    return {
        "profile_id": "changebridge.synthetic-dms-s3.full-images",
        "profile_version": "1.0.0",
        "record_kind": "snapshot" if operation == "snapshot" else "cdc",
        "operation": operation,
        "source_system": "postgresql",
        "source_database": "changebridge",
        "source_schema": "public",
        "source_table": event["table"],
        "source_contract_id": contract_id,
        "source_contract_version": version,
        "source_contract_digest": digest,
        "source_schema_version": event["schema_version"],
        "source_schema_digest": digest,
        "primary_key": [
            {"name": f"{event['table'][:-1]}_id", "type": "string", "value": event["key"]}
        ],
        "before": deepcopy(event["before"]),
        "after": deepcopy(event["after"]),
        "transaction_id": transaction_id,
        "transaction_sequence": transaction_sequence,
        "event_sequence": event["event_sequence"],
        "commit_lsn": commit_lsn,
        "committed_at": timestamp,
        "ingested_at": "2024-03-01T00:00:10.000000Z",
        "run_id": run_id,
        "generation_id": generation_id,
    }


def main() -> None:
    boundary = json.loads(
        (ROOT / "evidence/part2/stage1/boundary-capture-report.json").read_text(encoding="utf-8")
    )
    run = boundary["runs"][0]
    stage1_manifest = json.loads(
        (ROOT / "evidence/part2/stage1/source-workload-manifest.json").read_text(encoding="utf-8")
    )
    history = json.loads(
        (ROOT / "evidence/part2/stage1/source-history-ledger.json").read_text(encoding="utf-8")
    )
    spec = materialize_workload(stage1_manifest["seed"], stage1_manifest["schema_set_digest"])
    truth = replay_workload(spec, through_phase="PRE_BOUNDARY")
    tx = {item["transaction_id"]: item for item in spec["transactions"]}
    snapshot_row = next(
        row for row in truth["tables"]["orders"]["rows"] if row["order_id"] == "order-001"
    )
    snapshot_event = {
        "table": "orders",
        "key": snapshot_row["order_id"],
        "before": None,
        "after": snapshot_row,
        "event_sequence": 1,
        "schema_version": "orders/1.1.0",
    }
    generation_id = run["generation_id"]
    run_id = "stage22-synthetic-normalization-run-001"
    frontier = run["snapshot_frontier"]["value"]
    positions = [advance_lsn(frontier, increment) for increment in (256, 512, 768, 1024)]
    records = [
        raw_record(
            snapshot_event,
            operation="snapshot",
            transaction_id=f"snapshot-batch:{generation_id}:orders",
            transaction_sequence=0,
            commit_lsn=frontier,
            generation_id=generation_id,
            run_id=run_id,
            timestamp="2024-03-01T00:00:00.000000Z",
        ),
        raw_record(
            tx["tx-002-multi-row"]["events"][0],
            operation="insert",
            transaction_id="tx-002-multi-row",
            transaction_sequence=2,
            commit_lsn=positions[0],
            generation_id=generation_id,
            run_id=run_id,
            timestamp="2024-03-01T00:00:01.000000Z",
        ),
        raw_record(
            tx["tx-004-update"]["events"][0],
            operation="update",
            transaction_id="tx-004-update",
            transaction_sequence=4,
            commit_lsn=positions[1],
            generation_id=generation_id,
            run_id=run_id,
            timestamp="2024-03-01T00:00:02.000000Z",
        ),
        raw_record(
            tx["tx-005-delete"]["events"][0],
            operation="delete",
            transaction_id="tx-005-delete",
            transaction_sequence=5,
            commit_lsn=positions[2],
            generation_id=generation_id,
            run_id=run_id,
            timestamp="2024-03-01T00:00:03.000000Z",
        ),
        raw_record(
            tx["tx-012-post-boundary"]["events"][0],
            operation="update",
            transaction_id="tx-012-post-boundary",
            transaction_sequence=12,
            commit_lsn=positions[3],
            generation_id=generation_id,
            run_id=run_id,
            timestamp="2024-03-01T00:00:04.000000Z",
        ),
    ]
    OBJECTS.mkdir(parents=True, exist_ok=True)
    json_bytes = render(records[:2]).encode("utf-8")
    (OBJECTS / "snapshot-insert.json").write_bytes(json_bytes)
    jsonl_bytes = ("\n".join(compact(row) for row in records[2:4]) + "\n").encode("utf-8")
    (OBJECTS / "update-delete.jsonl").write_bytes(jsonl_bytes)
    parquet_rows = [compact(records[4])]
    table = pa.table(
        {
            "record_json": pa.array(parquet_rows, type=pa.string()),
            "record_sha256": pa.array(
                [sha(row.encode("utf-8")) for row in parquet_rows], type=pa.string()
            ),
        }
    )
    pq.write_table(table, OBJECTS / "post-boundary.parquet", compression="snappy", version="2.6")
    profile = json.loads((ROOT / "contracts/transport-profile-stage22-v1.json").read_text())
    descriptors = [
        (
            "object-json-001",
            "objects/snapshot-insert.json",
            "json",
            2,
            frontier,
            positions[0],
            "orders_source_contract_v1_1",
            "1.1.0",
        ),
        (
            "object-jsonl-002",
            "objects/update-delete.jsonl",
            "jsonl",
            2,
            positions[0],
            positions[2],
            "orders_source_contract",
            "1.0.0",
        ),
        (
            "object-parquet-003",
            "objects/post-boundary.parquet",
            "parquet",
            1,
            positions[2],
            positions[3],
            "orders_source_contract_v1_1",
            "1.1.0",
        ),
    ]
    objects = []
    for sequence, descriptor in enumerate(descriptors, 1):
        object_id, relative, fmt, count, start, end, contract_id, version = descriptor
        path = OUT / relative
        _, digest, _ = source_contract("orders", version)
        objects.append(
            {
                "object_id": object_id,
                "path": relative,
                "format": fmt,
                "compression": "snappy" if fmt == "parquet" else "none",
                "byte_length": path.stat().st_size,
                "sha256": sha(path.read_bytes()),
                "row_count": count,
                "object_sequence": sequence,
                "source_table": "orders",
                "source_contract_id": contract_id,
                "source_contract_version": version,
                "source_contract_digest": digest,
                "source_schema_digest": digest,
                "start_exclusive_frontier": {"kind": "postgres_lsn", "value": start},
                "end_inclusive_frontier": {"kind": "postgres_lsn", "value": end},
            }
        )
    fixture_set_digest = semantic_digest(objects, domain="stage22-fixture-set")
    boundary_receipt_digest = sha(
        (ROOT / "evidence/part2/stage1/boundary-capture-report.json").read_bytes()
    )
    base = {
        "manifest_version": "raw-landing-manifest/1.0.0",
        "canonicalization_version": CANONICALIZATION_VERSION,
        "profile_id": profile["profile_id"],
        "profile_version": profile["profile_version"],
        "producer_settings_digest": semantic_digest(
            profile["producer_settings"], domain="stage22-producer-settings"
        ),
        "fixture_set_digest": fixture_set_digest,
        "provenance": "SYNTHETIC_CONTRACT_FIXTURE",
        "creation_tool_version": BUILDER_VERSION,
        "run_id": run_id,
        "generation_id": generation_id,
        "workload_id": stage1_manifest["workload_id"],
        "source_history_digest": history["committed_history_digest"],
        "stage1_boundary_receipt_digest": boundary_receipt_digest,
        "stage1_snapshot_frontier": run["snapshot_frontier"],
        "start_exclusive_frontier": run["snapshot_frontier"],
        "object_end_frontier": {"kind": "postgres_lsn", "value": positions[3]},
        "observed_at": "2024-03-01T00:00:10.000000Z",
        "max_record_bytes": 262144,
        "declared_object_paths": [item["path"] for item in objects],
        "objects": objects,
    }
    manifest = {**base, "manifest_id": semantic_digest(base, domain="raw-landing-manifest")}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "manifest.json").write_text(render(manifest), encoding="utf-8")
    provenance = {
        "classification": "SYNTHETIC_CONTRACT_FIXTURE",
        "builder_version": BUILDER_VERSION,
        "derived_from_workload_id": stage1_manifest["workload_id"],
        "derived_from_history_digest": history["committed_history_digest"],
        "managed_dms_output": False,
        "record_semantic_digests": [
            semantic_digest(row, domain="raw-transport-record") for row in records
        ],
    }
    (OUT / "provenance.json").write_text(render(provenance), encoding="utf-8")


if __name__ == "__main__":
    main()
