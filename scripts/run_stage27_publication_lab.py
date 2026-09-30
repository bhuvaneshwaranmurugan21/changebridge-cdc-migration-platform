#!/usr/bin/env python3
"""Run the bounded real-Iceberg Stage 7 publication and fallback laboratory."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

from changebridge.contracts import semantic_digest
from changebridge.generation_registry import generation_namespace, generation_warehouse
from changebridge.iceberg_cdc import IcebergCDCAdapter
from changebridge.proof_gates import REQUIRED_GATES, gate_record
from changebridge.publication import (
    PublicationError,
    PublicationStore,
    publication_binding_manifest,
)
from changebridge.publication_orchestrator import PublicationOrchestrator
from scripts.run_stage26_reconciliation_lab import GENERATION, F, clean_run

ROOT = Path(__file__).resolve().parents[1]
PRODUCT = "orders-migration"


def load(relative: str) -> dict[str, Any]:
    value = json.loads((ROOT / relative).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def synthetic_proof(generation_id: str, seal: str) -> dict[str, Any]:
    gates = [
        gate_record(
            gate,
            generation_id=generation_id,
            frontier=F,
            schema_set_digest="synthetic-schema",
            input_revision=1,
            input_digests=[seal, "synthetic-reconciliation"],
            evidence_refs=["tests/fixtures/part2-stage7/rollback-generations.json"],
            producer="changebridge.stage27.rollback-policy",
            producer_version="1.0.0",
            limitations=["Isolated control-plane fixture; not accepted migration data."],
            invalidation_conditions=["fixture changes"],
        )
        for gate in REQUIRED_GATES
    ]
    body = {
        "record_type": "proof_manifest",
        "contract_version": "2.0.0",
        "protocol": "changebridge-frontier-proof/2.0.0",
        "generation_id": generation_id,
        "frontier": {"kind": "postgres_lsn", "value": F},
        "schema_set_digest": "synthetic-schema",
        "input_revision": 1,
        "seal_digest": seal,
        "state": "SEALED",
        "gates": gates,
    }
    return {**body, "proof_manifest_digest": semantic_digest(body, domain="stage26-proof-manifest")}


def synthetic_binding(generation_id: str, marker: str) -> dict[str, Any]:
    accepted = synthetic_proof(generation_id, f"accepted-{marker}")
    execution = synthetic_proof(generation_id, f"execution-{marker}")
    table_map = {
        table: {
            "identifier": f"fixture.{generation_id}.{table}",
            "snapshot_id": f"{marker}-{table}",
            "manifest_list_digest": semantic_digest(
                [generation_id, table, marker], domain="stage27-fixture-manifest"
            ),
            "row_count": count,
        }
        for table, count in (("order_items", 66), ("orders", 6))
    }
    return publication_binding_manifest(
        accepted_manifest=accepted,
        execution_manifest=execution,
        table_map=table_map,
        accepted_reconciliation_digest="synthetic-reconciliation",
        execution_reconciliation_digest="synthetic-reconciliation",
    )


def ordinary_rollback_lab(root: Path) -> dict[str, Any]:
    with PublicationStore(root / "rollback.db") as store:
        store.initialize_product(PRODUCT)
        for generation_id, marker in (("rollback-a", "a"), ("rollback-b", "b")):
            store.register_generation(
                synthetic_binding(generation_id, marker),
                consumer_contract="orders-reader/1.1.0",
            )
        store.publish(
            product_id=PRODUCT,
            generation_id="rollback-a",
            expected_revision=0,
            attempt_id="publish-rollback-a",
            authorization="fixture-authorization-a",
        )
        store.publish(
            product_id=PRODUCT,
            generation_id="rollback-b",
            expected_revision=1,
            attempt_id="publish-rollback-b",
            authorization="fixture-authorization-b",
        )
        receipt = store.rollback(
            product_id=PRODUCT,
            target_generation_id="rollback-a",
            expected_revision=2,
            attempt_id="rollback-to-a",
            authorization="explicit-rollback-authorization",
        )
        store.set_eligibility("rollback-b", readable=False)
        ineligible_code = None
        try:
            store.rollback(
                product_id=PRODUCT,
                target_generation_id="rollback-b",
                expected_revision=3,
                attempt_id="rollback-ineligible",
                authorization="explicit-but-ineligible",
            )
        except PublicationError as exc:
            ineligible_code = exc.code
        return {
            "receipt": receipt,
            "final_pointer": store.current(PRODUCT),
            "ineligible_target_code": ineligible_code,
            "uses_reverse_mutation": False,
        }


def control_run(
    root: Path,
    *,
    binding: dict[str, Any],
    read_table: Any,
) -> dict[str, Any]:
    with PublicationStore(root / "publication.db") as store:
        store.initialize_product(PRODUCT)
        store.register_generation(binding, consumer_contract="orders-reader/1.1.0")
        orchestrator = PublicationOrchestrator(store)
        published = orchestrator.publish_and_verify(
            run_id="stage27-publication-run",
            product_id=PRODUCT,
            generation_id=GENERATION,
            expected_revision=0,
            attempt_id="stage27-publish-attempt",
            authorization="bounded-stage27-authorization",
            pin_id="stage27-long-reader",
            read_table=read_table,
            lose_acknowledgement=True,
        )
        long_reader = copy.deepcopy(published["consumer"])
        replay = store.publish(
            product_id=PRODUCT,
            generation_id=GENERATION,
            expected_revision=0,
            attempt_id="stage27-publish-attempt",
            authorization="bounded-stage27-authorization",
        )
        stale_code = None
        try:
            store.publish(
                product_id=PRODUCT,
                generation_id=GENERATION,
                expected_revision=0,
                attempt_id="stage27-competing-stale-publisher",
                authorization="stale-writer",
            )
        except PublicationError as exc:
            stale_code = exc.code
        fallback = orchestrator.fallback(
            run_id="stage27-publication-run",
            product_id=PRODUCT,
            expected_revision=1,
            attempt_id="stage27-fallback-attempt",
            authorization="explicit-first-publication-fallback-authorization",
            lose_acknowledgement=True,
        )
        aba_code = None
        try:
            store.publish(
                product_id=PRODUCT,
                generation_id=GENERATION,
                expected_revision=0,
                attempt_id="stage27-aba-stale-publisher",
                authorization="stale-before-first-publication",
            )
        except PublicationError as exc:
            aba_code = exc.code
        final = store.current(PRODUCT)
        return {
            "publication": published,
            "idempotent_replay_equal": replay == published["publication"],
            "stale_writer_code": stale_code,
            "fallback": fallback,
            "aba_stale_writer_code": aba_code,
            "long_reader_pin": long_reader,
            "long_reader_still_generation_bound": long_reader["generation_id"] == GENERATION,
            "final_pointer": final,
            "generation": store.generation(GENERATION),
        }


def incident_lab(root: Path, binding: dict[str, Any]) -> dict[str, Any]:
    with PublicationStore(root / "incident.db") as store:
        store.initialize_product(PRODUCT)
        store.register_generation(binding, consumer_contract="orders-reader/1.1.0")
        orchestrator = PublicationOrchestrator(store)
        code = None
        try:
            orchestrator.publish_and_verify(
                run_id="incident-run",
                product_id=PRODUCT,
                generation_id=GENERATION,
                expected_revision=0,
                attempt_id="incident-publish",
                authorization="bounded-stage27-authorization",
                pin_id="incident-reader",
                read_table=lambda table, expected: {
                    "table": table,
                    "snapshot_id": "wrong",
                    "row_count": expected["row_count"],
                },
            )
        except PublicationError as exc:
            code = exc.code
        return {
            "consumer_failure_code": code,
            "run_state": store.run("incident-run")["state"],
            "pointer_mutated": store.current(PRODUCT)["revision"] == 1,
            "automatic_fallback": False,
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iceberg-jar", required=True, type=Path)
    parser.add_argument("--work-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    args.work_root.mkdir(parents=True, exist_ok=False)
    materialization_root = args.work_root / "materialization"
    execution = clean_run(materialization_root, args.iceberg_jar)
    accepted_manifest = load("evidence/part2/stage6/proof-manifest.json")
    accepted_reconciliation = load("evidence/part2/stage6/reconciliation-report.json")
    warehouse = generation_warehouse(
        (materialization_root / "warehouse-root").resolve(), GENERATION
    )
    namespace = generation_namespace(GENERATION)
    table_map = {
        table: {
            "identifier": f"stage23.{namespace}.{table}",
            "snapshot_id": execution["target_metadata"][table]["snapshot_id"],
            "manifest_list_digest": execution["target_metadata"][table][
                "manifest_list_digest"
            ],
            "row_count": execution["target_counts"][table],
        }
        for table in ("order_items", "orders")
    }
    binding = publication_binding_manifest(
        accepted_manifest=accepted_manifest,
        execution_manifest=execution["proof_manifest"],
        table_map=table_map,
        accepted_reconciliation_digest=accepted_reconciliation["reconciliation_digest"],
        execution_reconciliation_digest=execution["reconciliation"]["reconciliation_digest"],
    )
    with IcebergCDCAdapter(
        warehouse=warehouse, namespace=namespace, iceberg_jar=args.iceberg_jar
    ) as iceberg:

        def read_table(table: str, expected: dict[str, Any]) -> dict[str, Any]:
            identifier = iceberg.identifier(table)
            if identifier != expected["identifier"]:
                raise PublicationError("CB27C007_IDENTIFIER_MISMATCH", table)
            current = iceberg.spark.sql(
                f"SELECT snapshot_id, manifest_list FROM {identifier}.snapshots "
                "ORDER BY committed_at DESC LIMIT 1"
            ).collect()[0]
            rows = iceberg.spark.table(identifier).count()
            first_column = iceberg.spark.table(identifier).columns[0]
            sample = iceberg.spark.sql(
                f"SELECT {first_column} FROM {identifier} ORDER BY {first_column} LIMIT 1"
            ).collect()[0][0]
            return {
                "table": table,
                "identifier": identifier,
                "snapshot_id": str(current["snapshot_id"]),
                "manifest_list_digest": semantic_digest(
                    str(current["manifest_list"]), domain="stage26-manifest-list"
                ),
                "row_count": rows,
                "representative_key": str(sample),
            }

        first = control_run(args.work_root / "control-one", binding=binding, read_table=read_table)
        second = control_run(args.work_root / "control-two", binding=binding, read_table=read_table)
    incident = incident_lab(args.work_root / "incident", binding)
    rollback = ordinary_rollback_lab(args.work_root / "rollback")
    def stable_projection(value: dict[str, Any]) -> dict[str, Any]:
        return {
            "publication": value["publication"],
            "idempotent_replay_equal": value["idempotent_replay_equal"],
            "stale_writer_code": value["stale_writer_code"],
            "fallback": value["fallback"],
            "aba_stale_writer_code": value["aba_stale_writer_code"],
            "long_reader_still_generation_bound": value[
                "long_reader_still_generation_bound"
            ],
            "final_pointer": value["final_pointer"],
        }
    result = {
        "result": "PASS",
        "generation_id": GENERATION,
        "snapshot_frontier": execution["snapshot_frontier"],
        "frontier": execution["frontier"],
        "accepted_proof_manifest_digest": accepted_manifest["proof_manifest_digest"],
        "execution_proof_manifest": execution["proof_manifest"],
        "accepted_reconciliation_digest": accepted_reconciliation["reconciliation_digest"],
        "execution_reconciliation_digest": execution["reconciliation"][
            "reconciliation_digest"
        ],
        "publication_binding": binding,
        "table_map": table_map,
        "physical_snapshot_reuse": False,
        "logical_contents_preserved": execution["reconciliation"]["verdict"] == "PASS",
        "control_run": first,
        "control_replay_equal": stable_projection(first) == stable_projection(second),
        "incident_lab": incident,
        "ordinary_rollback_lab": rollback,
        "final_route": first["final_pointer"]["route"],
        "final_revision": first["final_pointer"]["revision"],
    }
    assert (
        result["accepted_reconciliation_digest"] == result["execution_reconciliation_digest"]
        and result["logical_contents_preserved"]
        and result["control_replay_equal"]
        and first["publication"]["run"]["state"] == "ACTIVE"
        and first["fallback"]["run"]["state"] == "SOURCE_FALLBACK_VERIFIED"
        and first["stale_writer_code"] == "CB27P007_STALE_REVISION"
        and first["aba_stale_writer_code"] == "CB27P007_STALE_REVISION"
        and incident
        == {
            "consumer_failure_code": "CB27C005_SNAPSHOT_MISMATCH",
            "run_state": "INCIDENT",
            "pointer_mutated": True,
            "automatic_fallback": False,
        }
        and rollback["ineligible_target_code"] == "CB27P006_GENERATION_INELIGIBLE"
        and result["final_route"] == "SOURCE_FALLBACK"
        and result["final_revision"] == 2
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"result": "PASS", "output": str(args.output)}, sort_keys=True))


if __name__ == "__main__":
    main()
