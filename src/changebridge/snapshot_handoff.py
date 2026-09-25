"""Complete deterministic Stage 1 snapshot to Stage 2 normalized handoff bridge."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]

from changebridge.contracts import CANONICALIZATION_VERSION, schema_digest, semantic_digest
from changebridge.normalizer import NormalizationBundle, normalize_manifest
from changebridge.source_workload import materialize_workload, replay_workload

STAGE23_HANDOFF_VERSION = "changebridge-stage23-full-handoff/1.0.0"
STAGE22_PROFILE_BUILDER_VERSION = "changebridge-stage22-fixture-builder/1.0.0"
EXPECTED_FRONTIER = "0/194FB20"
EXPECTED_COUNTS = {"order_items": 66, "orders": 6}
EXPECTED_WHOLE_STATE_DIGEST = "9089d027e04c0a78752776e679bed109348960d04f64c926b56a665a9e83439b"


def _render(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load(root: Path, relative: str) -> dict[str, Any]:
    value = json.loads((root / relative).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(relative)
    return value


def _advance_lsn(value: str, amount: int) -> str:
    high, low = (int(part, 16) for part in value.split("/"))
    combined = (high << 32) + low + amount
    return f"{combined >> 32:X}/{combined & 0xFFFFFFFF:X}"


def _contract(root: Path, table: str) -> tuple[str, str, str, dict[str, Any]]:
    if table == "orders":
        contract_id, version, relative = (
            "orders_source_contract_v1_1",
            "1.1.0",
            "contracts/orders-v1.1.json",
        )
    elif table == "order_items":
        contract_id, version, relative = (
            "order_items_source_contract",
            "1.0.0",
            "contracts/order-items-v1.json",
        )
    else:
        raise ValueError(table)
    schema = _load(root, relative)
    return contract_id, version, schema_digest(schema), schema


def _raw_record(
    root: Path,
    *,
    table: str,
    key: str,
    after: dict[str, Any] | None,
    before: dict[str, Any] | None,
    operation: str,
    transaction_id: str,
    transaction_sequence: int,
    event_sequence: int,
    commit_lsn: str,
    generation_id: str,
    run_id: str,
    timestamp: str,
) -> dict[str, Any]:
    contract_id, version, digest, _ = _contract(root, table)
    key_name = "order_id" if table == "orders" else "item_id"
    return {
        "profile_id": "changebridge.synthetic-dms-s3.full-images",
        "profile_version": "1.0.0",
        "record_kind": "snapshot" if operation == "snapshot" else "cdc",
        "operation": operation,
        "source_system": "postgresql",
        "source_database": "changebridge",
        "source_schema": "public",
        "source_table": table,
        "source_contract_id": contract_id,
        "source_contract_version": version,
        "source_contract_digest": digest,
        "source_schema_version": f"{table}/{version}",
        "source_schema_digest": digest,
        "primary_key": [{"name": key_name, "type": "string", "value": key}],
        "before": deepcopy(before),
        "after": deepcopy(after),
        "transaction_id": transaction_id,
        "transaction_sequence": transaction_sequence,
        "event_sequence": event_sequence,
        "commit_lsn": commit_lsn,
        "committed_at": timestamp,
        "ingested_at": "2024-03-01T00:00:10.000000Z",
        "run_id": run_id,
        "generation_id": generation_id,
    }


def reconstruct_snapshot(root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    workload = _load(root, "evidence/part2/stage1/source-workload-manifest.json")
    boundary = _load(root, "evidence/part2/stage1/boundary-capture-report.json")
    spec = materialize_workload(workload["seed"], workload["schema_set_digest"])
    truth = replay_workload(spec, through_phase="PRE_BOUNDARY")
    counts = {name: table["row_count"] for name, table in truth["tables"].items()}
    if counts != EXPECTED_COUNTS:
        raise ValueError(f"CBH001_SNAPSHOT_COUNTS:{counts!r}")
    if truth["whole_state_digest"] != EXPECTED_WHOLE_STATE_DIGEST:
        raise ValueError(f"CBH002_SNAPSHOT_DIGEST:{truth['whole_state_digest']}")
    run = boundary["runs"][0]
    if run["snapshot_frontier"]["value"] != EXPECTED_FRONTIER:
        raise ValueError(f"CBH003_FRONTIER:{run['snapshot_frontier']!r}")
    if run["snapshot_whole_state_digest"] != EXPECTED_WHOLE_STATE_DIGEST:
        raise ValueError("CBH004_BOUNDARY_DIGEST")
    return spec, truth, run


def build_full_handoff(root: Path, output: Path) -> dict[str, Any]:
    """Create an immutable synthetic profile fixture containing all 72 snapshot rows."""

    spec, truth, run = reconstruct_snapshot(root)
    if output.exists():
        raise FileExistsError(output)
    objects_dir = output / "objects"
    objects_dir.mkdir(parents=True)
    generation_id = run["generation_id"]
    run_id = "stage23-full-snapshot-handoff-001"
    frontier = run["snapshot_frontier"]["value"]

    orders = [
        _raw_record(
            root,
            table="orders",
            key=row["order_id"],
            after=row,
            before=None,
            operation="snapshot",
            transaction_id=f"snapshot-batch:{generation_id}:orders",
            transaction_sequence=0,
            event_sequence=index,
            commit_lsn=frontier,
            generation_id=generation_id,
            run_id=run_id,
            timestamp="2024-03-01T00:00:00.000000Z",
        )
        for index, row in enumerate(truth["tables"]["orders"]["rows"], 1)
    ]
    order_items = [
        _raw_record(
            root,
            table="order_items",
            key=row["item_id"],
            after=row,
            before=None,
            operation="snapshot",
            transaction_id=f"snapshot-batch:{generation_id}:order_items",
            transaction_sequence=1,
            event_sequence=index,
            commit_lsn=frontier,
            generation_id=generation_id,
            run_id=run_id,
            timestamp="2024-03-01T00:00:00.000000Z",
        )
        for index, row in enumerate(truth["tables"]["order_items"]["rows"], 1)
    ]
    post_transaction = next(
        tx for tx in spec["transactions"] if tx["transaction_id"] == "tx-012-post-boundary"
    )
    post_event = post_transaction["events"][0]
    post_lsn = _advance_lsn(frontier, 768)
    post_record = _raw_record(
        root,
        table="orders",
        key=post_event["key"],
        after=post_event["after"],
        before=post_event["before"],
        operation="update",
        transaction_id=post_transaction["transaction_id"],
        transaction_sequence=post_transaction["transaction_sequence"],
        event_sequence=post_event["event_sequence"],
        commit_lsn=post_lsn,
        generation_id=generation_id,
        run_id=run_id,
        timestamp="2024-03-01T00:00:04.000000Z",
    )

    order_bytes = _render(orders).encode("utf-8")
    (objects_dir / "orders-snapshot.json").write_bytes(order_bytes)
    item_bytes = ("\n".join(_compact(row) for row in order_items) + "\n").encode("utf-8")
    (objects_dir / "order-items-snapshot.jsonl").write_bytes(item_bytes)
    post_json = _compact(post_record)
    pq.write_table(
        pa.table(
            {
                "record_json": pa.array([post_json], type=pa.string()),
                "record_sha256": pa.array([_sha(post_json.encode("utf-8"))], type=pa.string()),
            }
        ),
        objects_dir / "post-s-cdc.parquet",
        compression="snappy",
        version="2.6",
    )
    positions = [_advance_lsn(frontier, amount) for amount in (256, 512, 768)]
    descriptors = [
        ("snapshot-orders-001", "objects/orders-snapshot.json", "json", 6, "orders"),
        (
            "snapshot-order-items-002",
            "objects/order-items-snapshot.jsonl",
            "jsonl",
            66,
            "order_items",
        ),
        ("post-s-cdc-003", "objects/post-s-cdc.parquet", "parquet", 1, "orders"),
    ]
    objects: list[dict[str, Any]] = []
    prior = frontier
    for sequence, (object_id, relative, fmt, count, table) in enumerate(descriptors, 1):
        contract_id, version, digest, _ = _contract(root, table)
        path = output / relative
        end = positions[sequence - 1]
        objects.append(
            {
                "object_id": object_id,
                "path": relative,
                "format": fmt,
                "compression": "snappy" if fmt == "parquet" else "none",
                "byte_length": path.stat().st_size,
                "sha256": _sha(path.read_bytes()),
                "row_count": count,
                "object_sequence": sequence,
                "source_table": table,
                "source_contract_id": contract_id,
                "source_contract_version": version,
                "source_contract_digest": digest,
                "source_schema_digest": digest,
                "start_exclusive_frontier": {"kind": "postgres_lsn", "value": prior},
                "end_inclusive_frontier": {"kind": "postgres_lsn", "value": end},
            }
        )
        prior = end

    profile = _load(root, "contracts/transport-profile-stage22-v1.json")
    history = _load(root, "evidence/part2/stage1/source-history-ledger.json")
    workload = _load(root, "evidence/part2/stage1/source-workload-manifest.json")
    base = {
        "manifest_version": "raw-landing-manifest/1.0.0",
        "canonicalization_version": CANONICALIZATION_VERSION,
        "profile_id": profile["profile_id"],
        "profile_version": profile["profile_version"],
        "producer_settings_digest": semantic_digest(
            profile["producer_settings"], domain="stage22-producer-settings"
        ),
        "fixture_set_digest": semantic_digest(objects, domain="stage23-handoff-fixture-set"),
        "provenance": "SYNTHETIC_CONTRACT_FIXTURE",
        # The accepted Stage 2 manifest schema intentionally closes this field.
        # Stage 3 provenance below records the bridge version without changing
        # or weakening that normalization authority.
        "creation_tool_version": STAGE22_PROFILE_BUILDER_VERSION,
        "run_id": run_id,
        "generation_id": generation_id,
        "workload_id": workload["workload_id"],
        "source_history_digest": history["committed_history_digest"],
        "stage1_boundary_receipt_digest": _sha(
            (root / "evidence/part2/stage1/boundary-capture-report.json").read_bytes()
        ),
        "stage1_snapshot_frontier": run["snapshot_frontier"],
        "start_exclusive_frontier": run["snapshot_frontier"],
        "object_end_frontier": {"kind": "postgres_lsn", "value": positions[-1]},
        "observed_at": "2024-03-01T00:00:10.000000Z",
        "max_record_bytes": 262144,
        "declared_object_paths": [row["path"] for row in objects],
        "objects": objects,
    }
    manifest = {**base, "manifest_id": semantic_digest(base, domain="raw-landing-manifest")}
    (output / "manifest.json").write_text(_render(manifest), encoding="utf-8")
    provenance = {
        "classification": "SYNTHETIC_CONTRACT_FIXTURE",
        "builder_version": STAGE23_HANDOFF_VERSION,
        "derived_from_workload_id": spec["workload_id"],
        "source_snapshot_whole_state_digest": truth["whole_state_digest"],
        "snapshot_counts": EXPECTED_COUNTS,
        "snapshot_record_count": len(orders) + len(order_items),
        "post_s_cdc_record_count": 1,
        "managed_dms_output": False,
    }
    (output / "provenance.json").write_text(_render(provenance), encoding="utf-8")
    return manifest


def normalize_full_handoff(root: Path, handoff: Path) -> NormalizationBundle:
    manifest = _load(handoff, "manifest.json")
    manifest_schema = _load(root, "contracts/raw-landing-manifest-v1.json")
    envelope_schema = _load(root, "contracts/cdc-envelope-v1.schema.json")
    source_contracts: dict[tuple[str, str], tuple[str, dict[str, Any]]] = {}
    for table in ("orders", "order_items"):
        contract_id, version, digest, schema = _contract(root, table)
        source_contracts[(contract_id, version)] = (digest, schema)
    bundle = normalize_manifest(
        handoff,
        manifest,
        manifest_schema=manifest_schema,
        envelope_schema=envelope_schema,
        source_contracts=source_contracts,
    )
    snapshots = [event for event in bundle.canonical if event["operation"] == "snapshot"]
    post_s = [event for event in bundle.canonical if event["operation"] != "snapshot"]
    counts = {
        table: sum(event["source_table"] == table for event in snapshots)
        for table in EXPECTED_COUNTS
    }
    if bundle.quarantine or counts != EXPECTED_COUNTS or len(snapshots) != 72 or len(post_s) != 1:
        raise ValueError(
            f"CBH005_NORMALIZED_HANDOFF:counts={counts!r},"
            f"quarantine={len(bundle.quarantine)},post_s={len(post_s)}"
        )
    return bundle
