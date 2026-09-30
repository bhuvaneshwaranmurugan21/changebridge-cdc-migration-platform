#!/usr/bin/env python3
"""Fail-closed validator for Part 2 Stage 7 publication closure."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import jsonschema

from changebridge.contracts import semantic_digest
from changebridge.publication import validate_proof_manifest

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evidence/part2/stage7"
BASE = "640c5714937aa5a7a68712ccebdafa3999ecc574"
BASE_TREE = "7fd9bb0e6a9d2009dbdd57c2761c8efa4e370f82"
ACCEPTED_PROOF = "df47eda3dff2f2d4491afab71574a9abefe02e1ba1af3a788f3c190ab650a5ad"
ACCEPTED_RECON = "0415ceec67d08af7eb2cc3335f6d2dd2542a313297f53883b5a788af32add19e"
GENERATION = "generation-34edddda5aee96dc7236aaf3"


def load(path: str) -> dict[str, Any]:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()


def validate() -> dict[str, Any]:
    assert git("rev-parse", f"{BASE}^{{tree}}") == BASE_TREE
    receipt = load("evidence/part2/stage7/stage-receipt.json")
    assert (
        receipt["criteria_total"], receipt["criteria_passed"],
        receipt["criteria_pending"], receipt["result"],
    ) == (56, 50, 6, "PENDING_EXTERNAL_CLOSURE")
    assert [row["id"] for row in receipt["criteria"]] == [
        f"ST27-AC-{number:02d}" for number in range(1, 57)
    ]
    assert all(
        row["result"] == ("PASS" if number <= 50 else "PENDING")
        for number, row in enumerate(receipt["criteria"], 1)
    )
    commit, tree = receipt["source_commit"], receipt["source_tree"]
    assert git("rev-parse", f"{commit}^{{tree}}") == tree

    accepted = load("evidence/part2/stage6/proof-manifest.json")
    execution = load("evidence/part2/stage7/execution-proof-manifest.json")
    validate_proof_manifest(accepted)
    validate_proof_manifest(execution)
    assert accepted["proof_manifest_digest"] == ACCEPTED_PROOF
    assert receipt["accepted_proof_manifest_digest"] == ACCEPTED_PROOF
    assert receipt["execution_proof_manifest_digest"] == execution["proof_manifest_digest"]

    binding = load("evidence/part2/stage7/publication-binding-manifest.json")
    jsonschema.validate(
        binding, load("schemas/part2-stage7/publication-binding-v1.schema.json")
    )
    body = {key: value for key, value in binding.items() if key != "publication_binding_digest"}
    assert semantic_digest(body, domain="stage27-publication-binding") == binding[
        "publication_binding_digest"
    ]
    assert binding["accepted_proof_manifest_digest"] == ACCEPTED_PROOF
    assert binding["accepted_reconciliation_digest"] == ACCEPTED_RECON
    assert binding["execution_reconciliation_digest"] == ACCEPTED_RECON
    assert binding["generation_id"] == GENERATION
    assert binding["frontier"]["value"] == "0/194FE20"
    assert not binding["reuses_vanished_stage6_snapshots"]
    table_map = binding["table_map"]
    assert set(table_map) == {"orders", "order_items"}
    assert {name: row["row_count"] for name, row in table_map.items()} == {
        "orders": 6, "order_items": 66,
    }
    accepted_snapshots = load("evidence/part2/stage6/target-observation.json")["snapshots"]
    accepted_ids = {str(value["snapshot_id"]) for value in accepted_snapshots.values()}
    assert all(str(value["snapshot_id"]) not in accepted_ids for value in table_map.values())

    publication = load("evidence/part2/stage7/publication-receipt.json")
    consumer = load("evidence/part2/stage7/consumer-verification.json")
    fallback = load("evidence/part2/stage7/fallback-receipt.json")
    jsonschema.validate(
        publication, load("schemas/part2-stage7/publication-receipt-v1.schema.json")
    )
    jsonschema.validate(consumer, load("schemas/part2-stage7/consumer-verification-v1.schema.json"))
    jsonschema.validate(fallback, load("schemas/part2-stage7/fallback-receipt-v1.schema.json"))
    assert publication["expected_revision"] == 0 and publication["resulting_revision"] == 1
    assert publication["publication_binding_digest"] == binding["publication_binding_digest"]
    assert consumer["revision"] == 1 and consumer["table_map"] == table_map
    assert all(
        str(consumer["tables"][name]["snapshot_id"]) == str(table_map[name]["snapshot_id"])
        for name in table_map
    )
    assert fallback["expected_revision"] == 1 and fallback["resulting_revision"] == 2
    assert not fallback["represents_prior_published_generation"]

    pointer = load("evidence/part2/stage7/pointer-history.json")
    assert pointer["final_pointer"] == {
        "pointer": None, "product_id": "orders-migration",
        "revision": 2, "route": "SOURCE_FALLBACK",
    }
    assert pointer["stale_writer_code"] == pointer["aba_stale_writer_code"] == (
        "CB27P007_STALE_REVISION"
    )
    assert pointer["idempotent_replay_equal"] and pointer["ambiguous_acknowledgements_reconciled"]
    failure = load("evidence/part2/stage7/failure-lab.json")
    assert (
        failure["pointer_mutated"] and not failure["automatic_fallback"]
        and failure["run_state"] == "INCIDENT"
        and failure["consumer_failure_code"] == "CB27C005_SNAPSHOT_MISMATCH"
        and failure["ineligible_rollback_code"] == "CB27P006_GENERATION_INELIGIBLE"
    )
    rollback = load("evidence/part2/stage7/rollback-policy-report.json")
    assert (
        not rollback["accepted_generation_had_historical_incumbent"]
        and not rollback["reverse_data_mutation"]
        and not rollback["ordinary_rollback"]["uses_reverse_mutation"]
        and rollback["ordinary_rollback"]["receipt"]["verdict"] == "ROLLBACK_VERIFIED"
    )

    artifacts = load("evidence/part2/stage7/artifact-manifest.json")
    assert all(
        (ROOT / row["path"]).is_file() and sha((ROOT / row["path"]).read_bytes()) == row["sha256"]
        for row in artifacts["artifacts"]
    )
    assert sha((OUT / "artifact-manifest.json").read_bytes()) == receipt[
        "artifact_manifest_digest"
    ]
    claims = load("claims/claims.json")["claims"]
    assert any(row["id"] == "CB-CLAIM-017" and row["label"] == "LOCAL_VERIFIED" for row in claims)
    assert (
        receipt["generation_id"] == GENERATION
        and receipt["snapshot_frontier"] == "0/194FB20"
        and receipt["frontier"] == "0/194FE20"
        and receipt["final_route"] == "SOURCE_FALLBACK"
        and receipt["final_revision"] == 2
        and receipt["active_pointer"] is None
    )
    return {
        "result": "PASS", "criteria_passed": 50, "criteria_pending_external": 6,
        "generation_id": GENERATION, "final_route": "SOURCE_FALLBACK",
        "final_revision": 2, "source_commit": commit, "source_tree": tree,
    }


if __name__ == "__main__":
    print(json.dumps(validate(), sort_keys=True))
