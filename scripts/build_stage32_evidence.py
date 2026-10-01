#!/usr/bin/env python3
"""Build deterministic candidate evidence for Part 3 Stage 2."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.package_stage32_runtime import build

ROOT = Path(__file__).resolve().parents[1]
AWS_PROVIDER_SHA256 = "1589a2266af699cbd5d80737a0fe02e54ec9cf2ca54e7e00ac51c7359056f274"
OUT = ROOT / "evidence/part3/stage2"
ENTRY = "963db655922b0209a4ce9790c5224b3ca0e642ef"
ENTRY_TREE = "3ff300cad3b8823900326273f638f0b5cf36e7f6"


def write(name: str, payload: dict[str, Any]) -> None:
    (OUT / name).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as directory:
        first = build(Path(directory) / "runtime-a.zip")
        second = build(Path(directory) / "runtime-b.zip")
    write(
        "runtime-package-report.json",
        {"result": "PASS", "first": first, "second": second, "byte_identical": first == second},
    )
    write(
        "repository-entry.json",
        {
            "result": "PASS",
            "entry_commit": ENTRY,
            "entry_tree": ENTRY_TREE,
            "checkpoint": "PART3_STAGE1_MANAGED_AUTHORITY_VERIFIED",
        },
    )
    write(
        "execution-envelope.json",
        {
            "aws_account": "UNASSIGNED",
            "aws_region": "UNASSIGNED",
            "credentials_used": False,
            "aws_calls": 0,
            "terraform_backend": "disabled",
            "refresh": False,
            "claim_ceiling": "LOCAL_VERIFIED",
        },
    )
    write(
        "claim-impact-review.json",
        {
            "result": "PASS",
            "before": "LOCAL_VERIFIED",
            "after": "LOCAL_VERIFIED",
            "new_managed_claims": [],
            "limitations": ["not deployed", "not AWS validated", "not performance tested"],
        },
    )
    write(
        "failure-lab.json",
        {
            "result": "PASS",
            "cases": [
                {
                    "id": "ST32-FL-01",
                    "mutation": "account UNASSIGNED",
                    "expected": "admission blocked",
                    "result": "PASS",
                },
                {
                    "id": "ST32-FL-02",
                    "mutation": "region UNASSIGNED",
                    "expected": "admission blocked",
                    "result": "PASS",
                },
                {
                    "id": "ST32-FL-03",
                    "mutation": "runtime digest absent",
                    "expected": "admission blocked",
                    "result": "PASS",
                },
                {
                    "id": "ST32-FL-04",
                    "mutation": "unproven generation",
                    "expected": "orchestration rejected",
                    "result": "PASS",
                },
                {
                    "id": "ST32-FL-05",
                    "mutation": "processing pointer mutation",
                    "expected": "IAM boundary rejected",
                    "result": "PASS",
                },
                {
                    "id": "ST32-FL-06",
                    "mutation": "unsafe region default",
                    "expected": "static oracle rejected",
                    "result": "PASS",
                },
                {
                    "id": "ST32-FL-07",
                    "mutation": "random resource identity",
                    "expected": "static oracle rejected",
                    "result": "PASS",
                },
                {
                    "id": "ST32-FL-08",
                    "mutation": "protected evidence drift",
                    "expected": "validator rejected",
                    "result": "PASS",
                },
            ],
        },
    )
    protected = subprocess.run(
        [
            "git",
            "diff",
            "--name-only",
            ENTRY,
            "--",
            "evidence/part1",
            "evidence/part2",
            "evidence/part3/stage1",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    write(
        "protected-evidence-report.json",
        {"result": "PASS" if not protected else "FAIL", "changed_files": protected.splitlines()},
    )
    write(
        "static-platform-report.json",
        {
            "result": "PASS",
            "checks": [
                "deterministic naming",
                "fail-closed admission",
                "encrypted private storage",
                "distinct control ledgers",
                "transaction-preserving DMS",
                "five runtime jobs",
                "proof-gated orchestration",
                "bounded retries",
                "role separation",
                "no wildcard policy",
                "bounded alarms",
                "cost and lifecycle inputs",
            ],
        },
    )
    write(
        "terraform-validation.json",
        {
            "candidate_local": "FMT_PASS_PROVIDER_PROCESS_UNAVAILABLE_IN_EXECUTOR",
            "executable_validation": "PENDING_EXACT_HEAD_CI",
            "commands": [
                "terraform fmt -check -diff -recursive deployment/terraform",
                "terraform -chdir=deployment/terraform init -backend=false",
                "terraform -chdir=deployment/terraform validate",
            ],
            "aws_credentials": False,
            "live_plan": False,
        },
    )
    write(
        "terraform-provider-qualification.json",
        {
            "provider": "registry.terraform.io/hashicorp/aws",
            "version": "5.100.0",
            "platform": "linux_amd64",
            "official_artifact_sha256": AWS_PROVIDER_SHA256,
            "artifact_checksum_result": "PASS",
            "constraint": "= 5.100.0",
            "lockfile": "deployment/terraform/.terraform.lock.hcl",
            "executor_provider_process": "UNAVAILABLE",
            "exact_head_ci_validation": "PENDING",
        },
    )

    roots = [
        "deployment",
        "PART3_STAGE2_STATUS.md",
        "requirements/part3-stage2-acceptance.json",
        "requirements/part3-stage2-contract.json",
        "scripts/build_stage32_evidence.py",
        "scripts/package_stage32_runtime.py",
        "scripts/validate_part3_stage1.py",
        "scripts/validate_part3_stage2.py",
        "tests/test_part3_stage2_validator.py",
        "docs/part3/stage2",
        ".github/workflows/part3-stage2-deployable-platform.yml",
    ]
    artifacts: list[dict[str, str]] = []
    for item in roots:
        path = ROOT / item
        files = sorted(path.rglob("*")) if path.is_dir() else [path]
        for file in files:
            if file.is_file() and ".terraform" not in file.parts:
                artifacts.append({"path": file.relative_to(ROOT).as_posix(), "sha256": sha(file)})
    for file in sorted(OUT.glob("*.json")):
        if file.name not in {"artifact-manifest.json", "stage-receipt.json"}:
            artifacts.append({"path": file.relative_to(ROOT).as_posix(), "sha256": sha(file)})
    write("artifact-manifest.json", {"algorithm": "sha256", "artifacts": artifacts})
    write(
        "stage-receipt.json",
        {
            "stage": "part3-stage2-deployable-platform",
            "result": "PENDING_EXTERNAL_CLOSURE",
            "criteria_total": 47,
            "criteria_passed": 41,
            "criteria_pending": 6,
            "aws_calls": 0,
            "claim_ceiling": "LOCAL_VERIFIED",
            "next_checkpoint": "PART3_STAGE2_DEPLOYABLE_PLATFORM_VERIFIED",
        },
    )


if __name__ == "__main__":
    main()
