"""Command-line entry point."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from changebridge.canonical import canonical_json
from changebridge.contracts import schema_digest
from changebridge.normalizer import normalize_manifest, strict_json_loads, write_bundle_atomic
from changebridge.simulator import run_failure_lab


def main() -> None:
    parser = argparse.ArgumentParser(prog="changebridge")
    commands = parser.add_subparsers(dest="command", required=True)
    simulate = commands.add_parser("simulate", help="run the deterministic failure lab")
    simulate.add_argument("--output", type=Path)
    normalize = commands.add_parser("normalize", help="normalize a local immutable raw manifest")
    normalize.add_argument("--manifest", type=Path, required=True)
    normalize.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "simulate":
        result = run_failure_lab()
        rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
        else:
            print(canonical_json(result))
        if result["result"] != "PASS":
            raise SystemExit(1)
    elif args.command == "normalize":
        root = args.manifest.resolve().parent
        repository = Path(__file__).resolve().parents[2]
        manifest = strict_json_loads(args.manifest.read_text(encoding="utf-8"))
        manifest_schema = strict_json_loads(
            (repository / "contracts/raw-landing-manifest-v1.json").read_text(
                encoding="utf-8"
            )
        )
        envelope_schema = strict_json_loads(
            (repository / "contracts/cdc-envelope-v1.schema.json").read_text(encoding="utf-8")
        )
        source_contracts = {}
        for contract_id, version, relative in (
            ("orders_source_contract", "1.0.0", "contracts/orders-v1.json"),
            ("orders_source_contract_v1_1", "1.1.0", "contracts/orders-v1.1.json"),
            ("order_items_source_contract", "1.0.0", "contracts/order-items-v1.json"),
        ):
            schema = strict_json_loads((repository / relative).read_text(encoding="utf-8"))
            source_contracts[(contract_id, version)] = (schema_digest(schema), schema)
        bundle = normalize_manifest(
            root,
            manifest,
            manifest_schema=manifest_schema,
            envelope_schema=envelope_schema,
            source_contracts=source_contracts,
        )
        write_bundle_atomic(args.output, bundle)
        if bundle.quarantine:
            raise SystemExit(2)


if __name__ == "__main__":
    main()
