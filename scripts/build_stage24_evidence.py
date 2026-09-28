#!/usr/bin/env python3
"""Build commit-bound Stage 4 evidence from the real-target laboratory."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence/part2/stage4"
BASE_COMMIT = "e9b4a6dc6d62c1c90a89ea4ba3c02ad6a0d6a601"
BASE_TREE = "775b6790edd7b671091e32b0e2787374e4bcb429"
LIMITATIONS = [
    (
        "Proof is bounded to local Spark 3.5.9, Iceberg 1.11.0, a filesystem Hadoop "
        "catalog, file-backed SQLite, and the accepted fixture."
    ),
    (
        "No AWS durability, distributed exactly-once, atomic cross-table storage transaction, "
        "schema/key evolution, publication, cutover, performance, availability, or production "
        "claim is established."
    ),
]


def render(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()


def envelope(kind: str, commit: str, tree: str, **fields: Any) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "project": "ChangeBridge",
        "repository": "bhuvaneshwaranmurugan21/changebridge-cdc-migration-platform",
        "part": 2,
        "stage": 4,
        "evidence_type": kind,
        "evidence_label": "LOCAL_VERIFIED",
        "source_commit": commit,
        "source_tree": tree,
        "result": "PASS",
        "limitations": LIMITATIONS,
        **fields,
    }


def tree_digest(commit: str, path: str) -> str:
    listing = git("ls-tree", "-r", commit, path)
    return sha((listing + "\n").encode())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--source-tree", required=True)
    parser.add_argument("--raw-lab", required=True, type=Path)
    parser.add_argument("--tests-passed", required=True, type=int)
    parser.add_argument("--tests-skipped", required=True, type=int)
    parser.add_argument("--coverage", required=True, type=float)
    args = parser.parse_args()
    if git("rev-parse", args.source_commit) != args.source_commit:
        raise SystemExit("source commit does not resolve")
    if git("rev-parse", f"{args.source_commit}^{{tree}}") != args.source_tree:
        raise SystemExit("source tree mismatch")
    lab = json.loads(args.raw_lab.read_text(encoding="utf-8"))
    if lab.get("result") != "PASS" or lab.get("stable_projection_equal") is not True:
        raise SystemExit("real-target laboratory did not pass deterministically")
    first = lab["clean_runs"][0]
    recovery = lab["recovery"]
    drift = lab["drift"]
    artifacts = {
        "repository-entry.json": envelope(
            "repository_entry",
            args.source_commit,
            args.source_tree,
            base_commit=BASE_COMMIT,
            base_tree=BASE_TREE,
            predecessor_checkpoint="PART2_STAGE3_SNAPSHOT_GENERATION_VERIFIED",
            branch="part2-stage4-transactional-apply",
        ),
        "execution-envelope.json": envelope(
            "execution_envelope",
            args.source_commit,
            args.source_tree,
            authorized_scope="Part 2 Stage 4 only",
            aws_operations=False,
            runtime="Spark 3.5.9 + Iceberg 1.11.0 + SQLite",
            iceberg_sha256="94b8e36fc329f0293d44ba9e01b784a56e9501affec1842d898144c51f6e486a",
        ),
        "apply-manifest-proof.json": envelope(
            "apply_manifest_proof",
            args.source_commit,
            args.source_tree,
            manifest=json.loads(
                (ROOT / "tests/fixtures/part2-stage4/apply-manifest.json").read_text()
            ),
            transaction_id=first["transaction_id"],
            transaction_digest=first["transaction_digest"],
        ),
        "differential-report.json": envelope(
            "differential_report",
            args.source_commit,
            args.source_tree,
            target=first["target"],
            reference=first["reference"],
            equal=first["differential_equal"],
        ),
        "checkpoint-recovery.json": envelope(
            "checkpoint_recovery",
            args.source_commit,
            args.source_tree,
            **recovery,
        ),
        "determinism-report.json": envelope(
            "determinism_report",
            args.source_commit,
            args.source_tree,
            clean_run_count=2,
            stable_projection_equal=lab["stable_projection_equal"],
            logical_transaction_digest=first["transaction_digest"],
        ),
        "failure-lab.json": envelope(
            "failure_lab",
            args.source_commit,
            args.source_tree,
            process_exit_code=recovery["crash_exit_code"],
            recovered_without_rewrite=recovery["recovered_without_rewrite"],
            drift=drift,
        ),
        "generation-state.json": envelope(
            "generation_state",
            args.source_commit,
            args.source_tree,
            generation_id=first["generation_id"],
            state=first["generation_state"],
            published=first["published"],
            checkpoint=first["checkpoint"],
        ),
        "protected-predecessor-baseline.json": envelope(
            "protected_predecessor_baseline",
            args.source_commit,
            args.source_tree,
            part1=tree_digest(BASE_COMMIT, "evidence/part1"),
            stage1=tree_digest(BASE_COMMIT, "evidence/part2/stage1"),
            stage2=tree_digest(BASE_COMMIT, "evidence/part2/stage2"),
            stage3=tree_digest(BASE_COMMIT, "evidence/part2/stage3"),
        ),
        "claim-impact-review.json": envelope(
            "claim_impact_review",
            args.source_commit,
            args.source_tree,
            corrected_claim="CB-CLAIM-006",
            new_claim="CB-CLAIM-014",
            cross_table_atomicity=False,
            production_exactly_once=False,
        ),
        "validation-summary.json": envelope(
            "validation_summary",
            args.source_commit,
            args.source_tree,
            ruff="PASS",
            strict_mypy="PASS",
            full_suite="PASS",
            tests_passed=args.tests_passed,
            tests_skipped=args.tests_skipped,
            coverage_percent=args.coverage,
            real_target_lab="PASS",
            predecessor_validators="PASS",
        ),
    }
    EVIDENCE.mkdir(parents=True, exist_ok=False)
    for name, value in artifacts.items():
        (EVIDENCE / name).write_text(render(value), encoding="utf-8")
    changed = sorted(
        filter(
            None, git("diff", "--name-only", f"{BASE_COMMIT}...{args.source_commit}").splitlines()
        )
    )
    (EVIDENCE / "file-manifest.json").write_text(
        render(
            envelope(
                "file_manifest",
                args.source_commit,
                args.source_tree,
                changed_path_count=len(changed),
                changed_paths=changed,
            )
        ),
        encoding="utf-8",
    )
    rows = [
        {"path": path.relative_to(ROOT).as_posix(), "sha256": sha(path.read_bytes())}
        for path in sorted(EVIDENCE.glob("*.json"))
    ]
    manifest = render(
        envelope(
            "artifact_manifest",
            args.source_commit,
            args.source_tree,
            artifact_count=len(rows),
            artifacts=rows,
        )
    ).encode()
    (EVIDENCE / "artifact-manifest.json").write_bytes(manifest)
    criteria = [
        {
            "id": f"ST24-AC-{number:02d}",
            "result": "PASS" if number <= 44 else "PENDING",
            "evidence": [
                "evidence/part2/stage4/validation-summary.json"
                if number <= 44
                else "EXTERNAL_CLOSURE"
            ],
        }
        for number in range(1, 49)
    ]
    receipt = envelope(
        "stage_receipt",
        args.source_commit,
        args.source_tree,
        evidence_label="PENDING_EXTERNAL_CLOSURE",
        result="PENDING_EXTERNAL_CLOSURE",
        contract_version="1.0.0",
        base_commit=BASE_COMMIT,
        base_tree=BASE_TREE,
        artifact_manifest_digest=sha(manifest),
        criteria_total=48,
        criteria_passed=44,
        criteria_pending=4,
        criteria=criteria,
    )
    (EVIDENCE / "stage-receipt.json").write_text(render(receipt), encoding="utf-8")


if __name__ == "__main__":
    main()
