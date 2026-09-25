#!/usr/bin/env python3
"""Bounded local Stage 3 Spark/Iceberg snapshot entry point."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from changebridge.generation_registry import (
    GenerationRegistry,
    generation_namespace,
    generation_warehouse,
)
from changebridge.iceberg_snapshot import IcebergSnapshotAdapter
from changebridge.normalizer import strict_json_loads
from changebridge.snapshot_loader import SnapshotLoader


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--warehouse-root", type=Path, required=True)
    parser.add_argument("--iceberg-jar", type=Path, required=True)
    parser.add_argument("--generation-record", type=Path, required=True)
    parser.add_argument("--table", choices=("orders", "order_items"), required=True)
    parser.add_argument(
        "--fault",
        choices=(
            "before_staging",
            "during_staging",
            "after_commit",
            "after_ledger",
            "process_exit_after_commit",
        ),
    )
    args = parser.parse_args()
    canonical = strict_json_loads((args.bundle / "canonical.json").read_text(encoding="utf-8"))
    generation_record = strict_json_loads(args.generation_record.read_text(encoding="utf-8"))
    generation_id = generation_record["generation_id"]
    events = [
        event
        for event in canonical
        if event["operation"] == "snapshot" and event["source_table"] == args.table
    ]
    warehouse = generation_warehouse(args.warehouse_root.resolve(), generation_id)
    namespace = generation_namespace(generation_id)
    with GenerationRegistry(args.registry) as registry:
        registry.register_generation(generation_record)
        generation = registry.get_generation(generation_id)
        assert generation is not None
        if generation["state"] == "CREATED":
            registry.transition(
                generation_id,
                expected_revision=0,
                to_state="SNAPSHOT_LOADING",
                actor="stage23-snapshot-job",
                decision={"reason": "begin snapshot loading"},
            )
        with IcebergSnapshotAdapter(
            warehouse=warehouse,
            namespace=namespace,
            iceberg_jar=args.iceberg_jar,
        ) as iceberg:
            result = SnapshotLoader(registry, iceberg).load_shard(
                generation_id=generation_id,
                table=args.table,
                events=events,
                fault=args.fault,
            )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
