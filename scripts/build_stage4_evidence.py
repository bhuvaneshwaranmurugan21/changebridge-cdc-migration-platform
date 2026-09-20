#!/usr/bin/env python3
"""Build and verify the deterministic Stage 4 artifact manifest and candidate receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BASE_COMMIT = "3634b23a7fb83611a9c3b28b785a7373b68861ec"
BASE_TREE = "edd0986becbe74daff9131587c535e17e26a9315"
VALIDATED_COMMIT = "6385a185e83a52f9f1ca9fd34f70435f6e9d0624"
VALIDATED_TREE = "6b8358f0cba2702fdf2554ae337babb5f95288b0"
MANIFEST_PATH = Path("evidence/part1/stage4/artifact-manifest.json")
RECEIPT_PATH = Path("evidence/part1/stage4/stage-receipt.json")
EXCLUDED = {MANIFEST_PATH.as_posix(), RECEIPT_PATH.as_posix()}
ALLOWED_PREFIXES = (
    "contracts/",
    "docs/contracts/",
    "docs/testing/",
    "evidence/part1/stage4/",
    "oracles/",
    "requirements/",
    "schemas/canonicalization-",
    "schemas/contract-",
    "schemas/invariant-",
    "schemas/test-layer",
    "scripts/build_contract_oracle_authority.py",
    "scripts/build_stage4_evidence.py",
    "scripts/validate_contract_oracle_authority.py",
    "src/changebridge/contracts.py",
    "src/changebridge/oracles.py",
    "testing/",
    "tests/fixtures/contract-oracle-authority/",
    "tests/test_contract_oracle_authority.py",
    "PROJECT_STATUS.md",
    "README.md",
    "pyproject.toml",
)


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def git_lines(root: Path, *args: str) -> set[str]:
    result = subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)
    return {line for line in result.stdout.splitlines() if line}


def collect_paths(root: Path) -> list[str]:
    paths = git_lines(root, "diff", "--name-only", f"{BASE_COMMIT}...HEAD")
    paths |= git_lines(root, "diff", "--name-only")
    paths |= git_lines(root, "ls-files", "--others", "--exclude-standard")
    paths -= EXCLUDED
    result = []
    for value in sorted(paths):
        path = root / value
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"CB4E001_INVALID_ARTIFACT_PATH: {value}")
        if not any(value == prefix or value.startswith(prefix) for prefix in ALLOWED_PREFIXES):
            raise ValueError(f"CB4E002_OUT_OF_SCOPE_ARTIFACT: {value}")
        result.append(value)
    return result


def build_manifest(root: Path) -> dict[str, Any]:
    artifacts = [
        {"path": value, "sha256": hashlib.sha256((root / value).read_bytes()).hexdigest()}
        for value in collect_paths(root)
    ]
    return {
        "schema_version": "1.0.0",
        "project": "ChangeBridge",
        "repository": "bhuvaneshwaranmurugan21/changebridge-cdc-migration-platform",
        "part": 1,
        "stage": 4,
        "base_commit": BASE_COMMIT,
        "base_tree": BASE_TREE,
        "validated_commit": VALIDATED_COMMIT,
        "validated_tree": VALIDATED_TREE,
        "digest_algorithm": "SHA-256",
        "artifacts": artifacts,
        "artifact_count": len(artifacts),
        "result": "PASS",
        "limitations": [
            "The manifest excludes itself and the receipt to avoid recursive identity.",
            "PR, merge, and continuation evidence are external closure artifacts.",
        ],
    }


def criterion_evidence() -> dict[int, list[str]]:
    return {
        1: ["evidence/part1/stage4/execution-envelope.json"],
        2: ["evidence/part1/stage4/execution-envelope.json"],
        3: [
            "evidence/part1/stage4/overlap-register.json",
            "evidence/part1/stage4/file-manifest.json",
        ],
        4: [
            "evidence/part1/stage4/protected-baseline.json",
            "evidence/part1/stage4/failure-lab-preservation.json",
        ],
        5: [
            "evidence/part1/stage4/file-manifest.json",
            "evidence/part1/stage4/dependency-decision.json",
            "evidence/part1/stage4/scope-isolation-report.json",
        ],
        6: ["evidence/part1/stage4/contract-source-inventory.json"],
        7: ["evidence/part1/stage4/contract-contradiction-resolution.json"],
        8: ["contracts/catalog.json"],
        9: ["contracts/VERSIONING.md"],
        10: ["contracts/canonicalization-v1.json"],
        11: ["contracts/canonicalization-v1.json"],
        12: ["contracts/cdc-envelope-v1.schema.json"],
        13: ["src/changebridge/contracts.py"],
        14: ["tests/fixtures/contract-oracle-authority/adversarial-cases.json"],
        15: [
            "contracts/source-workload-v1.schema.json",
            "contracts/target-record-metadata-v1.schema.json",
        ],
        16: ["tests/fixtures/contract-oracle-authority/valid-cdc-event.json"],
        17: ["contracts/catalog.json", "contracts/VERSIONING.md"],
        18: ["contracts/control/control-records-v1.schema.json"],
        19: ["tests/test_contract_oracle_authority.py"],
        20: ["tests/test_contract_oracle_authority.py"],
        21: ["oracles/invariants.json"],
        22: ["oracles/invariants.json"],
        23: ["src/changebridge/oracles.py"],
        24: ["evidence/part1/stage4/traceability-review.json"],
        25: ["evidence/part1/stage4/failure-lab-preservation.json"],
        26: ["evidence/part1/stage4/failure-lab-preservation.json"],
        27: ["evidence/part1/stage4/failure-lab-preservation.json"],
        28: ["tests/fixtures/contract-oracle-authority/adversarial-cases.json"],
        29: ["testing/test-layers.json"],
        30: ["docs/testing/TEST_ARCHITECTURE.md"],
        31: ["tests/fixtures/contract-oracle-authority/adversarial-cases.json"],
        32: ["tests/fixtures/contract-oracle-authority/validator-mutations.json"],
        33: ["evidence/part1/stage4/determinism-report.json"],
        34: ["evidence/part1/stage4/validation-report.json"],
        35: ["evidence/part1/stage4/claim-impact-review.json"],
        36: ["evidence/part1/stage4/claim-impact-review.json"],
        37: ["evidence/part1/stage4/artifact-manifest.json"],
        38: ["external:exact-pr-head-ci"],
        39: ["external:merge-and-main-ci"],
        40: ["external:stage5-continuation-checkpoint"],
    }


def build_receipt(manifest: dict[str, Any]) -> dict[str, Any]:
    manifest_digest = hashlib.sha256(canonical_json(manifest).encode()).hexdigest()
    evidence = criterion_evidence()
    criteria = [
        {
            "id": f"ST4-AC-{index:02d}",
            "result": "PASS" if index <= 37 else "PENDING",
            "evidence": evidence[index],
        }
        for index in range(1, 41)
    ]
    return {
        "record_type": "stage_receipt",
        "contract_version": "1.0.0",
        "record_id": "changebridge-part1-stage4",
        "revision": 1,
        "evidence_refs": [
            "evidence/part1/stage4/artifact-manifest.json",
            "evidence/part1/stage4/validation-report.json",
            "evidence/part1/stage4/determinism-report.json",
        ],
        "part": 1,
        "stage": 4,
        "base_commit": BASE_COMMIT,
        "candidate_commit": VALIDATED_COMMIT,
        "artifact_manifest_digest": manifest_digest,
        "criteria_total": 40,
        "criteria_passed": 37,
        "criteria_pending": 3,
        "criteria": criteria,
        "result": "PENDING",
        "limitations": [
            "The candidate commit binds the pre-receipt source/evidence freeze.",
            "Criteria 38-40 require exact-head CI, merge/main verification, and the external "
            "Stage 5 checkpoint.",
        ],
    }


def render(root: Path, *, check: bool) -> None:
    manifest = build_manifest(root)
    receipt = build_receipt(manifest)
    outputs = {MANIFEST_PATH: canonical_json(manifest), RECEIPT_PATH: canonical_json(receipt)}
    for relative, content in outputs.items():
        path = root / relative
        if check:
            if not path.is_file() or path.read_text(encoding="utf-8") != content:
                raise ValueError(f"CB4E003_EVIDENCE_DRIFT: {relative}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        render(args.root.resolve(), check=args.check)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
