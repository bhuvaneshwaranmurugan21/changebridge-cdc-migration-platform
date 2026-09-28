#!/usr/bin/env python3
"""Run the bounded real Spark/Iceberg Stage 6 proof laboratory."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

from changebridge.cdc_apply import CDCApplyCoordinator
from changebridge.cdc_control import CDCControlStore
from changebridge.contracts import semantic_digest
from changebridge.generation_registry import GenerationRegistry
from changebridge.hierarchical_reconciliation import reconcile
from changebridge.iceberg_cdc import IcebergCDCAdapter
from changebridge.proof_control import ProofControlStore
from changebridge.proof_gates import (
    ProofGateError,
    assemble_manifest,
    gate_record,
    validate_bootstrap_policy,
)
from changebridge.schema_policy import POLICY_DIGEST
from changebridge.source_workload import materialize_workload, replay_workload
from scripts.run_stage24_iceberg_lab import plan, prepare

ROOT = Path(__file__).resolve().parents[1]
GENERATION, S, F = "generation-34edddda5aee96dc7236aaf3", "0/194FB20", "0/194FE20"
SCHEMAS = {"order_items": "order_items/1.0.0", "orders": "orders/1.1.0"}
LIMITATIONS = [
    "Bounded local Spark 3.5.9, Iceberg 1.11.0 and SQLite proof.",
    "No AWS, publication, performance or production property is proven.",
]


def load(relative: str) -> dict[str, Any]:
    value = json.loads((ROOT / relative).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def source_observation() -> dict[str, list[dict[str, Any]]]:
    workload = load("evidence/part2/stage1/source-workload-manifest.json")
    truth = replay_workload(
        materialize_workload(int(workload["seed"]), str(workload["schema_set_digest"])),
        through_phase="POST_BOUNDARY",
    )
    return {table: list(value["rows"]) for table, value in truth["tables"].items()}


def bootstrap() -> dict[str, Any]:
    value = {
        "policy": "FIRST_PUBLICATION_SOURCE_FALLBACK",
        "active_pointer_before_publication": None,
        "source_authoritative": True,
        "publication_stage": 7,
        "rollback_target": "ABSENT_ACTIVE_POINTER",
        "represents_prior_published_generation": False,
        "evidence_refs": ["docs/adr/ADR-020-executable-frontier-proof.md"],
    }
    validate_bootstrap_policy(value)
    return value


def clean_run(root: Path, jar: Path) -> dict[str, Any]:
    record, _ = prepare(root, jar)
    transaction = plan()
    with (
        GenerationRegistry(root / "generation.db") as registry,
        CDCControlStore(root / "cdc.db") as control,
        IcebergCDCAdapter(
            warehouse=Path(str(record["warehouse_path"])),
            namespace=str(record["namespace"]),
            iceberg_jar=jar,
        ) as iceberg,
    ):
        result = CDCApplyCoordinator(
            registry=registry, control=control, iceberg=iceberg
        ).apply_transaction(transaction)
        target: dict[str, list[dict[str, Any]]] = {}
        metadata: dict[str, Any] = {}
        for table in ("order_items", "orders"):
            identifier = iceberg.identifier(table)
            columns = list(iceberg.spark.table(identifier).columns)
            business = [column for column in columns if not column.startswith("_cb_")]
            target[table] = [
                iceberg._normalize_business(table, row.asDict(recursive=True))
                for row in iceberg.spark.sql(
                    f"SELECT {','.join(business)} FROM {identifier} ORDER BY {business[0]}"
                ).collect()
            ]
            current = iceberg.spark.sql(
                f"SELECT snapshot_id, manifest_list FROM {identifier}.snapshots "
                "ORDER BY committed_at DESC LIMIT 1"
            ).collect()[0]
            metadata[table] = {
                "snapshot_id": str(current["snapshot_id"]),
                "manifest_list_digest": semantic_digest(
                    str(current["manifest_list"]), domain="stage26-manifest-list"
                ),
            }
    source = source_observation()
    report = reconcile(
        source, target, generation_id=GENERATION, frontier=F, schema_identities=SCHEMAS
    )
    seal_body = {
        "record_type": "generation_seal",
        "contract_version": "1.0.0",
        "generation_id": GENERATION,
        "snapshot_frontier": S,
        "frontier": {"kind": "postgres_lsn", "value": F},
        "checkpoint_revision": result["checkpoint"]["revision"],
        "schema_policy_digest": POLICY_DIGEST,
        "schema_set_digest": load("evidence/part2/stage1/source-workload-manifest.json")[
            "schema_set_digest"
        ],
        "source_observation_digest": semantic_digest(source, domain="stage26-source-observation"),
        "target_observation_digest": semantic_digest(target, domain="stage26-target-observation"),
        "target_metadata": metadata,
        "published": False,
        "active": False,
    }
    seal = {
        **seal_body,
        "seal_digest": semantic_digest(seal_body, domain="stage26-generation-seal"),
    }
    with ProofControlStore(root / "proof.db") as store:
        store.register_candidate(
            GENERATION, frontier=F, schema_set_digest=str(seal["schema_set_digest"])
        )
        store.seal(GENERATION, seal)
        attempt = store.begin_proof(GENERATION)
        inputs = [seal["seal_digest"], report["reconciliation_digest"]]
        gates = [
            gate_record(
                gate,
                generation_id=GENERATION,
                frontier=F,
                schema_set_digest=str(seal["schema_set_digest"]),
                input_revision=attempt["input_revision"],
                input_digests=inputs,
                evidence_refs=["evidence/part2/stage6/reconciliation-report.json"],
                producer="changebridge.stage26",
                producer_version="1.0.0",
                limitations=LIMITATIONS,
                invalidation_conditions=["sealed input changes"],
            )
            for gate in (
                "continuity",
                "schema",
                "deletes",
                "reconciliation",
                "lag",
                "pre_migration",
                "rollback_readiness",
                "evidence_integrity",
            )
        ]
        for gate in gates:
            store.record_gate(attempt["attempt_id"], gate)
        manifest = store.seal_manifest(attempt["attempt_id"])
        replay = store.seal_manifest(attempt["attempt_id"])
        state = store.generation(GENERATION)
    return {
        "generation_id": GENERATION,
        "snapshot_frontier": S,
        "frontier": F,
        "source_counts": {k: len(v) for k, v in source.items()},
        "target_counts": {k: len(v) for k, v in target.items()},
        "target_metadata": metadata,
        "generation_seal": seal,
        "seal_digest": seal["seal_digest"],
        "reconciliation": report,
        "proof_manifest": manifest,
        "proof_replay_equal": replay == manifest,
        "generation_state": state["state"] if state else None,
        "bootstrap_policy": bootstrap(),
        "source": source,
        "target": target,
    }


def failures(clean: dict[str, Any]) -> dict[str, Any]:
    source = clean["source"]
    changed = copy.deepcopy(source)
    changed["orders"][0]["amount"] = 999999
    value = reconcile(
        source, changed, generation_id=GENERATION, frontier=F, schema_identities=SCHEMAS
    )
    deleted = copy.deepcopy(source)
    deleted["orders"].append(
        {
            "order_id": "order-003",
            "customer_id": "deleted",
            "amount": 3000,
            "campaign_id": "campaign-b",
            "source_note": None,
        }
    )
    missed = reconcile(
        source, deleted, generation_id=GENERATION, frontier=F, schema_identities=SCHEMAS
    )
    manifest = clean["proof_manifest"]
    stale = copy.deepcopy(manifest["gates"])
    stale[0]["frontier"]["value"] = "0/194FD00"
    body = {k: v for k, v in stale[0].items() if k != "gate_digest"}
    stale[0]["gate_digest"] = semantic_digest(body, domain="stage26-gate-result")

    def code(gates: list[dict[str, Any]]) -> str | None:
        try:
            assemble_manifest(
                gates,
                generation_id=GENERATION,
                frontier=F,
                schema_set_digest=manifest["schema_set_digest"],
                input_revision=manifest["input_revision"],
                seal_digest=manifest["seal_digest"],
            )
        except ProofGateError as exc:
            return exc.code
        return None

    return {
        "value_mismatch": value["verdict"] == "FAIL",
        "missed_delete": missed["verdict"] == "FAIL",
        "stale_gate_code": code(stale),
        "missing_gate_code": code(manifest["gates"][:-1]),
    }


def projection(run: dict[str, Any]) -> dict[str, Any]:
    return {
        key: run[key]
        for key in (
            "generation_id",
            "snapshot_frontier",
            "frontier",
            "source_counts",
            "target_counts",
            "generation_state",
        )
    } | {"reconciliation_digest": run["reconciliation"]["reconciliation_digest"]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iceberg-jar", required=True, type=Path)
    parser.add_argument("--work-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    args.work_root.mkdir(parents=True, exist_ok=False)
    first, second = (
        clean_run(args.work_root / "one", args.iceberg_jar),
        clean_run(args.work_root / "two", args.iceberg_jar),
    )
    failure = failures(first)
    result = {
        "result": "PASS",
        "clean_runs": [first, second],
        "stable_projection_equal": projection(first) == projection(second),
        "distinct_physical_bindings": first["seal_digest"] != second["seal_digest"],
        "failure_lab": failure,
    }
    assert (
        result["stable_projection_equal"]
        and result["distinct_physical_bindings"]
        and first["generation_state"] == "PROVEN"
        and first["reconciliation"]["verdict"] == "PASS"
        and first["proof_replay_equal"]
        and failure
        == {
            "value_mismatch": True,
            "missed_delete": True,
            "stale_gate_code": "CB26G010_FRONTIER_MISMATCH",
            "missing_gate_code": "CB26G014_MISSING_GATE",
        }
    )
    for run in result["clean_runs"]:
        run.pop("source")
        run.pop("target")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"result": "PASS", "output": str(args.output)}, sort_keys=True))


if __name__ == "__main__":
    main()
