"""Apply one fully validated Stage 4 transaction to an unpublished generation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from changebridge.cdc_apply import CDCApplyCoordinator
from changebridge.cdc_control import CDCControlStore
from changebridge.generation_registry import GenerationRegistry
from changebridge.iceberg_cdc import IcebergCDCAdapter


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--generation-registry", required=True, type=Path)
    parser.add_argument("--cdc-control", required=True, type=Path)
    parser.add_argument("--warehouse", required=True, type=Path)
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--iceberg-jar", required=True, type=Path)
    parser.add_argument("--fault")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    with (
        GenerationRegistry(args.generation_registry) as registry,
        CDCControlStore(args.cdc_control) as control,
        IcebergCDCAdapter(
            warehouse=args.warehouse,
            namespace=args.namespace,
            iceberg_jar=args.iceberg_jar,
        ) as iceberg,
    ):
        result = CDCApplyCoordinator(
            registry=registry, control=control, iceberg=iceberg
        ).apply_transaction(plan, fault=args.fault)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
