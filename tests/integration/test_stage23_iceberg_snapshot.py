from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

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

pytestmark = pytest.mark.iceberg_integration
ROOT = Path(__file__).resolve().parents[2]


def _jar() -> Path:
    value = os.environ.get("CB_ICEBERG_JAR")
    if not value:
        pytest.fail("CB_ICEBERG_JAR is required; the real Iceberg lane cannot skip")
    path = Path(value)
    if not path.is_file():
        pytest.fail(f"CB_ICEBERG_JAR does not exist: {path}")
    return path


def _record(tmp_path: Path) -> tuple[dict[str, object], dict[str, object]]:
    spec, truth, run = reconstruct_snapshot(ROOT)
    generation_id = run["generation_id"]
    namespace = generation_namespace(generation_id)
    warehouse = generation_warehouse((tmp_path / "warehouse-root").resolve(), generation_id)
    record: dict[str, object] = {
        "generation_id": generation_id,
        "workload_id": spec["workload_id"],
        "run_id": "stage23-full-snapshot-handoff-001",
        "snapshot_frontier": "0/194FB20",
        "schema_set_digest": spec["schema_set_digest"],
        "canonicalization_profile": "changebridge-canonical-json/1.0.0",
        "warehouse_path": str(warehouse),
        "namespace": namespace,
        "table_map": {table: f"stage23.{namespace}.{table}" for table in ("order_items", "orders")},
    }
    return record, truth


def test_real_iceberg_snapshot_is_complete_idempotent_and_admitted(tmp_path: Path) -> None:
    handoff = tmp_path / "handoff"
    build_full_handoff(ROOT, handoff)
    bundle = normalize_full_handoff(ROOT, handoff)
    record, truth = _record(tmp_path)
    generation_id = str(record["generation_id"])
    namespace = str(record["namespace"])
    warehouse = Path(str(record["warehouse_path"]))
    with GenerationRegistry(tmp_path / "control.db") as registry:
        registry.register_generation(record)
        registry.transition(
            generation_id,
            expected_revision=0,
            to_state="SNAPSHOT_LOADING",
            actor="integration-test",
            decision={"reason": "real integration"},
        )
        with IcebergSnapshotAdapter(
            warehouse=warehouse, namespace=namespace, iceberg_jar=_jar()
        ) as iceberg:
            loader = SnapshotLoader(registry, iceberg)
            for table in ("orders", "order_items"):
                events = [
                    event
                    for event in bundle.canonical
                    if event["operation"] == "snapshot" and event["source_table"] == table
                ]
                first = loader.load_shard(generation_id=generation_id, table=table, events=events)
                snapshots = iceberg.snapshot_count(table)
                replay = loader.load_shard(generation_id=generation_id, table=table, events=events)
                assert first["row_count"] == len(events)
                assert replay["idempotent_replay"] is True
                assert iceberg.snapshot_count(table) == snapshots == 1
            admitted = loader.admit_snapshot(
                generation_id=generation_id,
                expected_table_digests={
                    table: truth["tables"][table]["state_digest"] for table in truth["tables"]
                },
            )
            assert admitted["proof"]["post_s_cdc_applied"] == 0
            assert admitted["generation"]["state"] == "CDC_APPLYING"


def test_commit_without_ledger_recovers_without_rewrite(tmp_path: Path) -> None:
    handoff = tmp_path / "handoff"
    build_full_handoff(ROOT, handoff)
    bundle = normalize_full_handoff(ROOT, handoff)
    record, _ = _record(tmp_path)
    generation_id = str(record["generation_id"])
    namespace = str(record["namespace"])
    warehouse = Path(str(record["warehouse_path"]))
    events = [
        event
        for event in bundle.canonical
        if event["operation"] == "snapshot" and event["source_table"] == "orders"
    ]
    database = tmp_path / "control.db"
    with GenerationRegistry(database) as registry:
        registry.register_generation(record)
        registry.transition(
            generation_id,
            expected_revision=0,
            to_state="SNAPSHOT_LOADING",
            actor="integration-test",
            decision={"reason": "recovery"},
        )
        with IcebergSnapshotAdapter(
            warehouse=warehouse, namespace=namespace, iceberg_jar=_jar()
        ) as iceberg:
            loader = SnapshotLoader(registry, iceberg)
            with pytest.raises(SnapshotLoadError, match="CBL012_INJECTED_AFTER_COMMIT"):
                loader.load_shard(
                    generation_id=generation_id,
                    table="orders",
                    events=events,
                    fault="after_commit",
                )
            assert iceberg.snapshot_count("orders") == 1
    with (
        GenerationRegistry(database) as registry,
        IcebergSnapshotAdapter(
            warehouse=warehouse, namespace=namespace, iceberg_jar=_jar()
        ) as iceberg,
    ):
        recovered = SnapshotLoader(registry, iceberg).load_shard(
            generation_id=generation_id, table="orders", events=events
        )
        assert recovered["idempotent_replay"] is True
        assert iceberg.snapshot_count("orders") == 1


def test_process_termination_after_commit_recovers_from_iceberg(tmp_path: Path) -> None:
    handoff = tmp_path / "handoff"
    build_full_handoff(ROOT, handoff)
    bundle = normalize_full_handoff(ROOT, handoff)
    bundle_path = tmp_path / "bundle"
    write_bundle_atomic(bundle_path, bundle)
    record, _ = _record(tmp_path)
    generation_path = tmp_path / "generation.json"
    generation_path.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    database = tmp_path / "process-control.db"
    command = [
        sys.executable,
        str(ROOT / "jobs/spark_iceberg_snapshot.py"),
        "--bundle",
        str(bundle_path),
        "--registry",
        str(database),
        "--warehouse-root",
        str((tmp_path / "warehouse-root").resolve()),
        "--iceberg-jar",
        str(_jar()),
        "--generation-record",
        str(generation_path),
        "--table",
        "orders",
    ]
    environment = {
        **os.environ,
        "SPARK_LOCAL_IP": "127.0.0.1",
        "PYSPARK_PYTHON": sys.executable,
    }
    crashed = subprocess.run(
        [*command, "--fault", "process_exit_after_commit"],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert crashed.returncode == 86
    recovered = subprocess.run(
        command,
        cwd=ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert '"idempotent_replay": true' in recovered.stdout
    generation_id = str(record["generation_id"])
    with GenerationRegistry(database) as registry:
        shards = registry.shards(generation_id)
        commits = registry.commits(generation_id)
        assert len(shards) == len(commits) == 1
        assert shards[0]["state"] == "RECONCILED"
