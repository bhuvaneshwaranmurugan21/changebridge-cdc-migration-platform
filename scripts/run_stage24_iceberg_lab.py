#!/usr/bin/env python3
"""Run the bounded real Spark/Iceberg Stage 4 transactional-apply proof."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from changebridge.cdc_apply import CDCApplyCoordinator
from changebridge.cdc_control import CDCControlStore
from changebridge.generation_registry import (
    GenerationRegistry,
    generation_namespace,
    generation_warehouse,
)
from changebridge.iceberg_cdc import IcebergCDCAdapter, IcebergCDCError
from changebridge.reference_cdc import ReferenceCDCStore
from changebridge.snapshot_handoff import normalize_full_handoff, reconstruct_snapshot
from changebridge.snapshot_loader import SnapshotLoader
from changebridge.transaction_assembler import assemble_transactions

ROOT = Path(__file__).resolve().parents[1]


def load(relative: str) -> Any:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def generation_record(run_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    spec, truth, boundary = reconstruct_snapshot(ROOT)
    generation_id = str(boundary["generation_id"])
    namespace = generation_namespace(generation_id)
    warehouse = generation_warehouse((run_root / "warehouse-root").resolve(), generation_id)
    return (
        {
            "generation_id": generation_id,
            "workload_id": spec["workload_id"],
            "run_id": "stage23-full-snapshot-handoff-001",
            "snapshot_frontier": "0/194FB20",
            "schema_set_digest": spec["schema_set_digest"],
            "canonicalization_profile": "changebridge-canonical-json/1.0.0",
            "warehouse_path": str(warehouse),
            "namespace": namespace,
            "table_map": {
                table: f"stage23.{namespace}.{table}"
                for table in ("order_items", "orders")
            },
        },
        truth,
    )


def plan() -> dict[str, Any]:
    events = load("tests/fixtures/part2-stage4/canonical-events.json")
    manifest = load("tests/fixtures/part2-stage4/apply-manifest.json")
    return assemble_transactions(
        events,
        manifest,
        admitted_schema_digests={str(events[0]["source_schema_digest"])},
    )[0]


def prepare(run_root: Path, jar: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    record, truth = generation_record(run_root)
    bundle = normalize_full_handoff(ROOT, ROOT / "tests/fixtures/part2-stage3/handoff")
    generation_id = str(record["generation_id"])
    with GenerationRegistry(run_root / "generation.db") as registry:
        registry.register_generation(record)
        registry.transition(
            generation_id,
            expected_revision=0,
            to_state="SNAPSHOT_LOADING",
            actor="stage24-real-lab",
            decision={"reason": "restore accepted Stage 3 candidate"},
        )
        with IcebergCDCAdapter(
            warehouse=Path(str(record["warehouse_path"])),
            namespace=str(record["namespace"]),
            iceberg_jar=jar,
        ) as iceberg:
            loader = SnapshotLoader(registry, iceberg)
            for table in ("orders", "order_items"):
                events = [
                    event
                    for event in bundle.canonical
                    if event["operation"] == "snapshot" and event["source_table"] == table
                ]
                loader.load_shard(generation_id=generation_id, table=table, events=events)
            loader.admit_snapshot(
                generation_id=generation_id,
                expected_table_digests={
                    table: truth["tables"][table]["state_digest"] for table in truth["tables"]
                },
            )
    return record, truth


def clean_run(run_root: Path, jar: Path) -> dict[str, Any]:
    record, truth = prepare(run_root, jar)
    transaction = plan()
    with ReferenceCDCStore(run_root / "reference.db") as reference:
        reference.initialize(truth["tables"])
        reference.apply(transaction)
        reference_results = {
            table: reference.table_result(table) for table in ("order_items", "orders")
        }
    with (
        GenerationRegistry(run_root / "generation.db") as registry,
        CDCControlStore(run_root / "cdc.db") as control,
        IcebergCDCAdapter(
            warehouse=Path(str(record["warehouse_path"])),
            namespace=str(record["namespace"]),
            iceberg_jar=jar,
        ) as iceberg,
    ):
        coordinator = CDCApplyCoordinator(registry=registry, control=control, iceberg=iceberg)
        result = coordinator.apply_transaction(transaction)
        target = {table: iceberg.verify_table(table) for table in ("order_items", "orders")}
        replay = coordinator.apply_transaction(transaction)
        generation = registry.get_generation(str(record["generation_id"]))
        assert generation is not None
        tombstones = control.tombstones(str(record["generation_id"]))
    return {
        "generation_id": record["generation_id"],
        "transaction_id": transaction["transaction_id"],
        "transaction_digest": transaction["transaction_digest"],
        "checkpoint": result["checkpoint"],
        "target": target,
        "reference": reference_results,
        "differential_equal": all(
            target[table]["row_count"] == reference_results[table]["row_count"]
            and target[table]["state_digest"] == reference_results[table]["state_digest"]
            for table in target
        ),
        "idempotent_replay": replay["idempotent_replay"],
        "receipt_count": len(result["receipts"]),
        "tombstone_count": len(tombstones),
        "generation_state": generation["state"],
        "published": False,
    }


def recovery_run(run_root: Path, jar: Path) -> dict[str, Any]:
    record, _ = prepare(run_root, jar)
    transaction = plan()
    plan_path = run_root / "plan.json"
    plan_path.write_text(json.dumps(transaction, sort_keys=True), encoding="utf-8")
    command = [
        sys.executable,
        str(ROOT / "jobs/spark_iceberg_apply.py"),
        "--plan", str(plan_path),
        "--generation-registry", str(run_root / "generation.db"),
        "--cdc-control", str(run_root / "cdc.db"),
        "--warehouse", str(record["warehouse_path"]),
        "--namespace", str(record["namespace"]),
        "--iceberg-jar", str(jar),
    ]
    env = {**os.environ, "SPARK_LOCAL_IP": "127.0.0.1", "PYSPARK_PYTHON": sys.executable}
    crashed = subprocess.run(
        [*command, "--fault", "process_exit_after_table_commit:orders"],
        cwd=ROOT, env=env, check=False, capture_output=True, text=True, timeout=150,
    )
    with CDCControlStore(run_root / "cdc.db") as control:
        after_crash = control.checkpoint(str(record["generation_id"]))
        receipts_after_crash = control.receipts(
            str(record["generation_id"]), str(transaction["transaction_id"])
        )
    recovered = subprocess.run(
        command, cwd=ROOT, env=env, check=True, capture_output=True, text=True, timeout=150,
    )
    response = json.loads(recovered.stdout.strip().splitlines()[-1])
    with IcebergCDCAdapter(
        warehouse=Path(str(record["warehouse_path"])),
        namespace=str(record["namespace"]), iceberg_jar=jar,
    ) as iceberg:
        orders_snapshots = iceberg.snapshot_count("orders")
    return {
        "crash_exit_code": crashed.returncode,
        "checkpoint_after_crash": after_crash,
        "receipts_after_crash": len(receipts_after_crash),
        "recovered_receipt": response["receipts"][0]["recovered"] == 1,
        "final_checkpoint": response["checkpoint"],
        "orders_snapshot_count": orders_snapshots,
        "recovered_without_rewrite": orders_snapshots == 2,
    }


def drift_run(run_root: Path, jar: Path) -> dict[str, Any]:
    record, _ = prepare(run_root, jar)
    transaction = plan()
    try:
        with (
            GenerationRegistry(run_root / "generation.db") as registry,
            CDCControlStore(run_root / "cdc.db") as control,
            IcebergCDCAdapter(
                warehouse=Path(str(record["warehouse_path"])),
                namespace=str(record["namespace"]), iceberg_jar=jar,
            ) as iceberg,
        ):
            iceberg.spark.sql(
                f"UPDATE {iceberg.identifier('orders')} SET amount=999 WHERE order_id='order-004'"
            ).collect()
            CDCApplyCoordinator(
                registry=registry, control=control, iceberg=iceberg
            ).apply_transaction(transaction)
    except IcebergCDCError as exc:
        return {"failed_closed": True, "reason_code": exc.code}
    return {"failed_closed": False, "reason_code": None}


def stable_projection(run: dict[str, Any]) -> dict[str, Any]:
    stable = {key: value for key, value in run.items() if key != "checkpoint"}
    stable["checkpoint_frontier"] = run["checkpoint"]["source_frontier"]
    return stable


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
        "stable_projection_equal": stable_projection(first) == stable_projection(second),
        "recovery": recovery_run(args.work_root / "recovery", args.iceberg_jar),
        "drift": drift_run(args.work_root / "drift", args.iceberg_jar),
    }
    assertions = (
        first["differential_equal"] is True
        and first["idempotent_replay"] is True
        and first["generation_state"] == "CDC_APPLYING"
        and first["published"] is False
        and result["stable_projection_equal"] is True
        and result["recovery"]["crash_exit_code"] == 87
        and result["recovery"]["checkpoint_after_crash"]["source_frontier"] == "0/194FB20"
        and result["recovery"]["final_checkpoint"]["source_frontier"] == "0/194FE20"
        and result["recovery"]["recovered_without_rewrite"] is True
        and result["drift"] == {
            "failed_closed": True,
            "reason_code": "CB24I005_TARGET_BEFORE_IMAGE_MISMATCH",
        }
    )
    if not assertions:
        raise RuntimeError("CB24L001_LAB_ASSERTION_FAILED")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"result": "PASS", "output": str(args.output)}, sort_keys=True))


if __name__ == "__main__":
    main()
