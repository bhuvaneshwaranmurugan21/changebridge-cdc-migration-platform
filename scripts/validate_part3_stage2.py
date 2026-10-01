#!/usr/bin/env python3
"""Fail-closed validator for Part 3 Stage 2 deployable-platform authority."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
ENTRY = "963db655922b0209a4ce9790c5224b3ca0e642ef"
ENTRY_TREE = "3ff300cad3b8823900326273f638f0b5cf36e7f6"


class Stage32Error(AssertionError):
    """Stable Stage 2 validation failure."""


def fail(code: str, detail: str) -> None:
    raise Stage32Error(f"{code}: {detail}")


def load(path: str) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((ROOT / path).read_text(encoding="utf-8")))


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()


def directory_digest(path: Path) -> tuple[int, str]:
    rows: list[str] = []
    files = sorted(item for item in path.rglob("*") if item.is_file())
    for item in files:
        rows.append(
            f"{item.relative_to(ROOT).as_posix()}\t{hashlib.sha256(item.read_bytes()).hexdigest()}\n"
        )
    return len(files), hashlib.sha256("".join(rows).encode()).hexdigest()


def require_tokens(text: str, tokens: list[str], code: str) -> None:
    missing = [token for token in tokens if token not in text]
    if missing:
        fail(code, f"missing tokens: {missing}")


def validate() -> dict[str, Any]:
    if git("rev-parse", f"{ENTRY}^{{tree}}") != ENTRY_TREE:
        fail("ST32_ENTRY", "entry tree mismatch")
    contract = load("requirements/part3-stage2-contract.json")
    if contract["entry_commit"] != ENTRY or contract["entry_tree"] != ENTRY_TREE:
        fail("ST32_CONTRACT", "entry authority drifted")
    if (
        contract["aws_account"] != "UNASSIGNED"
        or contract["aws_region"] != "UNASSIGNED"
        or contract["aws_mutation_authorized"]
    ):
        fail("ST32_AWS_BOUNDARY", "AWS must remain fail-closed")
    if contract["claim_ceiling"] != "LOCAL_VERIFIED":
        fail("ST32_CLAIMS", "claim ceiling promoted")

    baseline = load("evidence/part3/stage1/protected-evidence-baseline.json")
    for row in baseline["directories"]:
        actual = directory_digest(ROOT / row["path"])
        if actual != (row["files"], row["digest"]):
            fail("ST32_PROTECTED", f"protected drift: {row['path']}")
    protected_changes = git(
        "diff",
        "--name-only",
        ENTRY,
        "--",
        "evidence/part1",
        "evidence/part2",
        "evidence/part3/stage1",
    )
    if protected_changes:
        fail("ST32_PROTECTED", f"protected files changed: {protected_changes.splitlines()}")

    terraform = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((ROOT / "deployment/terraform").glob("*.tf"))
    )
    require_tokens(
        terraform,
        [
            'default = "UNASSIGNED"',
            'resource "terraform_data" "admission_guard"',
            "region = var.aws_region",
            "force_destroy = false",
            "preserve_transactions",
            'resource "aws_sfn_state_machine"',
            'resource "aws_glue_job"',
            'resource "aws_dynamodb_table" "control"',
            '"checkpoints"',
            'resource "aws_dynamodb_table" "publication_revisions"',
            "runtime_artifact_sha256",
        ],
        "ST32_TERRAFORM",
    )
    if "random_id" in terraform or 'default     = "ap-south-1"' in terraform:
        fail("ST32_DETERMINISM", "random naming or unsafe region default remains")
    if 'version = "= 5.100.0"' not in terraform:
        fail("ST32_PROVIDER_LOCK", "AWS provider is not pinned to 5.100.0")
    lock = (ROOT / "deployment/terraform/.terraform.lock.hcl").read_text(encoding="utf-8")
    if (
        'version     = "5.100.0"' not in lock
        or "h1:edXOJWE4ORX8Fm+dpVpICzMZJat4AX0VRCAy/xkcOc0=" not in lock
    ):
        fail("ST32_PROVIDER_LOCK", "provider lockfile identity drifted")
    if 'actions   = ["*"]' in terraform or 'resources = ["*"]' in terraform:
        fail("ST32_IAM", "wildcard IAM authority detected")

    orchestration = load("deployment/orchestration/migration.asl.json")
    states = orchestration["States"]
    if (
        states["ProofGate"]["Default"] != "Rejected"
        or states["ProofGate"]["Choices"][0]["Next"] != "Publish"
    ):
        fail("ST32_PROOF_GATE", "publication is not proof gated")
    retries = [row["MaxAttempts"] for state in states.values() for row in state.get("Retry", [])]
    if not retries or max(retries) > 2:
        fail("ST32_RETRIES", "retries are absent or unbounded")

    boundaries = load("deployment/policies/iam-boundaries.json")
    if boundaries["forbidden"] != ["Action:*", "Resource:*", "iam:PassRole:*", "sts:AssumeRole:*"]:
        fail("ST32_IAM", "forbidden authority inventory drifted")
    for name, role in boundaries["roles"].items():
        if (
            name != "publication_controller"
            and "dynamodb:UpdateItem:active-pointer" not in role["must_not"]
            and name in {"snapshot_job", "cdc_apply_job", "reconciliation_job"}
        ):
            fail("ST32_IAM", f"{name} lacks pointer denial boundary")

    runtime = load("deployment/runtime-lock.json")
    if (
        runtime["iceberg_sha256"]
        != "94b8e36fc329f0293d44ba9e01b784a56e9501affec1842d898144c51f6e486a"
    ):
        fail("ST32_RUNTIME_LOCK", "Iceberg checksum drifted")
    if runtime["pyspark"] != "3.5.9" or runtime["py4j"] != "0.10.9.9":
        fail("ST32_RUNTIME_LOCK", "qualified Spark matrix drifted")

    criteria = load("requirements/part3-stage2-acceptance.json")["criteria"]
    if [row["id"] for row in criteria] != [f"ST32-AC-{number:02d}" for number in range(1, 48)]:
        fail("ST32_ACCEPTANCE", "acceptance IDs are not contiguous")
    expected_statuses = ["PASS"] * 36 + ["PENDING"] + ["PASS"] * 5 + ["PENDING"] * 5
    if [row["status"] for row in criteria] != expected_statuses:
        fail("ST32_ACCEPTANCE", "candidate acceptance states drifted")

    manifest = load("evidence/part3/stage2/artifact-manifest.json")
    for row in manifest["artifacts"]:
        path = ROOT / row["path"]
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
            fail("ST32_MANIFEST", f"artifact mismatch: {row['path']}")

    return {
        "result": "PASS",
        "criteria_passed": 41,
        "criteria_pending_external": 6,
        "entry_commit": ENTRY,
        "entry_tree": ENTRY_TREE,
        "aws_binding": "UNASSIGNED",
        "claim_ceiling": "LOCAL_VERIFIED",
    }


if __name__ == "__main__":
    print(json.dumps(validate(), sort_keys=True))
