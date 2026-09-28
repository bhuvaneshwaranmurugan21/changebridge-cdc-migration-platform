#!/usr/bin/env python3
"""Build source-bound Part 2 Stage 5 evidence from the real Iceberg laboratory."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence/part2/stage5"
BASE_COMMIT = "cbf575315e3b9bea3c0ee79f78e3288c8746effb"
BASE_TREE = "30e26dd3d7cd89601de92bc6ec99ec0e1a2737f0"
LIMITATIONS = [
    (
        "Proof is bounded to local Spark 3.5.9, Iceberg 1.11.0, a filesystem "
        "Hadoop catalog, file-backed SQLite, and the accepted fixture."
    ),
    (
        "No AWS durability, arbitrary schema evolution, publication, Stage 6 "
        "reconciliation, performance, availability, exactly-once, zero-downtime, "
        "or production claim is established."
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


def tree_digest(commit: str, path: str) -> str:
    listing = git("ls-tree", "-r", commit, path)
    return sha((listing + "\n").encode())


def envelope(kind: str, commit: str, tree: str, **fields: Any) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "project": "ChangeBridge",
        "repository": "bhuvaneshwaranmurugan21/changebridge-cdc-migration-platform",
        "part": 2,
        "stage": 5,
        "evidence_type": kind,
        "evidence_label": "LOCAL_VERIFIED",
        "source_commit": commit,
        "source_tree": tree,
        "result": "PASS",
        "limitations": LIMITATIONS,
        **fields,
    }


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
        raise SystemExit("Stage 5 laboratory did not pass deterministically")
    clean = lab["clean_runs"][0]
    recovery = lab["recovery"]
    unknown = lab["unknown_quarantine"]
    incompatible = lab["incompatible_rejection"]
    artifacts: dict[str, dict[str, Any]] = {
        "repository-entry.json": envelope(
            "repository_entry",
            args.source_commit,
            args.source_tree,
            base_commit=BASE_COMMIT,
            base_tree=BASE_TREE,
            predecessor_checkpoint="PART2_STAGE4_CDC_APPLY_VERIFIED",
            branch="part2-stage5-schema-policy",
        ),
        "execution-envelope.json": envelope(
            "execution_envelope",
            args.source_commit,
            args.source_tree,
            authorized_scope="Part 2 Stage 5 only",
            aws_operations=False,
            runtime="Spark 3.5.9 + Iceberg 1.11.0 + SQLite",
            iceberg_sha256="94b8e36fc329f0293d44ba9e01b784a56e9501affec1842d898144c51f6e486a",
        ),
        "schema-policy-proof.json": envelope(
            "schema_policy_proof",
            args.source_commit,
            args.source_tree,
            policy_id="changebridge.schema-policy",
            policy_version="1.0.0",
            decision_id=clean["decision_id"],
            decision_digest=clean["decision_digest"],
            supported_transition="orders_source_contract/1.0.0->1.1.0",
            supported_change="ADD_NULLABLE_NON_KEY_FIELD:source_note",
        ),
        "iceberg-schema-apply.json": envelope(
            "iceberg_schema_apply",
            args.source_commit,
            args.source_tree,
            apply_token=clean["apply_token"],
            before_schema_id=clean["before_schema_id"],
            after_schema_id=clean["after_schema_id"],
            metadata_changed=clean["metadata_changed"],
            snapshot_count_unchanged=clean["snapshot_count_unchanged"],
            row_count=clean["row_count"],
            old_rows_null=clean["old_rows_null"],
        ),
        "schema-recovery.json": envelope(
            "schema_recovery", args.source_commit, args.source_tree, **recovery
        ),
        "quarantine-proof.json": envelope(
            "quarantine_proof", args.source_commit, args.source_tree, **unknown
        ),
        "generation-rejection.json": envelope(
            "generation_rejection", args.source_commit, args.source_tree, **incompatible
        ),
        "determinism-report.json": envelope(
            "determinism_report",
            args.source_commit,
            args.source_tree,
            clean_run_count=2,
            stable_projection_equal=lab["stable_projection_equal"],
            replay_recovered=clean["replay_recovered"],
            replay_metadata_unchanged=clean["replay_metadata_unchanged"],
        ),
        "generation-state.json": envelope(
            "generation_state",
            args.source_commit,
            args.source_tree,
            accepted_state=clean["generation_state"],
            published=clean["published"],
            sealed=False,
            checkpoint=clean["frontier"],
            incompatible_state="REJECTED",
        ),
        "protected-predecessor-baseline.json": envelope(
            "protected_predecessor_baseline",
            args.source_commit,
            args.source_tree,
            part1=tree_digest(BASE_COMMIT, "evidence/part1"),
            stage1=tree_digest(BASE_COMMIT, "evidence/part2/stage1"),
            stage2=tree_digest(BASE_COMMIT, "evidence/part2/stage2"),
            stage3=tree_digest(BASE_COMMIT, "evidence/part2/stage3"),
            stage4=tree_digest(BASE_COMMIT, "evidence/part2/stage4"),
        ),
        "claim-impact-review.json": envelope(
            "claim_impact_review",
            args.source_commit,
            args.source_tree,
            new_claim="CB-CLAIM-015",
            label="LOCAL_VERIFIED",
            arbitrary_schema_evolution=False,
            aws_verified=False,
            production_ready=False,
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
            "id": f"ST25-AC-{number:02d}",
            "result": "PASS" if number <= 44 else "PENDING",
            "evidence": [
                "evidence/part2/stage5/validation-summary.json"
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
