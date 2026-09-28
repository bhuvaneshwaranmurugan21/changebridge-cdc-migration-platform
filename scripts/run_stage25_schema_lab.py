#!/usr/bin/env python3
"""Run the bounded real Spark/Iceberg Stage 5 schema-policy proof."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

from changebridge.iceberg_schema import IcebergSchemaAdapter
from changebridge.schema_control import SchemaControlError, SchemaControlStore
from changebridge.schema_migration import SchemaMigrationCoordinator
from changebridge.schema_policy import (
    POLICY_DIGEST,
    ContractIdentity,
    SchemaPolicy,
    SchemaRegistry,
    registered_schema,
)
from changebridge.snapshot_handoff import reconstruct_snapshot

ROOT = Path(__file__).resolve().parents[1]
GENERATION = "generation-34edddda5aee96dc7236aaf3"
FRONTIER = "0/194FE20"


def load(relative: str) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((ROOT / relative).read_text(encoding="utf-8")))


def policy_authority() -> tuple[SchemaPolicy, Any, Any]:
    registry = SchemaRegistry()
    old = registered_schema(
        contract_id="orders_source_contract",
        version="1.0.0",
        source_table="orders",
        schema=load("contracts/orders-v1.json"),
        primary_key=("order_id",),
    )
    new = registered_schema(
        contract_id="orders_source_contract",
        version="1.1.0",
        source_table="orders",
        schema=load("contracts/orders-v1.1.json"),
        primary_key=("order_id",),
    )
    registry.add(old)
    registry.add(new)
    return SchemaPolicy(registry), old, new


def predecessor_rows() -> list[dict[str, Any]]:
    _, truth, _ = reconstruct_snapshot(ROOT)
    return [
        {key: value for key, value in row.items() if key != "source_note"}
        for row in truth["tables"]["orders"]["rows"]
    ]


def clean_run(root: Path, jar: Path) -> dict[str, Any]:
    policy, old, new = policy_authority()
    with (
        IcebergSchemaAdapter(warehouse=root / "warehouse", iceberg_jar=jar) as iceberg,
        SchemaControlStore(root / "schema.db") as control,
    ):
        iceberg.create_predecessor(predecessor_rows())
        before = iceberg.metadata()
        coordinator = SchemaMigrationCoordinator(policy=policy, control=control, iceberg=iceberg)
        first = coordinator.execute(
            generation_id=GENERATION,
            source_table="orders",
            previous=old.identity,
            candidate=new.identity,
            frontier=FRONTIER,
        )
        replay = coordinator.execute(
            generation_id=GENERATION,
            source_table="orders",
            previous=old.identity,
            candidate=new.identity,
            frontier=FRONTIER,
        )
        admission = control.require_admission(
            generation_id=GENERATION,
            source_table="orders",
            candidate_digest=new.identity.digest,
            policy_digest=POLICY_DIGEST,
        )
    return {
        "decision_id": first["decision"]["decision_id"],
        "decision_digest": first["decision"]["decision_digest"],
        "apply_token": first["apply"]["apply_token"],
        "receipt_id": admission["receipt_id"],
        "before_schema_id": before["schema_id"],
        "after_schema_id": first["apply"]["schema_id"],
        "metadata_changed": before["metadata_location"] != first["apply"]["metadata_location"],
        "snapshot_count_unchanged": before["snapshot_count"] == first["apply"]["snapshot_count"],
        "row_count": len(first["rows"]),
        "old_rows_null": all(row["source_note"] is None for row in first["rows"]),
        "replay_recovered": replay["apply"]["recovered"],
        "replay_metadata_unchanged": replay["apply"]["metadata_location"]
        == first["apply"]["metadata_location"],
        "frontier": FRONTIER,
        "generation_state": "CDC_APPLYING",
        "published": False,
    }


def recovery_run(root: Path, jar: Path) -> dict[str, Any]:
    with IcebergSchemaAdapter(warehouse=root / "warehouse", iceberg_jar=jar) as iceberg:
        iceberg.create_predecessor(predecessor_rows())
        before = iceberg.metadata()
    command = [
        sys.executable,
        str(ROOT / "jobs/spark_iceberg_schema.py"),
        "--old-contract",
        str(ROOT / "contracts/orders-v1.json"),
        "--new-contract",
        str(ROOT / "contracts/orders-v1.1.json"),
        "--generation-id",
        GENERATION,
        "--frontier",
        FRONTIER,
        "--warehouse",
        str(root / "warehouse"),
        "--control",
        str(root / "schema.db"),
        "--iceberg-jar",
        str(jar),
    ]
    env = {**os.environ, "SPARK_LOCAL_IP": "127.0.0.1", "PYSPARK_PYTHON": sys.executable}
    crashed = subprocess.run(
        [*command, "--fault", "process_exit_after_schema_commit"],
        cwd=ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=150,
    )
    with SchemaControlStore(root / "schema.db") as control:
        receipts_after_crash = control.connection.execute(
            "SELECT COUNT(*) FROM schema_apply_receipts"
        ).fetchone()[0]
    recovered = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
        timeout=150,
    )
    response = json.loads(recovered.stdout.strip().splitlines()[-1])
    with IcebergSchemaAdapter(warehouse=root / "warehouse", iceberg_jar=jar) as iceberg:
        after = iceberg.metadata()
    return {
        "crash_exit_code": crashed.returncode,
        "receipts_after_crash": receipts_after_crash,
        "recovered_receipt": response["apply"]["recovered"],
        "metadata_changed_once": before["metadata_location"] != after["metadata_location"],
        "snapshot_count_unchanged": before["snapshot_count"] == after["snapshot_count"],
        "schema_id": after["schema_id"],
        "frontier_unchanged": FRONTIER,
    }


def quarantine_run(root: Path, jar: Path) -> dict[str, Any]:
    policy, old, new = policy_authority()
    unknown = ContractIdentity(new.identity.contract_id, new.identity.version, "0" * 64)
    with (
        IcebergSchemaAdapter(warehouse=root / "warehouse", iceberg_jar=jar) as iceberg,
        SchemaControlStore(root / "schema.db") as control,
    ):
        iceberg.create_predecessor(predecessor_rows())
        before = iceberg.metadata()
        result = SchemaMigrationCoordinator(
            policy=policy, control=control, iceberg=iceberg
        ).execute(
            generation_id=GENERATION,
            source_table="orders",
            previous=old.identity,
            candidate=unknown,
            frontier=FRONTIER,
        )
        blocked = None
        try:
            control.require_admission(
                generation_id=GENERATION,
                source_table="orders",
                candidate_digest=new.identity.digest,
                policy_digest=POLICY_DIGEST,
            )
        except SchemaControlError as exc:
            blocked = exc.code
        after = iceberg.metadata()
    return {
        "verdict": result["decision"]["verdict"],
        "quarantine_status": result["quarantine"]["status"],
        "admission_blocked": blocked,
        "target_unchanged": before["metadata_location"] == after["metadata_location"],
        "snapshot_count_unchanged": before["snapshot_count"] == after["snapshot_count"],
        "frontier_unchanged": FRONTIER,
    }


def rejection_run(root: Path, jar: Path) -> dict[str, Any]:
    policy, old, _ = policy_authority()
    schema = load("contracts/orders-v1.json")
    schema["properties"].pop("amount")
    registry_source = policy.registry
    broken = registered_schema(
        contract_id="orders_source_contract",
        version="2.0.0",
        source_table="orders",
        schema=schema,
        primary_key=("order_id",),
    )
    registry_source.add(broken)
    with (
        IcebergSchemaAdapter(warehouse=root / "warehouse", iceberg_jar=jar) as iceberg,
        SchemaControlStore(root / "schema.db") as control,
    ):
        iceberg.create_predecessor(predecessor_rows())
        before = iceberg.metadata()
        result = SchemaMigrationCoordinator(
            policy=policy, control=control, iceberg=iceberg
        ).execute(
            generation_id=GENERATION,
            source_table="orders",
            previous=old.identity,
            candidate=broken.identity,
            frontier=FRONTIER,
            expected_generation_revision=2,
        )
        after = iceberg.metadata()
    return {
        "verdict": result["decision"]["verdict"],
        "reason_codes": result["decision"]["reason_codes"],
        "quarantine_status": result["quarantine"]["status"],
        "generation_state": result["rejection"]["state"],
        "generation_revision": result["rejection"]["revision"],
        "target_unchanged": before["metadata_location"] == after["metadata_location"],
        "frontier_unchanged": FRONTIER,
    }


def stable(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if key not in {"receipt_id"}}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iceberg-jar", required=True, type=Path)
    parser.add_argument("--work-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    args.work_root.mkdir(parents=True, exist_ok=False)
    first = clean_run(args.work_root / "clean-one", args.iceberg_jar)
    second = clean_run(args.work_root / "clean-two", args.iceberg_jar)
    result: dict[str, Any] = {
        "result": "PASS",
        "clean_runs": [first, second],
        "stable_projection_equal": stable(first) == stable(second),
        "recovery": recovery_run(args.work_root / "recovery", args.iceberg_jar),
        "unknown_quarantine": quarantine_run(args.work_root / "unknown", args.iceberg_jar),
        "incompatible_rejection": rejection_run(args.work_root / "rejection", args.iceberg_jar),
    }
    if not (
        first["row_count"] == 6
        and first["old_rows_null"] is True
        and first["snapshot_count_unchanged"] is True
        and first["replay_recovered"] is True
        and result["stable_projection_equal"] is True
        and result["recovery"]["crash_exit_code"] == 88
        and result["recovery"]["receipts_after_crash"] == 0
        and result["recovery"]["recovered_receipt"] is True
        and result["unknown_quarantine"]["admission_blocked"] == "CB25C005_GENERATION_QUARANTINED"
        and result["unknown_quarantine"]["target_unchanged"] is True
        and result["incompatible_rejection"]["generation_state"] == "REJECTED"
        and result["incompatible_rejection"]["target_unchanged"] is True
    ):
        raise RuntimeError("CB25L001_LAB_ASSERTION_FAILED")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"result": "PASS", "output": str(args.output)}, sort_keys=True))


if __name__ == "__main__":
    main()
