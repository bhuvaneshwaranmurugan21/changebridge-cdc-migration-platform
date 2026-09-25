#!/usr/bin/env python3
"""Fail-closed validator for ChangeBridge Part 2 Stage 2."""

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

from changebridge.normalizer import REASON_CODES, normalize_manifest, strict_json_loads

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
from build_stage22_evidence import contract_authority  # type: ignore[import-not-found]  # noqa: E402, I001

ROOT = Path(__file__).resolve().parents[1]
BASE_COMMIT = "006a74119ebc4edc050e31ae171ca8d9fbe8b669"
BASE_TREE = "745f25fc394fd06c339ee22b432e3f8f26d5035d"
EVIDENCE = Path("evidence/part2/stage2")
REQUIRED_EVIDENCE = {
    "artifact-manifest.json",
    "authority-transition.json",
    "claim-impact-review.json",
    "dependency-decision.json",
    "determinism-report.json",
    "differential-report.json",
    "execution-envelope.json",
    "file-manifest.json",
    "fixture-provenance.json",
    "normalization-report.json",
    "overlap-register.json",
    "profile-qualification.json",
    "protected-predecessor-baseline.json",
    "quarantine-proof.json",
    "repository-entry.json",
    "scope-isolation-report.json",
    "stage-receipt.json",
    "validation-summary.json",
}
ALLOWED_PREFIXES = (
    ".github/workflows/ci.yml",
    "CLAIMS.md",
    "PART2_COMPLETION_CONTRACT.md",
    "PROJECT_STATUS.md",
    "README.md",
    "claims/claims.json",
    "contracts/normalization-",
    "contracts/part2-stage2-catalog.json",
    "contracts/raw-landing-manifest-v1.json",
    "contracts/transport-profile-stage22-v1.json",
    "docs/adr/ADR-016-stage2-normalization-authority.md",
    "docs/part2/stage2/",
    "evidence/part2/stage2/",
    "pyproject.toml",
    "requirements/part2-stage2-acceptance.json",
    "requirements/completion-requirements.json",
    "requirements/REQUIREMENT_CATALOG.md",
    "requirements/REQUIREMENT_PROOF_MATRIX.md",
    "requirements/requirement-proof-matrix.json",
    "schemas/part2-stage2-evidence.schema.json",
    "scripts/build_stage22_evidence.py",
    "scripts/build_stage22_fixtures.py",
    "scripts/validate_part2_stage2.py",
    "scripts/validate_part2_stage1_frozen.py",
    "src/changebridge/cli.py",
    "src/changebridge/normalizer.py",
    "tests/fixtures/part2-stage2/",
    "tests/test_part2_stage2_normalizer.py",
    "tests/test_part2_stage2_validator.py",
)
SENSITIVE = (
    re.compile(r"postgres(?:ql)?://", re.IGNORECASE),
    re.compile(r"(?:^|[\"'])/(?:tmp|home|users|workspace)/", re.IGNORECASE),
    re.compile(r"(?:password|secret|token)\s*[=:]", re.IGNORECASE),
)


class Stage22Error(RuntimeError):
    pass


def fail(code: str, detail: str) -> NoReturn:
    raise Stage22Error(f"{code}: {detail}")


def load(root: Path, relative: str | Path) -> dict[str, Any]:
    path = root / relative
    try:
        value = strict_json_loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        fail("CB22V001_INVALID_JSON", f"{relative}:{type(exc).__name__}")
    if not isinstance(value, dict):
        fail("CB22V002_NOT_OBJECT", str(relative))
    return value


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


def tree_digest(root: Path, commit: str, path: str) -> str:
    listing = git(root, "ls-tree", "-r", commit, path)
    return hashlib.sha256((listing + "\n").encode()).hexdigest()


def changed_paths(root: Path) -> set[str]:
    result = set(git(root, "diff", "--name-only", f"{BASE_COMMIT}...HEAD").splitlines())
    result.update(git(root, "diff", "--name-only").splitlines())
    result.update(git(root, "ls-files", "--others", "--exclude-standard").splitlines())
    return {item for item in result if item}


def validate_acceptance(registry: Mapping[str, Any], receipt: Mapping[str, Any]) -> None:
    expected = [f"ST22-AC-{number:02d}" for number in range(1, 45)]
    criteria = registry.get("criteria")
    if not isinstance(criteria, Sequence) or isinstance(criteria, str):
        fail("CB22V003_ACCEPTANCE_SHAPE", "criteria")
    if [item.get("id") for item in criteria if isinstance(item, Mapping)] != expected:
        fail("CB22V004_ACCEPTANCE_SET", "ordered IDs")
    receipt_rows = receipt.get("criteria")
    if not isinstance(receipt_rows, Sequence) or isinstance(receipt_rows, str):
        fail("CB22V005_RECEIPT_SHAPE", "criteria")
    if [item.get("id") for item in receipt_rows if isinstance(item, Mapping)] != expected:
        fail("CB22V006_RECEIPT_SET", "ordered IDs")
    for number, row in enumerate(receipt_rows, 1):
        expected_result = "PASS" if number <= 40 else "PENDING"
        if row.get("result") != expected_result or not row.get("evidence"):
            fail("CB22V007_RECEIPT_RESULT", str(number))
    counts = (
        receipt.get("criteria_total"),
        receipt.get("criteria_passed"),
        receipt.get("criteria_pending"),
        receipt.get("result"),
    )
    if counts != (44, 40, 4, "PENDING_EXTERNAL_CLOSURE"):
        fail("CB22V008_RECEIPT_COUNTS", repr(counts))


def validate_artifacts(root: Path, receipt: Mapping[str, Any]) -> None:
    manifest_path = root / EVIDENCE / "artifact-manifest.json"
    manifest = load(root, EVIDENCE / "artifact-manifest.json")
    rows = manifest.get("artifacts")
    if not isinstance(rows, Sequence) or isinstance(rows, str):
        fail("CB22V009_MANIFEST_SHAPE", "artifacts")
    paths = []
    for row in rows:
        if not isinstance(row, Mapping) or not isinstance(row.get("path"), str):
            fail("CB22V009_MANIFEST_SHAPE", repr(row))
        relative = Path(row["path"])
        if relative.is_absolute() or ".." in relative.parts:
            fail("CB22V010_MANIFEST_PATH", str(relative))
        path = root / relative
        if not path.is_file() or path.is_symlink():
            fail("CB22V011_MANIFEST_MISSING", str(relative))
        if hashlib.sha256(path.read_bytes()).hexdigest() != row.get("sha256"):
            fail("CB22V012_MANIFEST_DIGEST", str(relative))
        paths.append(relative.as_posix())
    if len(paths) != len(set(paths)) or manifest.get("artifact_count") != len(paths):
        fail("CB22V013_MANIFEST_COUNT", repr(paths))
    if hashlib.sha256(manifest_path.read_bytes()).hexdigest() != receipt.get(
        "artifact_manifest_digest"
    ):
        fail("CB22V014_MANIFEST_BINDING", "stage receipt")


def validate_evidence(root: Path, receipt: Mapping[str, Any]) -> None:
    actual = {path.name for path in (root / EVIDENCE).glob("*.json")}
    if actual != REQUIRED_EVIDENCE:
        fail("CB22V015_EVIDENCE_SET", repr(sorted(actual ^ REQUIRED_EVIDENCE)))
    schema = load(root, "schemas/part2-stage2-evidence.schema.json")
    source_commit, source_tree = receipt.get("source_commit"), receipt.get("source_tree")
    if not isinstance(source_commit, str) or not isinstance(source_tree, str):
        fail("CB22V016_SOURCE_FREEZE", "identity")
    if (
        git(root, "rev-parse", source_commit) != source_commit
        or git(root, "rev-parse", f"{source_commit}^{{tree}}") != source_tree
    ):
        fail("CB22V016_SOURCE_FREEZE", "unresolvable identity")
    for name in sorted(REQUIRED_EVIDENCE):
        value = load(root, EVIDENCE / name)
        errors = list(Draft202012Validator(schema).iter_errors(value))
        if errors:
            fail("CB22V017_EVIDENCE_SCHEMA", f"{name}:{errors[0].validator}")
        if value.get("source_commit") != source_commit or value.get("source_tree") != source_tree:
            fail("CB22V016_SOURCE_FREEZE", name)
        text = (root / EVIDENCE / name).read_text(encoding="utf-8")
        for pattern in SENSITIVE:
            if pattern.search(text):
                fail("CB22V018_SENSITIVE_EVIDENCE", f"{name}:{pattern.pattern}")
    validate_artifacts(root, receipt)


def validate_scope(root: Path) -> None:
    paths = changed_paths(root)
    outside = sorted(
        path
        for path in paths
        if not any(path == prefix or path.startswith(prefix) for prefix in ALLOWED_PREFIXES)
    )
    if outside:
        fail("CB22V019_OUT_OF_SCOPE", repr(outside))
    protected = (
        tree_digest(root, BASE_COMMIT, "evidence/part1"),
        tree_digest(root, "HEAD", "evidence/part1"),
        tree_digest(root, BASE_COMMIT, "evidence/part2/stage1"),
        tree_digest(root, "HEAD", "evidence/part2/stage1"),
    )
    if protected[0] != protected[1] or protected[2] != protected[3]:
        fail("CB22V020_PREDECESSOR_DRIFT", repr(protected))


def validate_runtime(root: Path) -> None:
    registry = load(root, "contracts/normalization-reason-codes-v1.json")
    if registry.get("closed") is not True or set(registry.get("codes", [])) != REASON_CODES:
        fail("CB22V021_REASON_REGISTRY", "runtime/contract mismatch")
    manifest_schema, envelope_schema, contracts = contract_authority()
    fixture = root / "tests/fixtures/part2-stage2/valid"
    manifest = load(root, "tests/fixtures/part2-stage2/valid/manifest.json")
    first = normalize_manifest(
        fixture,
        manifest,
        manifest_schema=manifest_schema,
        envelope_schema=envelope_schema,
        source_contracts=contracts,
    )
    second = normalize_manifest(
        fixture,
        manifest,
        manifest_schema=manifest_schema,
        envelope_schema=envelope_schema,
        source_contracts=contracts,
    )
    if first != second or first.quarantine or first.report.get("result") != "PASS":
        fail("CB22V022_NORMALIZATION_RESULT", repr(first.report))
    if {item["operation"] for item in first.canonical} != {
        "snapshot",
        "insert",
        "update",
        "delete",
    }:
        fail("CB22V023_OPERATION_COVERAGE", repr(first.canonical))
    if not any(item["path"].endswith(".json") for item in manifest["objects"]):
        fail("CB22V024_FORMAT_COVERAGE", "json")
    if not any(item["path"].endswith(".jsonl") for item in manifest["objects"]):
        fail("CB22V024_FORMAT_COVERAGE", "jsonl")
    if not any(item["path"].endswith(".parquet") for item in manifest["objects"]):
        fail("CB22V024_FORMAT_COVERAGE", "parquet")
    profile = load(root, "contracts/transport-profile-stage22-v1.json")
    if profile.get("managed_service_claim") is not False:
        fail("CB22V025_CLAIM_CEILING", "managed profile")
    dependency = load(root, EVIDENCE / "dependency-decision.json")
    probe = dependency.get("compatibility_probe", {})
    if dependency.get("direct_dependency") != "pyarrow==21.0.0" or probe.get("result") != "PASS":
        fail("CB22V026_DEPENDENCY_PROBE", repr(probe))
    if not all(probe.get("checks", {}).values()):
        fail("CB22V026_DEPENDENCY_PROBE", repr(probe))


def validate(root: Path = ROOT) -> dict[str, Any]:
    if (
        git(root, "rev-parse", BASE_COMMIT) != BASE_COMMIT
        or git(root, "rev-parse", f"{BASE_COMMIT}^{{tree}}") != BASE_TREE
    ):
        fail("CB22V027_BASE_IDENTITY", "commit/tree")
    registry = load(root, "requirements/part2-stage2-acceptance.json")
    receipt = load(root, EVIDENCE / "stage-receipt.json")
    validate_acceptance(registry, receipt)
    validate_evidence(root, receipt)
    validate_scope(root)
    validate_runtime(root)
    return {
        "result": "PASS",
        "criteria_passed": 40,
        "criteria_pending_external": 4,
        "evidence_file_count": len(REQUIRED_EVIDENCE),
        "source_commit": receipt["source_commit"],
        "source_tree": receipt["source_tree"],
        "profile": "changebridge.synthetic-dms-s3.full-images/1.0.0",
    }


if __name__ == "__main__":
    try:
        print(json.dumps(validate(), sort_keys=True))
    except (Stage22Error, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
