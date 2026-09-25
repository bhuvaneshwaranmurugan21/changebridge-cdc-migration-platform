#!/usr/bin/env python3
"""Fail-closed validator for ChangeBridge Part 2 Stage 3."""

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

from changebridge.generation_registry import deterministic_generation_id, generation_namespace
from changebridge.normalizer import strict_json_loads
from changebridge.snapshot_handoff import (
    EXPECTED_COUNTS,
    EXPECTED_FRONTIER,
    EXPECTED_WHOLE_STATE_DIGEST,
    normalize_full_handoff,
    reconstruct_snapshot,
)

ROOT = Path(__file__).resolve().parents[1]
BASE_COMMIT = "9382f8150c5af1de1bcdc8494fda6212c1d0b18b"
BASE_TREE = "5e98c6a8fe03e0dd5e6e01ca5508943743782435"
EVIDENCE = Path("evidence/part2/stage3")
REQUIRED_EVIDENCE = {
    "artifact-manifest.json",
    "authority-reconciliation.json",
    "claim-impact-review.json",
    "compatibility-probe.json",
    "dependency-decision.json",
    "determinism-report.json",
    "differential-report.json",
    "execution-envelope.json",
    "fault-recovery.json",
    "file-manifest.json",
    "generation-identity.json",
    "generation-isolation.json",
    "handoff-normalization.json",
    "process-termination.json",
    "protected-predecessor-baseline.json",
    "repository-entry.json",
    "scope-isolation-report.json",
    "shard-idempotency.json",
    "snapshot-input.json",
    "stage-receipt.json",
    "table-map.json",
    "validation-summary.json",
}
ALLOWED_PREFIXES = (
    ".github/workflows/ci.yml",
    "CLAIMS.md",
    "PART2_COMPLETION_CONTRACT.md",
    "PROJECT_STATUS.md",
    "README.md",
    "claims/claims.json",
    "contracts/snapshot-",
    "contracts/stage3-runtime-lock.json",
    "docs/adr/ADR-017-",
    "docs/part2/stage3/",
    "evidence/part2/stage3/",
    "jobs/spark_iceberg_snapshot.py",
    "pyproject.toml",
    "requirements/part2-stage3-acceptance.json",
    "requirements/completion-requirements.json",
    "requirements/REQUIREMENT_CATALOG.md",
    "requirements/REQUIREMENT_PROOF_MATRIX.md",
    "requirements/requirement-proof-matrix.json",
    "schemas/part2-stage3-evidence.schema.json",
    "scripts/build_stage23_evidence.py",
    "scripts/build_stage23_fixtures.py",
    "scripts/run_stage23_iceberg_lab.py",
    "scripts/validate_part2_stage2.py",
    "scripts/validate_part2_stage3.py",
    "src/changebridge/generation_registry.py",
    "src/changebridge/iceberg_snapshot.py",
    "src/changebridge/snapshot_handoff.py",
    "src/changebridge/snapshot_loader.py",
    "tests/fixtures/part2-stage3/",
    "tests/integration/test_stage23_iceberg_snapshot.py",
    "tests/test_part2_stage3_validator.py",
    "tests/test_stage23_generation_registry.py",
    "tests/test_stage23_snapshot_handoff.py",
)
SENSITIVE = (
    re.compile(r"postgres(?:ql)?://", re.IGNORECASE),
    re.compile(r"(?:password|secret|access[_-]?key)\s*[=:]", re.IGNORECASE),
    re.compile(r'"(?:temporary_path|temp_path|hostname)"\s*:', re.IGNORECASE),
)


class Stage23Error(RuntimeError):
    pass


def fail(code: str, detail: str) -> NoReturn:
    raise Stage23Error(f"{code}: {detail}")


def load(root: Path, relative: str | Path) -> dict[str, Any]:
    try:
        value = strict_json_loads((root / relative).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        fail("CB23V001_INVALID_JSON", f"{relative}:{type(exc).__name__}")
    if not isinstance(value, dict):
        fail("CB23V002_NOT_OBJECT", str(relative))
    return value


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


def tree_digest(root: Path, commit: str, path: str) -> str:
    listing = git(root, "ls-tree", "-r", commit, path)
    return hashlib.sha256((listing + "\n").encode()).hexdigest()


def changed_paths(root: Path) -> set[str]:
    paths = set(git(root, "diff", "--name-only", f"{BASE_COMMIT}...HEAD").splitlines())
    paths.update(git(root, "diff", "--name-only").splitlines())
    paths.update(git(root, "ls-files", "--others", "--exclude-standard").splitlines())
    return {path for path in paths if path}


def validate_acceptance(registry: Mapping[str, Any], receipt: Mapping[str, Any]) -> None:
    expected = [f"ST23-AC-{number:02d}" for number in range(1, 43)]
    criteria = registry.get("criteria")
    rows = receipt.get("criteria")
    if not isinstance(criteria, Sequence) or isinstance(criteria, str):
        fail("CB23V003_ACCEPTANCE_SHAPE", "registry")
    if not isinstance(rows, Sequence) or isinstance(rows, str):
        fail("CB23V003_ACCEPTANCE_SHAPE", "receipt")
    if [row.get("id") for row in criteria if isinstance(row, Mapping)] != expected:
        fail("CB23V004_ACCEPTANCE_SET", "registry")
    if [row.get("id") for row in rows if isinstance(row, Mapping)] != expected:
        fail("CB23V004_ACCEPTANCE_SET", "receipt")
    for number, row in enumerate(rows, 1):
        wanted = "PASS" if number <= 38 else "PENDING"
        if row.get("result") != wanted or not row.get("evidence"):
            fail("CB23V005_ACCEPTANCE_RESULT", str(number))
    counts = (
        receipt.get("criteria_total"),
        receipt.get("criteria_passed"),
        receipt.get("criteria_pending"),
        receipt.get("result"),
    )
    if counts != (42, 38, 4, "PENDING_EXTERNAL_CLOSURE"):
        fail("CB23V006_ACCEPTANCE_COUNTS", repr(counts))


def validate_artifacts(root: Path, receipt: Mapping[str, Any]) -> None:
    manifest_path = root / EVIDENCE / "artifact-manifest.json"
    manifest = load(root, EVIDENCE / "artifact-manifest.json")
    rows = manifest.get("artifacts")
    if not isinstance(rows, Sequence) or isinstance(rows, str):
        fail("CB23V007_ARTIFACT_SHAPE", "rows")
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping) or not isinstance(row.get("path"), str):
            fail("CB23V007_ARTIFACT_SHAPE", repr(row))
        relative = Path(row["path"])
        if relative.is_absolute() or ".." in relative.parts or relative.as_posix() in seen:
            fail("CB23V008_ARTIFACT_PATH", str(relative))
        path = root / relative
        if not path.is_file() or path.is_symlink():
            fail("CB23V009_ARTIFACT_MISSING", str(relative))
        if hashlib.sha256(path.read_bytes()).hexdigest() != row.get("sha256"):
            fail("CB23V010_ARTIFACT_DIGEST", str(relative))
        seen.add(relative.as_posix())
    if manifest.get("artifact_count") != len(seen):
        fail("CB23V011_ARTIFACT_COUNT", repr(len(seen)))
    if hashlib.sha256(manifest_path.read_bytes()).hexdigest() != receipt.get(
        "artifact_manifest_digest"
    ):
        fail("CB23V012_ARTIFACT_BINDING", "stage receipt")


def validate_evidence(root: Path, receipt: Mapping[str, Any]) -> None:
    actual = {path.name for path in (root / EVIDENCE).glob("*.json")}
    if actual != REQUIRED_EVIDENCE:
        fail("CB23V013_EVIDENCE_SET", repr(sorted(actual ^ REQUIRED_EVIDENCE)))
    schema = load(root, "schemas/part2-stage3-evidence.schema.json")
    source_commit, source_tree = receipt.get("source_commit"), receipt.get("source_tree")
    if not isinstance(source_commit, str) or not isinstance(source_tree, str):
        fail("CB23V014_SOURCE_FREEZE", "identity")
    if git(root, "rev-parse", source_commit) != source_commit:
        fail("CB23V014_SOURCE_FREEZE", "commit")
    if git(root, "rev-parse", f"{source_commit}^{{tree}}") != source_tree:
        fail("CB23V014_SOURCE_FREEZE", "tree")
    for name in sorted(REQUIRED_EVIDENCE):
        value = load(root, EVIDENCE / name)
        errors = list(Draft202012Validator(schema).iter_errors(value))
        if errors:
            fail("CB23V015_EVIDENCE_SCHEMA", f"{name}:{errors[0].validator}")
        if value.get("source_commit") != source_commit or value.get("source_tree") != source_tree:
            fail("CB23V014_SOURCE_FREEZE", name)
        text = (root / EVIDENCE / name).read_text(encoding="utf-8")
        for pattern in SENSITIVE:
            if pattern.search(text):
                fail("CB23V016_SENSITIVE_EVIDENCE", f"{name}:{pattern.pattern}")
    validate_artifacts(root, receipt)


def validate_scope(root: Path) -> None:
    outside = sorted(
        path
        for path in changed_paths(root)
        if not any(path == prefix or path.startswith(prefix) for prefix in ALLOWED_PREFIXES)
    )
    if outside:
        fail("CB23V017_OUT_OF_SCOPE", repr(outside))
    for path in ("evidence/part1", "evidence/part2/stage1", "evidence/part2/stage2"):
        if tree_digest(root, BASE_COMMIT, path) != tree_digest(root, "HEAD", path):
            fail("CB23V018_PREDECESSOR_DRIFT", path)


def validate_runtime(root: Path) -> None:
    lock = load(root, "contracts/stage3-runtime-lock.json")
    expected = {
        "spark": "3.5.9",
        "scala_binary": "2.12",
        "scala_runtime": "2.12.18",
    }
    if any(lock.get(key) != value for key, value in expected.items()):
        fail("CB23V019_RUNTIME_LOCK", repr(lock))
    packages = {row["name"]: row["version"] for row in lock.get("python_packages", [])}
    if packages != {"pyspark": "3.5.9", "py4j": "0.10.9.9"}:
        fail("CB23V019_RUNTIME_LOCK", repr(packages))
    maven = lock.get("maven_artifact", {})
    if maven.get("coordinate") != "org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.11.0":
        fail("CB23V020_ICEBERG_LOCK", repr(maven))
    if maven.get("sha256") != "94b8e36fc329f0293d44ba9e01b784a56e9501affec1842d898144c51f6e486a":
        fail("CB23V020_ICEBERG_LOCK", repr(maven))

    spec, truth, boundary = reconstruct_snapshot(root)
    if truth["whole_state_digest"] != EXPECTED_WHOLE_STATE_DIGEST:
        fail("CB23V021_SOURCE_ORACLE", truth["whole_state_digest"])
    generation_id = str(boundary["generation_id"])
    if generation_id != deterministic_generation_id(spec["workload_id"]):
        fail("CB23V022_GENERATION_ID", generation_id)
    identity = load(root, EVIDENCE / "generation-identity.json")
    if identity.get("generation_id") != generation_id:
        fail("CB23V022_GENERATION_ID", repr(identity))
    if identity.get("namespace") != generation_namespace(generation_id):
        fail("CB23V023_NAMESPACE", repr(identity))
    bundle = normalize_full_handoff(root, root / "tests/fixtures/part2-stage3/handoff")
    snapshots = [row for row in bundle.canonical if row["operation"] == "snapshot"]
    post_s = [row for row in bundle.canonical if row["operation"] != "snapshot"]
    counts = {
        table: sum(row["source_table"] == table for row in snapshots) for table in EXPECTED_COUNTS
    }
    if bundle.quarantine or counts != EXPECTED_COUNTS or len(post_s) != 1:
        fail("CB23V024_HANDOFF", repr((counts, len(bundle.quarantine), len(post_s))))
    if any(row["source_position"]["value"] != EXPECTED_FRONTIER for row in snapshots):
        fail("CB23V025_FRONTIER", "snapshot")
    differential = load(root, EVIDENCE / "differential-report.json")
    if differential.get("source_counts") != differential.get("target_counts"):
        fail("CB23V026_DIFFERENTIAL", "counts")
    if differential.get("source_digests") != differential.get("target_digests"):
        fail("CB23V026_DIFFERENTIAL", "digests")
    termination = load(root, EVIDENCE / "process-termination.json")
    if (
        termination.get("exit_code") != 86
        or termination.get("recovered_without_rewrite") is not True
    ):
        fail("CB23V027_PROCESS_RECOVERY", repr(termination))
    claims = load(root, "claims/claims.json").get("claims", [])
    claim = next((row for row in claims if row.get("id") == "CB-CLAIM-013"), None)
    if claim is None or claim.get("label") != "LOCAL_VERIFIED":
        fail("CB23V028_CLAIM", repr(claim))


def validate(root: Path = ROOT) -> dict[str, Any]:
    if git(root, "rev-parse", BASE_COMMIT) != BASE_COMMIT:
        fail("CB23V029_BASE_IDENTITY", "commit")
    if git(root, "rev-parse", f"{BASE_COMMIT}^{{tree}}") != BASE_TREE:
        fail("CB23V029_BASE_IDENTITY", "tree")
    registry = load(root, "requirements/part2-stage3-acceptance.json")
    receipt = load(root, EVIDENCE / "stage-receipt.json")
    validate_acceptance(registry, receipt)
    validate_evidence(root, receipt)
    validate_scope(root)
    validate_runtime(root)
    return {
        "result": "PASS",
        "criteria_passed": 38,
        "criteria_pending_external": 4,
        "evidence_file_count": len(REQUIRED_EVIDENCE),
        "source_commit": receipt["source_commit"],
        "source_tree": receipt["source_tree"],
        "profile": "changebridge.local-spark-iceberg-snapshot/1.0.0",
    }


if __name__ == "__main__":
    try:
        print(json.dumps(validate(), sort_keys=True))
    except (Stage23Error, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
