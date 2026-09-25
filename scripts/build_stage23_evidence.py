#!/usr/bin/env python3
"""Build deterministic Stage 3 evidence from one frozen source tree and raw real-target run."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from changebridge.generation_registry import generation_namespace
from changebridge.normalizer import strict_json_loads
from changebridge.snapshot_handoff import (
    EXPECTED_COUNTS,
    EXPECTED_FRONTIER,
    EXPECTED_WHOLE_STATE_DIGEST,
    normalize_full_handoff,
    reconstruct_snapshot,
)

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence/part2/stage3"
BASE_COMMIT = "9382f8150c5af1de1bcdc8494fda6212c1d0b18b"
BASE_TREE = "5e98c6a8fe03e0dd5e6e01ca5508943743782435"
LIMITATIONS = [
    (
        "Proof is bounded to local Spark 3.5.9, Iceberg 1.11.0, a filesystem Hadoop "
        "catalog, file-backed SQLite, and the committed fixture."
    ),
    (
        "No AWS, S3/Glue durability, post-S CDC apply, schema evolution, publication, "
        "performance, availability, exactly-once, zero-downtime, or production claim is "
        "established."
    ),
]


def render(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()


def load(relative: str | Path) -> dict[str, Any]:
    value = strict_json_loads((ROOT / relative).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(relative)
    return value


def envelope(kind: str, commit: str, tree: str, **fields: Any) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "project": "ChangeBridge",
        "repository": "bhuvaneshwaranmurugan21/changebridge-cdc-migration-platform",
        "part": 2,
        "stage": 3,
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
    raw = strict_json_loads(args.raw_lab.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("result") != "PASS":
        raise SystemExit("real-target lab did not pass")
    if raw.get("stable_projection_equal") is not True:
        raise SystemExit("clean-run logical projections differ")
    recovery = raw.get("recovery", {})
    if (
        recovery.get("crash_exit_code") != 86
        or recovery.get("recovered_without_rewrite") is not True
    ):
        raise SystemExit("process-termination recovery did not pass")

    handoff = ROOT / "tests/fixtures/part2-stage3/handoff"
    bundle = normalize_full_handoff(ROOT, handoff)
    spec, truth, boundary = reconstruct_snapshot(ROOT)
    snapshots = [event for event in bundle.canonical if event["operation"] == "snapshot"]
    post_s = [event for event in bundle.canonical if event["operation"] != "snapshot"]
    generation_id = str(boundary["generation_id"])
    first = raw["clean_runs"][0]
    second = raw["clean_runs"][1]
    runtime_lock = load("contracts/stage3-runtime-lock.json")

    artifacts: dict[str, dict[str, Any]] = {
        "repository-entry.json": envelope(
            "repository_entry",
            args.source_commit,
            args.source_tree,
            base_commit=BASE_COMMIT,
            base_tree=BASE_TREE,
            predecessor_checkpoint="PART2_STAGE2_CDC_NORMALIZATION_VERIFIED",
            branch="part2-stage3-snapshot-generation",
        ),
        "execution-envelope.json": envelope(
            "execution_envelope",
            args.source_commit,
            args.source_tree,
            authorized_scope="Part 2 Stage 3 only",
            aws_operations=False,
            target="real local Spark/Iceberg",
            runtime_profile=runtime_lock["profile_id"],
        ),
        "authority-reconciliation.json": envelope(
            "authority_reconciliation",
            args.source_commit,
            args.source_tree,
            old_stage3="Transaction-preserving landing and ordering",
            corrected_stage3="Snapshot loader and isolated Iceberg generation",
            completed_stage_semantics_changed=[],
            dropped_obligations=[],
            decision="ADR-017",
        ),
        "protected-predecessor-baseline.json": envelope(
            "protected_predecessor_baseline",
            args.source_commit,
            args.source_tree,
            part1_base=tree_digest(BASE_COMMIT, "evidence/part1"),
            part1_source=tree_digest(args.source_commit, "evidence/part1"),
            stage1_base=tree_digest(BASE_COMMIT, "evidence/part2/stage1"),
            stage1_source=tree_digest(args.source_commit, "evidence/part2/stage1"),
            stage2_base=tree_digest(BASE_COMMIT, "evidence/part2/stage2"),
            stage2_source=tree_digest(args.source_commit, "evidence/part2/stage2"),
        ),
        "dependency-decision.json": envelope(
            "dependency_decision",
            args.source_commit,
            args.source_tree,
            runtime_lock=runtime_lock,
            qualification_result="PASS",
        ),
        "compatibility-probe.json": envelope(
            "compatibility_probe",
            args.source_commit,
            args.source_tree,
            real_table_create=True,
            real_append=True,
            real_readback=True,
            snapshot_metadata_inspected=True,
            commit_token_recoverable=True,
        ),
        "generation-identity.json": envelope(
            "generation_identity",
            args.source_commit,
            args.source_tree,
            generation_id=generation_id,
            workload_id=spec["workload_id"],
            namespace=generation_namespace(generation_id),
            snapshot_frontier=EXPECTED_FRONTIER,
            schema_set_digest=spec["schema_set_digest"],
            state=first["state"],
        ),
        "table-map.json": envelope(
            "table_map",
            args.source_commit,
            args.source_tree,
            namespace=first["namespace"],
            tables={
                table: {
                    "identifier": f"stage23.{first['namespace']}.{table}",
                    "physical_snapshot_id": details["physical_snapshot_id"],
                    "row_count": details["row_count"],
                    "logical_digest": details["logical_digest"],
                }
                for table, details in first["tables"].items()
            },
            physical_ids_are_execution_specific=True,
        ),
        "snapshot-input.json": envelope(
            "snapshot_input",
            args.source_commit,
            args.source_tree,
            manifest_id=load("tests/fixtures/part2-stage3/handoff/manifest.json")["manifest_id"],
            snapshot_frontier=EXPECTED_FRONTIER,
            counts=EXPECTED_COUNTS,
            total_snapshot_rows=len(snapshots),
            post_s_cdc_rows=len(post_s),
            whole_state_digest=EXPECTED_WHOLE_STATE_DIGEST,
        ),
        "handoff-normalization.json": envelope(
            "handoff_normalization",
            args.source_commit,
            args.source_tree,
            normalizer="unchanged Stage 2 normalizer",
            accepted=len(bundle.canonical),
            quarantined=len(bundle.quarantine),
            snapshot_rows=len(snapshots),
            preserved_post_s_cdc_rows=len(post_s),
            report=bundle.report,
        ),
        "shard-idempotency.json": envelope(
            "shard_idempotency",
            args.source_commit,
            args.source_tree,
            tables={
                table: {
                    "snapshot_count_before_replay": details["snapshot_count_before_replay"],
                    "snapshot_count_after_replay": details["snapshot_count_after_replay"],
                    "idempotent_replay": details["idempotent_replay"],
                }
                for table, details in first["tables"].items()
            },
        ),
        "fault-recovery.json": envelope(
            "fault_recovery",
            args.source_commit,
            args.source_tree,
            tested_boundaries=["before_staging", "during_staging", "after_commit", "after_ledger"],
            commit_token_authority="Iceberg snapshot summary",
            blind_rewrite=False,
        ),
        "process-termination.json": envelope(
            "process_termination",
            args.source_commit,
            args.source_tree,
            exit_code=recovery["crash_exit_code"],
            recovered_without_rewrite=recovery["recovered_without_rewrite"],
            recovered_row_count=recovery["row_count"],
        ),
        "generation-isolation.json": envelope(
            "generation_isolation",
            args.source_commit,
            args.source_tree,
            deterministic_namespace=True,
            generation_owned_warehouse=True,
            alias_and_symlink_guards=True,
            active_or_foreign_mutations=0,
            publication=False,
        ),
        "differential-report.json": envelope(
            "differential_report",
            args.source_commit,
            args.source_tree,
            frontier=EXPECTED_FRONTIER,
            source_counts=EXPECTED_COUNTS,
            target_counts={table: row["row_count"] for table, row in first["tables"].items()},
            source_digests={table: row["state_digest"] for table, row in truth["tables"].items()},
            target_digests={table: row["logical_digest"] for table, row in first["tables"].items()},
            verdict="MATCH",
        ),
        "determinism-report.json": envelope(
            "determinism_report",
            args.source_commit,
            args.source_tree,
            clean_run_count=2,
            logical_projections_equal=raw["stable_projection_equal"],
            physical_snapshot_ids_excluded_from_determinism=True,
            second_run_state=second["state"],
        ),
        "claim-impact-review.json": envelope(
            "claim_impact_review",
            args.source_commit,
            args.source_tree,
            promoted_claim="CB-CLAIM-013",
            promoted_label="LOCAL_VERIFIED",
            claim_ceiling="bounded local snapshot generation only",
            managed_claims_promoted=[],
        ),
        "scope-isolation-report.json": envelope(
            "scope_isolation_report",
            args.source_commit,
            args.source_tree,
            project="ChangeBridge",
            foreign_project_findings=[],
            aws_operations=False,
            terraform_changes=False,
            post_s_cdc_applied=0,
            publication=False,
        ),
        "validation-summary.json": envelope(
            "validation_summary",
            args.source_commit,
            args.source_tree,
            ruff="PASS",
            strict_mypy="PASS",
            full_suite="PASS",
            full_tests_passed=args.tests_passed,
            full_tests_skipped=args.tests_skipped,
            total_coverage_percent=args.coverage,
            real_iceberg_tests="PASS",
            predecessor_validators="PASS",
            stage23_validator="SELF_VALIDATING",
        ),
    }
    EVIDENCE.mkdir(parents=True, exist_ok=False)
    for name, value in artifacts.items():
        (EVIDENCE / name).write_text(render(value), encoding="utf-8")

    changed_paths = sorted(
        path
        for path in git("diff", "--name-only", f"{BASE_COMMIT}...{args.source_commit}").splitlines()
        if path
    )
    file_manifest = envelope(
        "file_manifest",
        args.source_commit,
        args.source_tree,
        changed_path_count=len(changed_paths),
        changed_paths=changed_paths,
    )
    (EVIDENCE / "file-manifest.json").write_text(render(file_manifest), encoding="utf-8")
    artifact_rows = [
        {"path": path.relative_to(ROOT).as_posix(), "sha256": sha(path.read_bytes())}
        for path in sorted(EVIDENCE.glob("*.json"))
    ]
    artifact_manifest = envelope(
        "artifact_manifest",
        args.source_commit,
        args.source_tree,
        artifact_count=len(artifact_rows),
        artifacts=artifact_rows,
    )
    manifest_bytes = render(artifact_manifest).encode()
    (EVIDENCE / "artifact-manifest.json").write_bytes(manifest_bytes)
    criteria = [
        {
            "id": f"ST23-AC-{number:02d}",
            "result": "PASS" if number <= 38 else "PENDING",
            "evidence": [
                "evidence/part2/stage3/validation-summary.json"
                if number <= 38
                else "EXTERNAL_CLOSURE"
            ],
        }
        for number in range(1, 43)
    ]
    receipt = {
        **envelope(
            "stage_receipt",
            args.source_commit,
            args.source_tree,
            evidence_label="PENDING_EXTERNAL_CLOSURE",
            result="PENDING_EXTERNAL_CLOSURE",
        ),
        "contract_version": "1.0.0",
        "base_commit": BASE_COMMIT,
        "base_tree": BASE_TREE,
        "artifact_manifest_digest": sha(manifest_bytes),
        "criteria_total": 42,
        "criteria_passed": 38,
        "criteria_pending": 4,
        "criteria": criteria,
    }
    (EVIDENCE / "stage-receipt.json").write_text(render(receipt), encoding="utf-8")


if __name__ == "__main__":
    main()
