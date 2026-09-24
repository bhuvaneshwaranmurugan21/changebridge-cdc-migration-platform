#!/usr/bin/env python3
"""Run the bounded real-PostgreSQL Stage 2.1 integration laboratory."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import psycopg2  # type: ignore[import-untyped]

from changebridge.contracts import (
    schema_digest,
    semantic_digest,
    validate_control_record,
    validate_json_schema,
)
from changebridge.source_boundary import PostgresSettings
from changebridge.source_workload import materialize_workload, replay_workload
from scripts.stage21_postgres_adapter import (
    apply_migration,
    capture_boundary,
    drop_source_namespace,
    execute_workload_phase,
    initialize_source_namespace,
    query_source_state,
)

ROOT = Path(__file__).resolve().parents[1]
SEED = 424242


def _load_json(relative: str) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((ROOT / relative).read_text(encoding="utf-8")))


def _schema_authority() -> tuple[str, dict[str, dict[str, Any]]]:
    schemas = {
        "order_items/1.0.0": _load_json("contracts/order-items-v1.json"),
        "orders/1.0.0": _load_json("contracts/orders-v1.json"),
        "orders/1.1.0": _load_json("contracts/orders-v1.1.json"),
    }
    digests = {name: schema_digest(schema) for name, schema in sorted(schemas.items())}
    return semantic_digest(digests, domain="source-schema-set"), schemas


def _validate_event_rows(spec: dict[str, Any], schemas: dict[str, dict[str, Any]]) -> None:
    for transaction in spec["transactions"]:
        for event in transaction["events"]:
            if event["operation"] == "schema_change":
                continue
            schema = schemas[event["schema_version"]]
            if event["before"] is not None:
                validate_json_schema(
                    event["before"], schema, owner=f"{event['schema_version']}:before"
                )
            if event["after"] is not None:
                validate_json_schema(
                    event["after"], schema, owner=f"{event['schema_version']}:after"
                )


def _run_once(
    base_settings: PostgresSettings,
    *,
    seed: int,
    suffix: str,
    repository_commit: str,
    repository_tree: str,
    schema_set_digest: str,
    schemas: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    settings = replace(base_settings, schema=f"cb_stage21_{suffix}")
    initialize_source_namespace(settings)
    try:
        connection = psycopg2.connect(**settings.connect_arguments())
        try:
            migration_001 = apply_migration(
                connection, ROOT / "migrations/source/001_initial_source.sql"
            )
        finally:
            connection.close()

        migration_002 = hashlib.sha256(
            (ROOT / "migrations/source/002_orders_source_note.sql").read_bytes()
        ).hexdigest()
        spec = materialize_workload(seed, schema_set_digest)
        validate_json_schema(
            spec,
            _load_json("contracts/source-workload-spec-v1.json"),
            owner="source-workload-spec-v1",
        )
        _validate_event_rows(spec, schemas)
        pre_observations = execute_workload_phase(settings, spec, "PRE_BOUNDARY")
        boundary = capture_boundary(
            settings,
            spec,
            repository_commit=repository_commit,
            repository_tree=repository_tree,
        )
        validate_json_schema(
            boundary,
            _load_json("contracts/source-boundary-receipt-v1.json"),
            owner="source-boundary-receipt-v1",
        )
        validate_control_record(
            boundary["generation_record"],
            _load_json("contracts/control/control-records-v1.schema.json"),
        )

        connection = psycopg2.connect(**settings.connect_arguments())
        try:
            queried_final = query_source_state(
                connection, workload_id=spec["workload_id"], phase="POST_BOUNDARY"
            )
        finally:
            connection.close()
        expected_pre = replay_workload(spec, through_phase="PRE_BOUNDARY")
        expected_final = replay_workload(spec, through_phase="POST_BOUNDARY")
        if queried_final["whole_state_digest"] != expected_final["whole_state_digest"]:
            raise RuntimeError("CBSRC025_FINAL_STATE_MISMATCH")
        return {
            "boundary": boundary,
            "expected_final": expected_final,
            "expected_pre_boundary": expected_pre,
            "migration_checksums": {
                "001_initial_source.sql": migration_001,
                "002_orders_source_note.sql": migration_002,
            },
            "namespace_identity_sha256": semantic_digest(
                settings.schema, domain="source-namespace-identity"
            ),
            "pre_boundary_observations": pre_observations,
            "queried_final": queried_final,
            "seed": seed,
            "workload_spec": spec,
        }
    finally:
        drop_source_namespace(settings)


def build_report(repository_commit: str, repository_tree: str) -> dict[str, Any]:
    base_settings = PostgresSettings.from_environment()
    schema_set_digest, schemas = _schema_authority()
    runs = [
        _run_once(
            base_settings,
            seed=SEED,
            suffix="same_a",
            repository_commit=repository_commit,
            repository_tree=repository_tree,
            schema_set_digest=schema_set_digest,
            schemas=schemas,
        ),
        _run_once(
            base_settings,
            seed=SEED,
            suffix="same_b",
            repository_commit=repository_commit,
            repository_tree=repository_tree,
            schema_set_digest=schema_set_digest,
            schemas=schemas,
        ),
        _run_once(
            base_settings,
            seed=SEED + 1,
            suffix="different",
            repository_commit=repository_commit,
            repository_tree=repository_tree,
            schema_set_digest=schema_set_digest,
            schemas=schemas,
        ),
    ]
    first, second, different = runs
    same_seed_equal = {
        "expected_final_digest": first["expected_final"]["whole_state_digest"]
        == second["expected_final"]["whole_state_digest"],
        "history_digest": first["expected_final"]["history_digest"]
        == second["expected_final"]["history_digest"],
        "workload_id": first["workload_spec"]["workload_id"]
        == second["workload_spec"]["workload_id"],
    }
    if not all(same_seed_equal.values()):
        raise RuntimeError("CBSRC026_SAME_SEED_NONDETERMINISM")
    if (
        first["workload_spec"]["workload_id"] == different["workload_spec"]["workload_id"]
        or first["expected_final"]["history_digest"]
        == different["expected_final"]["history_digest"]
    ):
        raise RuntimeError("CBSRC027_DIFFERENT_SEED_COLLISION")
    physical_lsns = [run["boundary"]["snapshot_frontier"]["value"] for run in runs]
    if len(set(physical_lsns)) != len(physical_lsns):
        raise RuntimeError("CBSRC028_PHYSICAL_LSN_NOT_RUN_SPECIFIC")
    return {
        "different_seed_differs": True,
        "image": runs[0]["boundary"]["image"],
        "physical_lsn_excluded_from_identity": True,
        "report_version": "stage21-postgres-lab/1.0.0",
        "repository_commit": repository_commit,
        "repository_tree": repository_tree,
        "result": "PASS",
        "runs": runs,
        "same_seed_equal": same_seed_equal,
        "schema_set_digest": schema_set_digest,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    repository_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    repository_tree = subprocess.check_output(
        ["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT, text=True
    ).strip()
    report = build_report(repository_commit, repository_tree)
    arguments.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "different_seed_differs": report["different_seed_differs"],
                "result": report["result"],
                "same_seed_equal": report["same_seed_equal"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
