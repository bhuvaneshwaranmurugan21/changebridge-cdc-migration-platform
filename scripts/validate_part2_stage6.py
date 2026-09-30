#!/usr/bin/env python3
"""Fail-closed validator for Part 2 Stage 6."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from changebridge.contracts import semantic_digest
from changebridge.proof_gates import REQUIRED_GATES, validate_bootstrap_policy, validate_gate

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evidence/part2/stage6"
BASE = "7b5e71c68c52766affd68d0a2c6087656b447c31"
BASE_TREE = "62ed362e52a7d5fb3ccc8aa30085211980c1ca7d"


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
    receipt = load("evidence/part2/stage6/stage-receipt.json")
    assert (
        receipt["criteria_total"],
        receipt["criteria_passed"],
        receipt["criteria_pending"],
        receipt["result"],
    ) == (52, 48, 4, "PENDING_EXTERNAL_CLOSURE")
    assert [row["id"] for row in receipt["criteria"]] == [f"ST26-AC-{n:02d}" for n in range(1, 53)]
    assert all(
        row["result"] == ("PASS" if n <= 48 else "PENDING")
        for n, row in enumerate(receipt["criteria"], 1)
    )
    commit, tree = receipt["source_commit"], receipt["source_tree"]
    assert git("rev-parse", f"{commit}^{{tree}}") == tree
    seal = load("evidence/part2/stage6/generation-seal.json")
    recorded = seal.pop("seal_digest")
    assert semantic_digest(seal, domain="stage26-generation-seal") == recorded
    report = load("evidence/part2/stage6/reconciliation-report.json")
    digest = report.pop("reconciliation_digest")
    assert (
        semantic_digest(report, domain="stage26-reconciliation") == digest
        and report["verdict"] == "PASS"
        and report["mismatch_count"] == 0
    )
    manifest = load("evidence/part2/stage6/proof-manifest.json")
    for gate in manifest["gates"]:
        validate_gate(gate)
    assert tuple(gate["gate_id"] for gate in manifest["gates"]) == REQUIRED_GATES
    body = {key: value for key, value in manifest.items() if key != "proof_manifest_digest"}
    manifest_digest = manifest["proof_manifest_digest"]
    assert semantic_digest(body, domain="stage26-proof-manifest") == manifest_digest
    policy = load("evidence/part2/stage6/rollback-readiness.json")
    validate_bootstrap_policy(policy)
    failure = load("evidence/part2/stage6/failure-lab.json")
    assert (
        failure["value_mismatch"]
        and failure["missed_delete"]
        and failure["stale_gate_code"] == "CB26G010_FRONTIER_MISMATCH"
        and failure["missing_gate_code"] == "CB26G014_MISSING_GATE"
    )
    artifacts = load("evidence/part2/stage6/artifact-manifest.json")
    assert all(
        (ROOT / row["path"]).is_file() and sha((ROOT / row["path"]).read_bytes()) == row["sha256"]
        for row in artifacts["artifacts"]
    )
    assert sha((OUT / "artifact-manifest.json").read_bytes()) == receipt["artifact_manifest_digest"]
    claims = load("claims/claims.json")["claims"]
    assert any(row["id"] == "CB-CLAIM-016" and row["label"] == "LOCAL_VERIFIED" for row in claims)
    assert (
        receipt["generation_state"] == "PROVEN"
        and not receipt["published"]
        and not receipt["active"]
    )
    return {
        "result": "PASS",
        "criteria_passed": 48,
        "criteria_pending_external": 4,
        "frontier": receipt["frontier"],
        "generation_state": "PROVEN",
        "proof_manifest_digest": manifest_digest,
        "source_commit": commit,
        "source_tree": tree,
    }


if __name__ == "__main__":
    print(json.dumps(validate(), sort_keys=True))
