#!/usr/bin/env python3
"""Fail-closed validator for ChangeBridge Part 2 Stage 1."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, NoReturn

from jsonschema import Draft202012Validator

try:
    from scripts import validate_part1_preservation
except ModuleNotFoundError:  # direct script execution places scripts/ on sys.path
    import validate_part1_preservation  # type: ignore[no-redef]

ROOT = Path(__file__).resolve().parents[1]
BASE_COMMIT = "6ae4e071782bddeb5a35f9635262e868f52df6f5"
BASE_TREE = "2126b55cb85844189aa9907452de22847ca43e98"
SOURCE_COMMIT = "6f64f6afe99dbacfac71e3176bc15fe4b6227dc4"
SOURCE_TREE = "022f0b80aa20a2b6588465d924e53bae2ff0bb1a"
IMAGE = "postgres@sha256:639ab7ceb90e13123085b741fb31ef493fba25463002f6da665352e7b534b652"
EVIDENCE = Path("evidence/part2/stage1")
REQUIRED_EVIDENCE = {
    "artifact-manifest.json",
    "authority-transition.json",
    "bootstrap-report.json",
    "boundary-capture-report.json",
    "claim-impact-review.json",
    "container-image-lock.json",
    "dependency-decision.json",
    "determinism-report.json",
    "execution-envelope.json",
    "expected-state-manifest.json",
    "file-manifest.json",
    "negative-case-report.json",
    "overlap-register.json",
    "protected-part1-baseline.json",
    "repository-entry.json",
    "scope-isolation-report.json",
    "source-history-ledger.json",
    "source-surface-inventory.json",
    "source-workload-manifest.json",
    "stage-receipt.json",
    "toolchain-inventory.json",
    "validation-summary.json",
}
ALLOWED_PREFIXES = (
    ".github/workflows/ci.yml",
    ".github/workflows/part2-stage1-postgres.yml",
    "architecture/requirement-architecture-map.json",
    "CLAIMS.md",
    "PART2_COMPLETION_CONTRACT.md",
    "PROJECT_STATUS.md",
    "README.md",
    "claims/claims.json",
    "contracts/order-items-v1.json",
    "contracts/orders-v1.1.json",
    "contracts/part2-stage1-catalog.json",
    "contracts/source-boundary-receipt-v1.json",
    "contracts/source-workload-spec-v1.json",
    "docs/part2/stage1/",
    "evidence/part2/stage1/",
    "migrations/source/",
    "pyproject.toml",
    "requirements/completion-requirements.json",
    "requirements/part2-stage1-acceptance.json",
    "requirements/REQUIREMENT_CATALOG.md",
    "requirements/REQUIREMENT_PROOF_MATRIX.md",
    "requirements/requirement-proof-matrix.json",
    "schemas/part2-stage1-evidence.schema.json",
    "scripts/__init__.py",
    "scripts/build_stage21_evidence.py",
    "scripts/probe_postgres_replication.py",
    "scripts/run_stage21_postgres_lab.py",
    "scripts/stage21_postgres_adapter.py",
    "scripts/validate_part1_frozen.py",
    "scripts/validate_part1_preservation.py",
    "scripts/validate_part2_stage1.py",
    "src/changebridge/contracts.py",
    "src/changebridge/source_boundary.py",
    "src/changebridge/source_workload.py",
    "tests/integration/",
    "tests/fixtures/architecture-authority/valid-authority.json",
    "tests/fixtures/completion-authority/valid-authority.json",
    "tests/test_part2_stage1_validator.py",
    "tests/test_source_boundary.py",
    "tests/test_source_workload.py",
)
FOREIGN_TOKEN_DIGESTS = {
    "fa6693fea98aaee155729a8d507bd19851613641e3f8d76458521ef89f53c826",
    "b84df95f092334b6a9fd6e1d9136aa06604070312e3ebd76387f52def66c7e19",
    "4eaab07b1ac907e562c30d4d79e59eb842a0c37085340d51c841c5a4e8a14ae5",
    "7249a5fce3e754cbb4f9ca87025ec031f31f8665ad2580c200a8c8e5cdb16e51",
}
SENSITIVE_PATTERNS = (
    re.compile(r"postgres(?:ql)?://", re.IGNORECASE),
    re.compile(r"(?:^|[\"'])/(?:tmp|home|users|workspace)/", re.IGNORECASE),
    re.compile(r"\b(?:localhost|127\.0\.0\.1)\b", re.IGNORECASE),
    re.compile(r"(?:password|secret|token)\s*[=:]", re.IGNORECASE),
)


class Stage21Error(RuntimeError):
    pass


def fail(code: str, detail: str) -> NoReturn:
    raise Stage21Error(f"{code}: {detail}")


def load(root: Path, relative: str | Path) -> dict[str, Any]:
    path = root / relative
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail("CB21V001_INVALID_JSON", f"{relative}: {exc}")
    if not isinstance(value, dict):
        fail("CB21V002_NOT_OBJECT", str(relative))
    return value


def git_paths(root: Path) -> set[str]:
    paths: set[str] = set()
    for args in (
        ("diff", "--name-only", f"{BASE_COMMIT}...HEAD"),
        ("diff", "--name-only"),
        ("ls-files", "--others", "--exclude-standard"),
    ):
        result = subprocess.run(
            ["git", *args], cwd=root, check=True, capture_output=True, text=True
        )
        paths.update(line for line in result.stdout.splitlines() if line)
    return paths


def validate_acceptance(registry: Mapping[str, Any], receipt: Mapping[str, Any]) -> None:
    criteria = registry.get("criteria")
    if not isinstance(criteria, Sequence) or isinstance(criteria, str):
        fail("CB21V003_ACCEPTANCE_SHAPE", "criteria")
    expected = [f"ST21-AC-{number:02d}" for number in range(1, 41)]
    ids = [row.get("id") for row in criteria if isinstance(row, Mapping)]
    if ids != expected:
        fail("CB21V004_ACCEPTANCE_SET", repr(ids))
    receipt_rows = receipt.get("criteria")
    if not isinstance(receipt_rows, Sequence) or isinstance(receipt_rows, str):
        fail("CB21V005_RECEIPT_SHAPE", "criteria")
    receipt_ids = [row.get("id") for row in receipt_rows if isinstance(row, Mapping)]
    if receipt_ids != expected:
        fail("CB21V006_RECEIPT_SET", repr(receipt_ids))
    for number, row in enumerate(receipt_rows, 1):
        expected_result = "PASS" if number <= 36 else "PENDING"
        if row.get("result") != expected_result or not row.get("evidence"):
            fail("CB21V007_RECEIPT_RESULT", f"{number}: {row}")
    if (
        receipt.get("criteria_total") != 40
        or receipt.get("criteria_passed") != 36
        or receipt.get("criteria_pending") != 4
        or receipt.get("result") != "PENDING_EXTERNAL_CLOSURE"
    ):
        fail("CB21V008_RECEIPT_COUNTS", repr(receipt))


def validate_manifest(root: Path, manifest: Mapping[str, Any], receipt: Mapping[str, Any]) -> None:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, Sequence) or isinstance(artifacts, str):
        fail("CB21V009_MANIFEST_SHAPE", "artifacts")
    paths: set[str] = set()
    for row in artifacts:
        if not isinstance(row, Mapping):
            fail("CB21V009_MANIFEST_SHAPE", repr(row))
        relative = row.get("path")
        expected = row.get("sha256")
        if not isinstance(relative, str) or relative in paths:
            fail("CB21V010_MANIFEST_PATH", repr(relative))
        path = root / relative
        if not path.is_file() or path.is_symlink():
            fail("CB21V011_MANIFEST_MISSING", relative)
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            fail("CB21V012_MANIFEST_DIGEST", relative)
        paths.add(relative)
    if manifest.get("artifact_count") != len(artifacts):
        fail("CB21V013_MANIFEST_COUNT", repr(manifest.get("artifact_count")))
    manifest_digest = hashlib.sha256(
        (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    ).hexdigest()
    if receipt.get("artifact_manifest_digest") != manifest_digest:
        fail("CB21V014_MANIFEST_BINDING", manifest_digest)


def validate_security(root: Path) -> None:
    for relative in sorted(REQUIRED_EVIDENCE):
        text = (root / EVIDENCE / relative).read_text(encoding="utf-8")
        for pattern in SENSITIVE_PATTERNS:
            if pattern.search(text):
                fail("CB21V015_SENSITIVE_EVIDENCE", f"{relative}: {pattern.pattern}")


def validate_scope(root: Path) -> None:
    paths = git_paths(root)
    outside = sorted(
        path
        for path in paths
        if not any(path == prefix or path.startswith(prefix) for prefix in ALLOWED_PREFIXES)
    )
    if outside:
        fail("CB21V016_OUT_OF_SCOPE_PATH", repr(outside))
    for relative in sorted(paths):
        path = root / relative
        if not path.is_file() or path.suffix not in {
            ".py",
            ".md",
            ".json",
            ".yml",
            ".yaml",
            ".sql",
            ".toml",
        }:
            continue
        words = re.findall(r"[a-z0-9_-]+", path.read_text(encoding="utf-8").lower())
        for word in words:
            if hashlib.sha256(word.encode()).hexdigest() in FOREIGN_TOKEN_DIGESTS:
                fail("CB21V017_FOREIGN_PROJECT_TOKEN", relative)


def validate_runtime(boundary: Mapping[str, Any], determinism: Mapping[str, Any]) -> None:
    if boundary.get("source_commit") != SOURCE_COMMIT or boundary.get("source_tree") != SOURCE_TREE:
        fail("CB21V018_SOURCE_FREEZE", "boundary report")
    if boundary.get("image") != IMAGE or boundary.get("workflow_run_id") != 36036471399:
        fail("CB21V019_RUNTIME_IDENTITY", repr(boundary.get("workflow_run_id")))
    runs = boundary.get("runs")
    if not isinstance(runs, Sequence) or len(runs) != 3:
        fail("CB21V020_RUNTIME_COUNT", repr(runs))
    frontiers = []
    for run in runs:
        if not isinstance(run, Mapping):
            fail("CB21V020_RUNTIME_COUNT", repr(run))
        if (
            run.get("capture_method") != "postgres-logical-slot-exported-snapshot/1.0.0"
            or run.get("snapshot_imported") is not True
            or run.get("cleanup") != {"slot_dropped": True}
            or run.get("generation_transitions") != ["CREATED", "SNAPSHOT_LOADING", "CDC_APPLYING"]
        ):
            fail("CB21V021_BOUNDARY_SEMANTICS", repr(run))
        snapshot = run.get("snapshot_frontier", {}).get("value")
        commit = run.get("first_post_boundary_position", {}).get("value")
        if not isinstance(snapshot, str) or not isinstance(commit, str):
            fail("CB21V022_BOUNDARY_POSITION", repr((snapshot, commit)))
        high_s, low_s = (int(value, 16) for value in snapshot.split("/"))
        high_c, low_c = (int(value, 16) for value in commit.split("/"))
        if (high_c, low_c) <= (high_s, low_s):
            fail("CB21V023_NONADVANCING_COMMIT", repr((snapshot, commit)))
        frontiers.append(snapshot)
    if len(set(frontiers)) != 3:
        fail("CB21V024_PHYSICAL_FRONTIER_COLLISION", repr(frontiers))
    same = determinism.get("same_seed_equal")
    if not isinstance(same, Mapping) or not all(same.values()):
        fail("CB21V025_NONDETERMINISTIC", repr(same))
    if determinism.get("different_seed_differs") is not True:
        fail("CB21V026_SEED_COLLISION", repr(determinism))


def validate_dependency_and_workflow(root: Path) -> None:
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    if pyproject.count('"psycopg2-binary==2.9.12"') != 1:
        fail("CB21V027_DRIVER_DECLARATION", "psycopg2-binary")
    workflow = (root / ".github/workflows/part2-stage1-postgres.yml").read_text(encoding="utf-8")
    if workflow.count(IMAGE) != 1 or "postgres:17.11" in workflow or "postgres:latest" in workflow:
        fail("CB21V028_IMAGE_NOT_PINNED", "workflow")
    if "pytest -m postgres_integration tests/integration --no-cov" not in workflow:
        fail("CB21V029_INTEGRATION_NOT_REQUIRED", "workflow")


def validate_claims_and_requirements(root: Path) -> None:
    claims = load(root, "claims/claims.json").get("claims", [])
    claim = next((row for row in claims if row.get("id") == "CB-CLAIM-011"), None)
    if claim is None or claim.get("label") != "LOCAL_VERIFIED":
        fail("CB21V030_CLAIM_MISSING", repr(claim))
    forbidden_labels = {
        row.get("id"): row.get("label")
        for row in claims
        if row.get("id") in {"CB-CLAIM-003", "CB-CLAIM-006", "CB-CLAIM-007", "CB-CLAIM-008"}
    }
    if forbidden_labels != {
        "CB-CLAIM-003": "UNCLAIMED",
        "CB-CLAIM-006": "DESIGN_ONLY",
        "CB-CLAIM-007": "UNCLAIMED",
        "CB-CLAIM-008": "DESIGN_ONLY",
    }:
        fail("CB21V031_MANAGED_CLAIM_PROMOTION", repr(forbidden_labels))
    requirements = {
        row["id"]: row
        for row in load(root, "requirements/completion-requirements.json").get("requirements", [])
    }
    if requirements["CB-BOUNDARY-001"].get("current_status") != "PARTIAL":
        fail("CB21V032_BOUNDARY_REQUIREMENT", "CB-BOUNDARY-001")
    if requirements["CB-BOUNDARY-002"].get("current_status") != "PARTIAL":
        fail("CB21V032_BOUNDARY_REQUIREMENT", "CB-BOUNDARY-002")
    if requirements["CB-BOUNDARY-003"].get("current_status") != "PARTIAL":
        fail("CB21V032_BOUNDARY_REQUIREMENT", "CB-BOUNDARY-003")


def validate(root: Path) -> dict[str, Any]:
    evidence_files = {path.name for path in (root / EVIDENCE).glob("*.json")}
    if evidence_files != REQUIRED_EVIDENCE:
        fail(
            "CB21V033_EVIDENCE_SET",
            repr(sorted(REQUIRED_EVIDENCE.symmetric_difference(evidence_files))),
        )
    schema = load(root, "schemas/part2-stage1-evidence.schema.json")
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    loaded: dict[str, dict[str, Any]] = {}
    for name in sorted(REQUIRED_EVIDENCE):
        value = load(root, EVIDENCE / name)
        errors = sorted(validator.iter_errors(value), key=lambda error: list(error.path))
        if errors:
            fail("CB21V034_EVIDENCE_SCHEMA", f"{name}: {errors[0].message}")
        if value.get("source_commit") != SOURCE_COMMIT or value.get("source_tree") != SOURCE_TREE:
            fail("CB21V035_EVIDENCE_SOURCE_BINDING", name)
        loaded[name] = value
    registry = load(root, "requirements/part2-stage1-acceptance.json")
    validate_acceptance(registry, loaded["stage-receipt.json"])
    validate_manifest(root, loaded["artifact-manifest.json"], loaded["stage-receipt.json"])
    validate_security(root)
    validate_scope(root)
    validate_part1_preservation.validate(root)
    validate_runtime(loaded["boundary-capture-report.json"], loaded["determinism-report.json"])
    validate_dependency_and_workflow(root)
    validate_claims_and_requirements(root)
    file_manifest_paths = set(loaded["file-manifest.json"].get("changed_paths", []))
    if file_manifest_paths != git_paths(root):
        fail("CB21V036_FILE_MANIFEST_DRIFT", "changed path set")
    return {
        "result": "PASS",
        "source_commit": SOURCE_COMMIT,
        "source_tree": SOURCE_TREE,
        "evidence_file_count": len(REQUIRED_EVIDENCE),
        "criteria_passed": 36,
        "criteria_pending_external": 4,
        "runtime_run_id": 36036471399,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        print(json.dumps(validate(args.root.resolve()), sort_keys=True))
    except (OSError, Stage21Error, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
