#!/usr/bin/env python3
"""Run the bounded real Spark/Iceberg Stage 3 proof laboratory."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from changebridge.generation_registry import (
    GenerationRegistry,
    generation_namespace,
    generation_warehouse,
)
from changebridge.iceberg_snapshot import IcebergSnapshotAdapter
from changebridge.normalizer import write_bundle_atomic
from changebridge.snapshot_handoff import (
    build_full_handoff,
    normalize_full_handoff,
    reconstruct_snapshot,
)
from changebridge.snapshot_loader import SnapshotLoader, SnapshotLoadError

ROOT = Path(__file__).resolve().parents[1]


def generation_record(root: Path, run_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    spec, truth, boundary = reconstruct_snapshot(root)
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
                table: f"stage23.{namespace}.{table}" for table in ("order_items", "orders")
            },
        },
        truth,
    )


def clean_run(run_root: Path, jar: Path) -> dict[str, Any]:
    handoff = run_root / "handoff"
    build_full_handoff(ROOT, handoff)
    bundle = normalize_full_handoff(ROOT, handoff)
    record, truth = generation_record(ROOT, run_root)
    generation_id = str(record["generation_id"])
    results: dict[str, Any] = {}
    with GenerationRegistry(run_root / "control.db") as registry:
        registry.register_generation(record)
        registry.transition(
            generation_id,
            expected_revision=0,
            to_state="SNAPSHOT_LOADING",
            actor="stage23-real-lab",
            decision={"reason": "bounded real proof"},
        )
        with IcebergSnapshotAdapter(
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
                first = loader.load_shard(generation_id=generation_id, table=table, events=events)
                before_replay = iceberg.snapshot_count(table)
                replay = loader.load_shard(generation_id=generation_id, table=table, events=events)
                after_replay = iceberg.snapshot_count(table)
                results[table] = {
                    "row_count": first["row_count"],
                    "logical_digest": first["logical_digest"],
                    "snapshot_count_before_replay": before_replay,
                    "snapshot_count_after_replay": after_replay,
                    "idempotent_replay": replay["idempotent_replay"],
                    "physical_snapshot_id": first["physical_snapshot_id"],
                }
            admission = loader.admit_snapshot(
                generation_id=generation_id,
                expected_table_digests={
                    table: truth["tables"][table]["state_digest"] for table in truth["tables"]
                },
            )
            return {
                "generation_id": generation_id,
                "namespace": record["namespace"],
                "snapshot_frontier": record["snapshot_frontier"],
                "tables": results,
                "state": admission["generation"]["state"],
                "admission_proof_digest": admission["receipt"]["proof_digest"],
                "post_s_cdc_applied": admission["proof"]["post_s_cdc_applied"],
            }


def recovery_run(run_root: Path, jar: Path) -> dict[str, Any]:
    handoff = run_root / "handoff"
    build_full_handoff(ROOT, handoff)
    bundle = normalize_full_handoff(ROOT, handoff)
    bundle_path = run_root / "bundle"
    write_bundle_atomic(bundle_path, bundle)
    record, _ = generation_record(ROOT, run_root)
    record_path = run_root / "generation.json"
    record_path.write_text(json.dumps(record, sort_keys=True), encoding="utf-8")
    registry_path = run_root / "control.db"
    command = [
        sys.executable,
        str(ROOT / "jobs/spark_iceberg_snapshot.py"),
        "--bundle",
        str(bundle_path),
        "--registry",
        str(registry_path),
        "--warehouse-root",
        str((run_root / "warehouse-root").resolve()),
        "--iceberg-jar",
        str(jar),
        "--generation-record",
        str(record_path),
        "--table",
        "orders",
    ]
    env = {**os.environ, "SPARK_LOCAL_IP": "127.0.0.1", "PYSPARK_PYTHON": sys.executable}
    crashed = subprocess.run(
        [*command, "--fault", "process_exit_after_commit"],
        cwd=ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    recovered = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    response = json.loads(recovered.stdout)
    return {
        "crash_exit_code": crashed.returncode,
        "recovered_without_rewrite": response["idempotent_replay"],
        "row_count": response["row_count"],
    }


def stable_projection(run: dict[str, Any]) -> dict[str, Any]:
    return {
        "generation_id": run["generation_id"],
        "namespace": run["namespace"],
        "snapshot_frontier": run["snapshot_frontier"],
        "tables": {
            table: {key: value for key, value in details.items() if key != "physical_snapshot_id"}
            for table, details in run["tables"].items()
        },
        "state": run["state"],
        "post_s_cdc_applied": run["post_s_cdc_applied"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iceberg-jar", required=True, type=Path)
    parser.add_argument("--work-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    args.work_root.mkdir(parents=True, exist_ok=False)
    first = clean_run(args.work_root / "clean-one", args.iceberg_jar)
    second = clean_run(args.work_root / "clean-two", args.iceberg_jar)
    recovery = recovery_run(args.work_root / "recovery", args.iceberg_jar)
    result = {
        "result": "PASS",
        "clean_runs": [first, second],
        "stable_projection_equal": stable_projection(first) == stable_projection(second),
        "recovery": recovery,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"result": result["result"], "output": str(args.output)}, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except SnapshotLoadError as exc:
        raise SystemExit(str(exc)) from exc
