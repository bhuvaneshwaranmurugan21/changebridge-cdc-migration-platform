#!/usr/bin/env python3
"""Fail-closed validator for ChangeBridge Part 2 Stage 5."""

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
BASE_COMMIT = "cbf575315e3b9bea3c0ee79f78e3288c8746effb"
BASE_TREE = "30e26dd3d7cd89601de92bc6ec99ec0e1a2737f0"
EVIDENCE = Path("evidence/part2/stage5")
REQUIRED_EVIDENCE = {
    "artifact-manifest.json",
    "claim-impact-review.json",
    "determinism-report.json",
    "execution-envelope.json",
    "file-manifest.json",
    "generation-rejection.json",
    "generation-state.json",
    "iceberg-schema-apply.json",
    "protected-predecessor-baseline.json",
    "quarantine-proof.json",
    "repository-entry.json",
    "schema-policy-proof.json",
    "schema-recovery.json",
    "stage-receipt.json",
    "validation-summary.json",
}
PROTECTED = (
    "evidence/part1",
    "evidence/part2/stage1",
    "evidence/part2/stage2",
    "evidence/part2/stage3",
    "evidence/part2/stage4",
)
SENSITIVE = (
    re.compile(r"postgres(?:ql)?://", re.IGNORECASE),
    re.compile(r"(?:password|secret|access[_-]?key)\s*[=:]", re.IGNORECASE),
    re.compile(r'"(?:temporary_path|temp_path|hostname|work_root|warehouse)"\s*:', re.IGNORECASE),
    re.compile(r"/tmp/"),
)


class Stage25Error(RuntimeError):
    pass


def fail(code: str, detail: str) -> NoReturn:
    raise Stage25Error(f"{code}: {detail}")


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()


def load(relative: str | Path) -> dict[str, Any]:
    try:
        value = json.loads((ROOT / relative).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        fail("CB25V002_INVALID_JSON", f"{relative}:{type(exc).__name__}")
    if not isinstance(value, dict):
        fail("CB25V003_NOT_OBJECT", str(relative))
    return value


def tree_digest(commit: str, path: str) -> str:
    listing = git("ls-tree", "-r", commit, path)
    return hashlib.sha256((listing + "\n").encode()).hexdigest()


def validate() -> dict[str, Any]:
    if git("rev-parse", f"{BASE_COMMIT}^{{tree}}") != BASE_TREE:
        fail("CB25V004_BASE_IDENTITY", BASE_COMMIT)
    registry = load("requirements/part2-stage5-acceptance.json")
    receipt = load(EVIDENCE / "stage-receipt.json")
    expected = [f"ST25-AC-{number:02d}" for number in range(1, 49)]
    criteria, rows = registry.get("criteria"), receipt.get("criteria")
    if not isinstance(criteria, Sequence) or isinstance(criteria, str):
        fail("CB25V005_ACCEPTANCE_SHAPE", "registry")
    if not isinstance(rows, Sequence) or isinstance(rows, str):
        fail("CB25V005_ACCEPTANCE_SHAPE", "receipt")
    if [row.get("id") for row in criteria if isinstance(row, Mapping)] != expected:
        fail("CB25V006_ACCEPTANCE_SET", "registry")
    if [row.get("id") for row in rows if isinstance(row, Mapping)] != expected:
        fail("CB25V006_ACCEPTANCE_SET", "receipt")
    for number, row in enumerate(rows, 1):
        wanted = "PASS" if number <= 44 else "PENDING"
        if not isinstance(row, Mapping) or row.get("result") != wanted or not row.get("evidence"):
            fail("CB25V007_ACCEPTANCE_RESULT", str(number))
    counts = (
        receipt.get("criteria_total"),
        receipt.get("criteria_passed"),
        receipt.get("criteria_pending"),
        receipt.get("result"),
    )
    if counts != (48, 44, 4, "PENDING_EXTERNAL_CLOSURE"):
        fail("CB25V008_ACCEPTANCE_COUNTS", repr(counts))
    actual = {path.name for path in (ROOT / EVIDENCE).glob("*.json")}
    if actual != REQUIRED_EVIDENCE:
        fail("CB25V009_EVIDENCE_SET", repr(sorted(actual ^ REQUIRED_EVIDENCE)))
    source_commit, source_tree = receipt.get("source_commit"), receipt.get("source_tree")
    if not isinstance(source_commit, str) or not isinstance(source_tree, str):
        fail("CB25V010_SOURCE_FREEZE", "identity")
    if git("rev-parse", source_commit) != source_commit:
        fail("CB25V010_SOURCE_FREEZE", "commit")
    if git("rev-parse", f"{source_commit}^{{tree}}") != source_tree:
        fail("CB25V010_SOURCE_FREEZE", "tree")
    schema = load("schemas/part2-stage5-evidence.schema.json")
    for name in REQUIRED_EVIDENCE:
        value = load(EVIDENCE / name)
        errors = list(Draft202012Validator(schema).iter_errors(value))
        if errors:
            fail("CB25V011_EVIDENCE_SCHEMA", f"{name}:{errors[0].validator}")
        if value.get("source_commit") != source_commit or value.get("source_tree") != source_tree:
            fail("CB25V010_SOURCE_FREEZE", name)
        text = (ROOT / EVIDENCE / name).read_text(encoding="utf-8")
        if any(pattern.search(text) for pattern in SENSITIVE):
            fail("CB25V012_SENSITIVE_EVIDENCE", name)
    artifact_path = ROOT / EVIDENCE / "artifact-manifest.json"
    manifest = load(EVIDENCE / "artifact-manifest.json")
    artifact_rows = manifest.get("artifacts")
    if not isinstance(artifact_rows, list):
        fail("CB25V013_ARTIFACT_SHAPE", "rows")
    for row in artifact_rows:
        path = ROOT / str(row["path"])
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != row.get("sha256"):
            fail("CB25V014_ARTIFACT_DIGEST", str(path))
    if hashlib.sha256(artifact_path.read_bytes()).hexdigest() != receipt.get(
        "artifact_manifest_digest"
    ):
        fail("CB25V015_ARTIFACT_BINDING", "receipt")
    baseline = load(EVIDENCE / "protected-predecessor-baseline.json")
    for key, path in zip(("part1", "stage1", "stage2", "stage3", "stage4"), PROTECTED, strict=True):
        expected_digest = tree_digest(BASE_COMMIT, path)
        if baseline.get(key) != expected_digest or tree_digest("HEAD", path) != expected_digest:
            fail("CB25V016_PREDECESSOR_DRIFT", path)
    apply = load(EVIDENCE / "iceberg-schema-apply.json")
    if not (
        apply.get("after_schema_id") == apply.get("before_schema_id", -1) + 1
        and apply.get("snapshot_count_unchanged") is True
        and apply.get("row_count") == 6
        and apply.get("old_rows_null") is True
    ):
        fail("CB25V017_SCHEMA_APPLY", repr(apply))
    recovery = load(EVIDENCE / "schema-recovery.json")
    if not (
        recovery.get("crash_exit_code") == 88
        and recovery.get("receipts_after_crash") == 0
        and recovery.get("recovered_receipt") is True
        and recovery.get("snapshot_count_unchanged") is True
    ):
        fail("CB25V018_RECOVERY", repr(recovery))
    quarantine = load(EVIDENCE / "quarantine-proof.json")
    if not (
        quarantine.get("verdict") == "UNKNOWN"
        and quarantine.get("admission_blocked") == "CB25C005_GENERATION_QUARANTINED"
        and quarantine.get("target_unchanged") is True
    ):
        fail("CB25V019_QUARANTINE", repr(quarantine))
    rejection = load(EVIDENCE / "generation-rejection.json")
    if (
        rejection.get("generation_state") != "REJECTED"
        or rejection.get("target_unchanged") is not True
    ):
        fail("CB25V020_REJECTION", repr(rejection))
    state = load(EVIDENCE / "generation-state.json")
    if (
        state.get("accepted_state"),
        state.get("published"),
        state.get("sealed"),
        state.get("checkpoint"),
    ) != ("CDC_APPLYING", False, False, "0/194FE20"):
        fail("CB25V021_BOUNDARY", repr(state))
    claims = load("claims/claims.json").get("claims", [])
    claim = next((row for row in claims if row.get("id") == "CB-CLAIM-015"), None)
    if claim is None or claim.get("label") != "LOCAL_VERIFIED":
        fail("CB25V022_CLAIM", repr(claim))
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
    except (Stage25Error, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
