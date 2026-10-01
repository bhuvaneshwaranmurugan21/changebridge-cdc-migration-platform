#!/usr/bin/env python3
"""Fail-closed validator for Part 3 Stage 1 managed-proof authority."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
ENTRY = "fd93d0863114ac131b79c011b2205a233fe185d7"
ENTRY_TREE = "5be57fe4dc8369e7324770accb662e3cca9c8883"


class Stage31Error(AssertionError):
    """A stable Stage 1 validation failure."""


def fail(code: str, detail: str) -> None:
    raise Stage31Error(f"{code}: {detail}")


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
        digest = hashlib.sha256(item.read_bytes()).hexdigest()
        rows.append(f"{item.relative_to(ROOT).as_posix()}\t{digest}\n")
    return len(files), hashlib.sha256("".join(rows).encode()).hexdigest()


def load_bundle() -> dict[str, Any]:
    return {
        "contract": load("requirements/part3-completion-contract.json"),
        "stages": load("readiness/part3-stage-map.json"),
        "dependencies": load("readiness/part3-dependency-graph.json"),
        "corrections": load("requirements/part3-stage1-requirement-corrections.json"),
        "aws": load("evidence/part3/stage1/aws-authorization-forecast.json"),
        "claims": load("evidence/part3/stage1/claim-impact-review.json"),
        "acceptance": load("requirements/part3-stage1-acceptance.json"),
    }


def validate_authority(bundle: dict[str, Any]) -> None:
    contract = bundle["contract"]
    if contract["entry_commit"] != ENTRY or contract["entry_tree"] != ENTRY_TREE:
        fail("ST31_ENTRY_IDENTITY", "contract entry identity drifted")
    if not contract["final_part"] or contract["stage_count"] != 8:
        fail("ST31_STAGE_SEQUENCE", "Part 3 must contain exactly eight final-part stages")
    stages = bundle["stages"]["stages"]
    if [row["number"] for row in stages] != list(range(1, 9)):
        fail("ST31_STAGE_SEQUENCE", "stage numbers are not contiguous")
    expected = "PART2_COMPLETION_VERIFIED"
    for row in stages:
        if row["depends_on"] != [expected]:
            fail("ST31_STAGE_SEQUENCE", f"stage {row['number']} dependency drifted")
        expected = row["checkpoint"]
    if expected != "PROJECT_COMPLETION_VERIFIED":
        fail("ST31_STAGE_SEQUENCE", "final checkpoint drifted")

    aws = bundle["aws"]
    fields = ("account_id", "region", "budget_ceiling", "execution_identity", "oidc_binding")
    if any(aws[field] != "UNASSIGNED" for field in fields) or aws["mutation_authorized"]:
        fail("ST31_AWS_NOT_UNASSIGNED", "AWS boundary must remain fail-closed")
    if (
        bundle["claims"]["claim_ceiling_after"] != "LOCAL_VERIFIED"
        or bundle["claims"]["new_managed_claims"]
    ):
        fail("ST31_CLAIM_PROMOTION", "Stage 1 cannot promote a managed claim")

    criteria = bundle["acceptance"]["criteria"]
    if [row["id"] for row in criteria] != [f"ST31-AC-{n:02d}" for n in range(1, 45)]:
        fail("ST31_ACCEPTANCE_SEQUENCE", "acceptance IDs are not exact and contiguous")
    expected_status = ["PASS"] * 39 + ["PENDING"] * 5
    if [row["status"] for row in criteria] != expected_status:
        fail("ST31_ACCEPTANCE_SEQUENCE", "candidate/external acceptance states drifted")

    corrections = bundle["corrections"]
    rows = corrections["corrections"]
    if len(rows) != 17 or len({row["id"] for row in rows}) != 17:
        fail("ST31_REQUIREMENT_OVERLAY", "requirement corrections are incomplete or duplicated")
    if corrections["effective_counts"] != {
        "SATISFIED": 31,
        "PARTIAL": 3,
        "UNSATISFIED": 3,
        "DEFERRED": 2,
    }:
        fail("ST31_REQUIREMENT_OVERLAY", "effective requirement counts drifted")
    if any(row["to"] != "SATISFIED" or not (ROOT / row["proof"]).is_file() for row in rows):
        fail("ST31_REQUIREMENT_OVERLAY", "a correction lacks local proof or safe status")


def validate() -> dict[str, Any]:
    if git("rev-parse", f"{ENTRY}^{{tree}}") != ENTRY_TREE:
        fail("ST31_ENTRY_IDENTITY", "Git entry tree does not match authority")
    validate_authority(load_bundle())

    baseline = load("evidence/part3/stage1/protected-evidence-baseline.json")
    for row in baseline["directories"]:
        count, digest = directory_digest(ROOT / row["path"])
        if (count, digest) != (row["files"], row["digest"]):
            fail("ST31_PROTECTED_EVIDENCE", f"protected evidence drift: {row['path']}")

    receipt = load("evidence/part3/stage1/stage-receipt.json")
    counts = receipt["criteria_total"], receipt["criteria_passed"], receipt["criteria_pending"]
    if counts != (44, 39, 5):
        fail("ST31_RECEIPT", "receipt counts drifted")
    if receipt["result"] != "PENDING_EXTERNAL_CLOSURE":
        fail("ST31_RECEIPT", "candidate must remain pending external closure")

    status = (ROOT / "PART3_STATUS.md").read_text(encoding="utf-8")
    if "PART3_STAGE1_MANAGED_AUTHORITY_PENDING_EXTERNAL_CLOSURE" not in status:
        fail("ST31_STATUS", "project status is not at Stage 1 candidate closure")

    changed = set(filter(None, git("diff", "--name-only", ENTRY).splitlines()))
    forbidden = {
        path for path in changed
        if path.startswith(("src/", "terraform/", "infra/", ".github/workflows/"))
        or path in {"pyproject.toml", "requirements.txt", "poetry.lock"}
    }
    if forbidden:
        fail("ST31_SCOPE", f"forbidden behavior/dependency paths changed: {sorted(forbidden)}")

    manifest = load("evidence/part3/stage1/artifact-manifest.json")
    for row in manifest["artifacts"]:
        path = ROOT / row["path"]
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
            fail("ST31_ARTIFACT_MANIFEST", f"artifact mismatch: {row['path']}")

    return {
        "result": "PASS",
        "criteria_passed": 39,
        "criteria_pending_external": 5,
        "entry_commit": ENTRY,
        "entry_tree": ENTRY_TREE,
        "claim_ceiling": "LOCAL_VERIFIED",
        "aws_binding": "UNASSIGNED",
    }


if __name__ == "__main__":
    print(json.dumps(validate(), sort_keys=True))
