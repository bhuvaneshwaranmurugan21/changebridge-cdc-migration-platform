#!/usr/bin/env python3
"""Build deterministic pre-authorization evidence for Part 3 Stage 3."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evidence/part3/stage3"
ENTRY = "084407a972d2d3f937e8ac670733f198dd4b0179"
ENTRY_TREE = "3a5ceefaf9dcfcbe97da5a593f76eab0cd5fe257"


def write(name: str, payload: dict[str, Any]) -> None:
    (OUT / name).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    write(
        "repository-entry.json",
        {
            "result": "PASS",
            "entry_commit": ENTRY,
            "entry_tree": ENTRY_TREE,
            "checkpoint": "PART3_STAGE2_DEPLOYABLE_PLATFORM_VERIFIED",
            "branch": "part3-stage3-aws-admission",
        },
    )
    write(
        "operator-observation.json",
        {
            "result": "PASS",
            "observed_at_utc": "2026-10-01T10:18:19Z",
            "account_id": "857229544428",
            "region": "ap-southeast-2",
            "role": "AccountFullAccessRole",
            "role_session": "REDACTED",
            "alert_endpoint": "VERIFIED_REDACTED",
            "shared_budget": {
                "name": "portfolio-labs-monthly-cost",
                "limit_usd_monthly": 20,
                "alerts": ["ACTUAL_50_PERCENT", "ACTUAL_80_PERCENT", "FORECASTED_100_PERCENT"],
            },
            "portfolio_credit_context_usd": 140,
            "portfolio_credit_is_stage_allowance": False,
            "aws_mutations": 0,
        },
    )
    write(
        "predecessor-external-closure.json",
        {
            "result": "PASS",
            "pull_request": 15,
            "reviewed_head": "daa39539ff9d32340a87a3caa0d8a84c06a726a7",
            "exact_head_checks_passed": 2,
            "merge_commit": ENTRY,
            "merge_tree": ENTRY_TREE,
            "fresh_origin_main_verified": True,
            "checkpoint": "PART3_STAGE2_DEPLOYABLE_PLATFORM_VERIFIED",
            "note": (
                "The committed candidate receipt remains historically pending; external closure "
                "is independently reconstructed from the exact-head checks and merged main "
                "identity."
            ),
        },
    )
    protected = git(
        "diff",
        "--name-only",
        ENTRY,
        "--",
        "evidence/part1",
        "evidence/part2",
        "evidence/part3/stage1",
        "evidence/part3/stage2",
    )
    write(
        "protected-evidence-report.json",
        {"result": "PASS" if not protected else "FAIL", "changed_files": protected.splitlines()},
    )
    write(
        "authorization-state.json",
        {
            "result": "PASS",
            "read_only_qualification_authorized": True,
            "repository_preparation_authorized": True,
            "aws_mutation_authorized": False,
            "exact_bootstrap_authorization": "PENDING",
            "managed_workload_authorized": False,
        },
    )
    write(
        "qualification-gaps.json",
        {
            "result": "BLOCKED_AS_DESIGNED",
            "pending": [
                "candidate-role exact trust observation (role is absent)",
                "candidate role permission and boundary observation (role is absent)",
                "complete bounded quota usage/headroom comparison",
                "bounded cost estimate acceptance",
                "48-hour lifetime versus retention and KMS deletion-window correction",
                "fresh timestamped pre-mutation qualification",
                "exact-resource mutation authorization",
                "complete repository quality validation (partial suite coverage failed)",
            ],
            "closed_observation_gaps": [
                "received evidence archive and member integrity",
                "OIDC provider and audience observation",
                "resource name collision observations",
                "regional service read API availability",
                "quota ceiling and network observations",
            ],
        },
    )
    roots = [
        "requirements/part3-stage3-contract.json",
        "requirements/part3-stage3-acceptance.json",
        "deployment/stage3",
        "docs/part3/stage3",
        "scripts/collect_stage33_readonly.sh",
        "scripts/build_stage33_evidence.py",
        "scripts/validate_part3_stage3.py",
        "tests/test_part3_stage3_validator.py",
        "tests/test_stage33_oidc_qualification.py",
        ".github/workflows/aws-oidc-identity.yml",
        ".github/workflows/part3-stage3-aws-admission.yml",
        "PART3_STAGE3_STATUS.md",
    ]
    artifacts: list[dict[str, str]] = []
    for item in roots:
        path = ROOT / item
        files = sorted(path.rglob("*")) if path.is_dir() else [path]
        for file in files:
            if file.is_file():
                artifacts.append({"path": file.relative_to(ROOT).as_posix(), "sha256": sha(file)})
    for file in sorted(OUT.glob("*.json")):
        if file.name not in {"artifact-manifest.json", "stage-receipt.json"}:
            artifacts.append({"path": file.relative_to(ROOT).as_posix(), "sha256": sha(file)})
    write("artifact-manifest.json", {"algorithm": "sha256", "artifacts": artifacts})
    write(
        "stage-receipt.json",
        {
            "stage": "part3-stage3-aws-admission",
            "result": "PENDING_AUTHORITY_CORRECTION_AND_BOOTSTRAP_AUTHORIZATION",
            "criteria_total": 52,
            "criteria_passed": 32,
            "criteria_pending": 20,
            "focused_validation": "PASS",
            "broader_quality_validation": "NOT_PASSED_PARTIAL_SUITE_COVERAGE_FAILURE",
            "aws_calls": "READ_ONLY_OPERATOR_OBSERVATIONS",
            "aws_mutations": 0,
            "claim_ceiling": "AWS_ADMISSION_OBSERVED",
            "next_checkpoint": "PART3_STAGE3_AWS_ADMISSION_VERIFIED",
        },
    )


if __name__ == "__main__":
    main()
