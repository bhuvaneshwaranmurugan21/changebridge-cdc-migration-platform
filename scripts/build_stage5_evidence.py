#!/usr/bin/env python3
"""Build deterministic Stage 5 artifact identity and candidate receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BASE_COMMIT = "f7ada638e0404afacaac604be400c1434858002f"
BASE_TREE = "2401a4e8cdff8ae153dc4b1cebc1bc7b5cc61ac3"
VALIDATED_COMMIT = "a4ad1b73e6cd7da2ed1cea22f1f86a608d7052ee"
VALIDATED_TREE = "8ae75b0d6e71fd12d744d6dabea454f564a815a9"
MANIFEST_PATH = Path("evidence/part1/stage5/artifact-manifest.json")
RECEIPT_PATH = Path("evidence/part1/stage5/stage-receipt.json")
EXCLUDED = {MANIFEST_PATH.as_posix(), RECEIPT_PATH.as_posix()}
ALLOWED_PREFIXES = (
    ".github/workflows/ci.yml",
    "PROJECT_STATUS.md",
    "architecture/requirement-architecture-map.json",
    "claims/claims.json",
    "docs/INTERVIEW_WALKTHROUGH.md",
    "docs/readiness/",
    "evidence/part1/stage5/",
    "readiness/",
    "requirements/REQUIREMENT_CATALOG.md",
    "requirements/REQUIREMENT_PROOF_MATRIX.md",
    "requirements/completion-requirements.json",
    "requirements/requirement-proof-matrix.json",
    "schemas/part1-closure.schema.json",
    "scripts/build_part1_closure.py",
    "scripts/build_stage5_evidence.py",
    "scripts/validate_part1_closure.py",
    "tests/fixtures/part1-closure/",
    "tests/test_part1_closure.py",
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
            raise ValueError(f"CB5E001_INVALID_ARTIFACT_PATH: {value}")
        if not any(value == prefix or value.startswith(prefix) for prefix in ALLOWED_PREFIXES):
            raise ValueError(f"CB5E002_OUT_OF_SCOPE_ARTIFACT: {value}")
        result.append(value)
    return result


def build_manifest(root: Path) -> dict[str, Any]:
    artifacts = [
        {
            "path": value,
            "sha256": hashlib.sha256((root / value).read_bytes()).hexdigest(),
        }
        for value in collect_paths(root)
    ]
    return {
        "schema_version": "1.0.0",
        "project": "ChangeBridge",
        "repository": "bhuvaneshwaranmurugan21/changebridge-cdc-migration-platform",
        "part": 1,
        "stage": 5,
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
            "Exact-head CI, merge, merged-main CI and continuation evidence are external.",
        ],
    }


def criterion_evidence() -> dict[int, list[str]]:
    stage5 = "evidence/part1/stage5/"
    return {
        1: [stage5 + "execution-envelope.json"],
        2: [stage5 + "execution-envelope.json"],
        3: [stage5 + "overlap-register.json", stage5 + "file-manifest.json"],
        4: [stage5 + "protected-baseline.json"],
        5: [stage5 + "scope-isolation-report.json"],
        6: ["requirements/completion-requirements.json"],
        7: [stage5 + "cross-artifact-traceability.json"],
        8: [stage5 + "orphan-reference-review.json"],
        9: [stage5 + "cross-artifact-traceability.json"],
        10: ["requirements/requirement-proof-matrix.json"],
        11: ["architecture/requirement-architecture-map.json"],
        12: ["contracts/catalog.json"],
        13: ["oracles/invariants.json"],
        14: ["claims/claims.json"],
        15: [stage5 + "cross-artifact-traceability.json"],
        16: ["readiness/implementation-manifest.json"],
        17: ["readiness/implementation-manifest.json"],
        18: ["readiness/dependency-graph.json"],
        19: ["readiness/dependency-graph.json"],
        20: ["readiness/dependency-graph.json"],
        21: ["readiness/implementation-manifest.json"],
        22: ["readiness/implementation-manifest.json"],
        23: [stage5 + "risk-failure-rehearsal.json"],
        24: [stage5 + "risk-failure-rehearsal.json"],
        25: [stage5 + "risk-failure-rehearsal.json"],
        26: [stage5 + "historical-stage-reconciliation.json"],
        27: [stage5 + "command-rehearsal.json"],
        28: [stage5 + "resource-authorization-forecast.json"],
        29: [stage5 + "resource-authorization-forecast.json"],
        30: [stage5 + "skeptical-review.json"],
        31: ["docs/INTERVIEW_WALKTHROUGH.md"],
        32: [stage5 + "interview-rehearsal.json"],
        33: [stage5 + "claim-impact-review.json"],
        34: [stage5 + "claim-impact-review.json"],
        35: ["schemas/part1-closure.schema.json"],
        36: ["tests/fixtures/part1-closure/validator-mutations.json"],
        37: [stage5 + "validation-report.json"],
        38: [stage5 + "validation-report.json"],
        39: [stage5 + "determinism-report.json"],
        40: [stage5 + "artifact-manifest.json", stage5 + "stage-receipt.json"],
        41: ["external:exact-pr-head-ci"],
        42: ["external:policy-compliant-merge"],
        43: ["external:merged-main-ci"],
        44: ["external:part2-continuation-checkpoint"],
    }


def build_receipt(manifest: dict[str, Any]) -> dict[str, Any]:
    manifest_digest = hashlib.sha256(canonical_json(manifest).encode()).hexdigest()
    evidence = criterion_evidence()
    criteria = [
        {
            "id": f"ST5-AC-{index:02d}",
            "result": "PASS" if index <= 40 else "PENDING",
            "evidence": evidence[index],
        }
        for index in range(1, 45)
    ]
    return {
        "record_type": "stage_receipt",
        "contract_version": "1.0.0",
        "record_id": "changebridge-part1-stage5",
        "revision": 1,
        "evidence_refs": [
            MANIFEST_PATH.as_posix(),
            "evidence/part1/stage5/validation-report.json",
            "evidence/part1/stage5/determinism-report.json",
        ],
        "part": 1,
        "stage": 5,
        "base_commit": BASE_COMMIT,
        "candidate_commit": VALIDATED_COMMIT,
        "artifact_manifest_digest": manifest_digest,
        "criteria_total": 44,
        "criteria_passed": 40,
        "criteria_pending": 4,
        "criteria": criteria,
        "result": "PENDING_EXTERNAL_CLOSURE",
        "deferred_project_requirement": "CB-INTERVIEW-001",
        "limitations": [
            "The candidate commit binds the pre-receipt source and evidence freeze.",
            (
                "Criteria 41-44 require exact-head CI, merge, merged-main CI and the external "
                "Part 2 checkpoint."
            ),
            "The interview rehearsal remains mandatory at final ChangeBridge project completion.",
        ],
    }


def render(root: Path, *, check: bool) -> None:
    if not (
        len(VALIDATED_COMMIT) == 40
        and len(VALIDATED_TREE) == 40
        and all(character in "0123456789abcdef" for character in VALIDATED_COMMIT + VALIDATED_TREE)
    ):
        raise ValueError("CB5E004_SOURCE_FREEZE_NOT_BOUND")
    manifest = build_manifest(root)
    receipt = build_receipt(manifest)
    outputs = {
        MANIFEST_PATH: canonical_json(manifest),
        RECEIPT_PATH: canonical_json(receipt),
    }
    for relative, content in outputs.items():
        path = root / relative
        if check:
            if not path.is_file() or path.read_text(encoding="utf-8") != content:
                raise ValueError(f"CB5E003_EVIDENCE_DRIFT: {relative}")
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
