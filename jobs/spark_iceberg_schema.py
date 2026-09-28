#!/usr/bin/env python3
"""Execute one Stage 5 schema decision against an isolated Iceberg table."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import cast

from changebridge.iceberg_schema import IcebergSchemaAdapter
from changebridge.schema_control import SchemaControlStore
from changebridge.schema_migration import SchemaMigrationCoordinator
from changebridge.schema_policy import SchemaPolicy, SchemaRegistry, registered_schema


def load(path: Path) -> dict[str, object]:
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--old-contract", required=True, type=Path)
    parser.add_argument("--new-contract", required=True, type=Path)
    parser.add_argument("--generation-id", required=True)
    parser.add_argument("--frontier", required=True)
    parser.add_argument("--warehouse", required=True, type=Path)
    parser.add_argument("--control", required=True, type=Path)
    parser.add_argument("--iceberg-jar", required=True, type=Path)
    parser.add_argument("--fault")
    args = parser.parse_args()
    registry = SchemaRegistry()
    old = registered_schema(
        contract_id="orders_source_contract",
        version="1.0.0",
        source_table="orders",
        schema=load(args.old_contract),
        primary_key=("order_id",),
    )
    new = registered_schema(
        contract_id="orders_source_contract",
        version="1.1.0",
        source_table="orders",
        schema=load(args.new_contract),
        primary_key=("order_id",),
    )
    registry.add(old)
    registry.add(new)
    with (
        IcebergSchemaAdapter(warehouse=args.warehouse, iceberg_jar=args.iceberg_jar) as iceberg,
        SchemaControlStore(args.control) as control,
    ):
        result = SchemaMigrationCoordinator(
            policy=SchemaPolicy(registry), control=control, iceberg=iceberg
        ).execute(
            generation_id=args.generation_id,
            source_table="orders",
            previous=old.identity,
            candidate=new.identity,
            frontier=args.frontier,
            fault=args.fault,
        )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
