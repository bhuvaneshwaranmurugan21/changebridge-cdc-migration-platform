#!/usr/bin/env python3
"""Fail-closed validator for ChangeBridge Part 2 Stage 4."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, NoReturn

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[1]
BASE_COMMIT = "e9b4a6dc6d62c1c90a89ea4ba3c02ad6a0d6a601"
BASE_TREE = "775b6790edd7b671091e32b0e2787374e4bcb429"
EVIDENCE = Path("evidence/part2/stage4")
REQUIRED_EVIDENCE = {
    "apply-manifest-proof.json",
    "artifact-manifest.json",
    "checkpoint-recovery.json",
    "claim-impact-review.json",
    "determinism-report.json",
    "differential-report.json",
    "execution-envelope.json",
    "failure-lab.json",
    "file-manifest.json",
    "generation-state.json",
    "protected-predecessor-baseline.json",
    "repository-entry.json",
    "stage-receipt.json",
    "validation-summary.json",
}
PROTECTED = (
    "evidence/part1",
    "evidence/part2/stage1",
    "evidence/part2/stage2",
    "evidence/part2/stage3",
)
SENSITIVE = (
    re.compile(r"postgres(?:ql)?://", re.IGNORECASE),
    re.compile(r"(?:password|secret|access[_-]?key)\s*[=:]", re.IGNORECASE),
    re.compile(r'"(?:temporary_path|temp_path|hostname)"\s*:', re.IGNORECASE),
)


class Stage24Error(RuntimeError):
    pass


def fail(code: str, detail: str) -> NoReturn:
    raise Stage24Error(f"{code}: {detail}")


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()


def load(relative: str | Path) -> dict[str, Any]:
    try:
        value = json.loads((ROOT / relative).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        fail("CB24V002_INVALID_JSON", f"{relative}:{type(exc).__name__}")
    if not isinstance(value, dict):
        fail("CB24V003_NOT_OBJECT", str(relative))
    return value


def tree_digest(commit: str, path: str) -> str:
    listing = git("ls-tree", "-r", commit, path)
    return hashlib.sha256((listing + "\n").encode()).hexdigest()


def validate(root: Path = ROOT) -> dict[str, Any]:
    del root
    if git("rev-parse", f"{BASE_COMMIT}^{{tree}}") != BASE_TREE:
        fail("CB24V004_BASE_IDENTITY", BASE_COMMIT)
    registry = load("requirements/part2-stage4-acceptance.json")
    receipt = load(EVIDENCE / "stage-receipt.json")
    expected = [f"ST24-AC-{number:02d}" for number in range(1, 49)]
    criteria = registry.get("criteria")
    rows = receipt.get("criteria")
    if not isinstance(criteria, Sequence) or isinstance(criteria, str):
        fail("CB24V005_ACCEPTANCE_SHAPE", "registry")
    if not isinstance(rows, Sequence) or isinstance(rows, str):
        fail("CB24V005_ACCEPTANCE_SHAPE", "receipt")
    if [row.get("id") for row in criteria if isinstance(row, Mapping)] != expected:
        fail("CB24V006_ACCEPTANCE_SET", "registry")
    if [row.get("id") for row in rows if isinstance(row, Mapping)] != expected:
        fail("CB24V006_ACCEPTANCE_SET", "receipt")
    for number, row in enumerate(rows, 1):
        wanted = "PASS" if number <= 44 else "PENDING"
        if not isinstance(row, Mapping) or row.get("result") != wanted or not row.get("evidence"):
            fail("CB24V007_ACCEPTANCE_RESULT", str(number))
    counts = (
        receipt.get("criteria_total"),
        receipt.get("criteria_passed"),
        receipt.get("criteria_pending"),
        receipt.get("result"),
    )
    if counts != (48, 44, 4, "PENDING_EXTERNAL_CLOSURE"):
        fail("CB24V008_ACCEPTANCE_COUNTS", repr(counts))
    actual = {path.name for path in (ROOT / EVIDENCE).glob("*.json")}
    if actual != REQUIRED_EVIDENCE:
        fail("CB24V009_EVIDENCE_SET", repr(sorted(actual ^ REQUIRED_EVIDENCE)))
    schema = load("schemas/part2-stage4-evidence.schema.json")
    source_commit = receipt.get("source_commit")
    source_tree = receipt.get("source_tree")
    if not isinstance(source_commit, str) or not isinstance(source_tree, str):
        fail("CB24V010_SOURCE_FREEZE", "identity")
    if git("rev-parse", source_commit) != source_commit:
        fail("CB24V010_SOURCE_FREEZE", "commit")
    if git("rev-parse", f"{source_commit}^{{tree}}") != source_tree:
        fail("CB24V010_SOURCE_FREEZE", "tree")
    for name in REQUIRED_EVIDENCE:
        value = load(EVIDENCE / name)
        errors = list(Draft202012Validator(schema).iter_errors(value))
        if errors:
            fail("CB24V011_EVIDENCE_SCHEMA", f"{name}:{errors[0].validator}")
        if value.get("source_commit") != source_commit or value.get("source_tree") != source_tree:
            fail("CB24V010_SOURCE_FREEZE", name)
        text = (ROOT / EVIDENCE / name).read_text(encoding="utf-8")
        for pattern in SENSITIVE:
            if pattern.search(text):
                fail("CB24V012_SENSITIVE_EVIDENCE", name)
    artifact_path = ROOT / EVIDENCE / "artifact-manifest.json"
    manifest = load(EVIDENCE / "artifact-manifest.json")
    artifact_rows = manifest.get("artifacts")
    if not isinstance(artifact_rows, list):
        fail("CB24V013_ARTIFACT_SHAPE", "rows")
    for row in artifact_rows:
        path = ROOT / str(row["path"])
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != row.get("sha256"):
            fail("CB24V014_ARTIFACT_DIGEST", str(path))
    if hashlib.sha256(artifact_path.read_bytes()).hexdigest() != receipt.get(
        "artifact_manifest_digest"
    ):
        fail("CB24V015_ARTIFACT_BINDING", "receipt")
    baseline = load(EVIDENCE / "protected-predecessor-baseline.json")
    for key, path in zip(("part1", "stage1", "stage2", "stage3"), PROTECTED, strict=True):
        expected_digest = tree_digest(BASE_COMMIT, path)
        if baseline.get(key) != expected_digest or tree_digest("HEAD", path) != expected_digest:
            fail("CB24V016_PREDECESSOR_DRIFT", path)
    recovery = load(EVIDENCE / "checkpoint-recovery.json")
    if not (
        recovery.get("crash_exit_code") == 87
        and recovery.get("recovered_without_rewrite") is True
        and recovery.get("checkpoint_after_crash", {}).get("source_frontier") == "0/194FB20"
        and recovery.get("final_checkpoint", {}).get("source_frontier") == "0/194FE20"
    ):
        fail("CB24V017_RECOVERY", repr(recovery))
    differential = load(EVIDENCE / "differential-report.json")
    if (
        differential.get("equal") is not True
        or differential.get("target", {}).get("orders", {}).get("row_count") != 6
    ):
        fail("CB24V018_DIFFERENTIAL", repr(differential))
    state = load(EVIDENCE / "generation-state.json")
    if state.get("state") != "CDC_APPLYING" or state.get("published") is not False:
        fail("CB24V019_PUBLICATION_BOUNDARY", repr(state))
    claims = load("claims/claims.json").get("claims", [])
    claim = next((row for row in claims if row.get("id") == "CB-CLAIM-014"), None)
    if claim is None or claim.get("label") != "LOCAL_VERIFIED":
        fail("CB24V020_CLAIM", repr(claim))
    return {
        "result": "PASS",
        "criteria_passed": 44,
        "criteria_pending_external": 4,
        "evidence_file_count": len(REQUIRED_EVIDENCE),
        "source_commit": source_commit,
        "source_tree": source_tree,
    }


if __name__ == "__main__":
    try:
        print(json.dumps(validate(), sort_keys=True))
    except (Stage24Error, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
