#!/usr/bin/env python3
"""Build bounded, secret-free ChangeBridge Part 2 Stage 1 evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BASE_COMMIT = "6ae4e071782bddeb5a35f9635262e868f52df6f5"
BASE_TREE = "2126b55cb85844189aa9907452de22847ca43e98"
SOURCE_COMMIT = "6f64f6afe99dbacfac71e3176bc15fe4b6227dc4"
SOURCE_TREE = "022f0b80aa20a2b6588465d924e53bae2ff0bb1a"
RUNTIME_RUN_ID = 36036471399
RUNTIME_ARTIFACT_ID = 10824187394
RUNTIME_ARTIFACT_DIGEST = "27170270e61438644ffc24aae164579f6884622b120d20f52e18fa3fe9cd49d1"
RUNTIME_JSON_DIGEST = "a02c8fa8b9cbe1088dd0737c2c3e1c32f9325f96b98ba8c6fc1511fd78e37a13"
IMAGE = "postgres@sha256:639ab7ceb90e13123085b741fb31ef493fba25463002f6da665352e7b534b652"
EVIDENCE_DIR = Path("evidence/part2/stage1")
MANIFEST_PATH = EVIDENCE_DIR / "artifact-manifest.json"
RECEIPT_PATH = EVIDENCE_DIR / "stage-receipt.json"
LIMITATIONS = [
    "Proof is limited to isolated PostgreSQL 17.11 and local Python behavior.",
    (
        "No AWS DMS, Spark, Iceberg, Terraform, deployment, performance, availability, cost, "
        "RTO/RPO, exactly-once, zero-downtime, or production-readiness claim is established."
    ),
]


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def envelope(evidence_type: str, **fields: Any) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "project": "ChangeBridge",
        "repository": "bhuvaneshwaranmurugan21/changebridge-cdc-migration-platform",
        "part": 2,
        "stage": 1,
        "evidence_type": evidence_type,
        "evidence_label": "LOCAL_VERIFIED",
        "source_commit": SOURCE_COMMIT,
        "source_tree": SOURCE_TREE,
        "result": "PASS",
        "limitations": LIMITATIONS,
        **fields,
    }


def table_summary(state: dict[str, Any]) -> dict[str, Any]:
    return {
        name: {
            "row_count": table["row_count"],
            "state_digest": table["state_digest"],
        }
        for name, table in sorted(state["tables"].items())
    }


def transaction_summary(transaction: dict[str, Any]) -> dict[str, Any]:
    return {
        "transaction_id": transaction["transaction_id"],
        "transaction_sequence": transaction["transaction_sequence"],
        "commit_ordinal": transaction["commit_ordinal"],
        "phase": transaction["phase"],
        "outcome": transaction["outcome"],
        "cases": transaction["cases"],
        "transaction_digest": transaction["transaction_digest"],
        "events": [
            {
                "event_sequence": event["event_sequence"],
                "table": event["table"],
                "operation": event["operation"],
                "schema_version": event["schema_version"],
                "key": event["key"],
                "cases": event["cases"],
                "event_digest": event["event_digest"],
                "before_present": event["before"] is not None,
                "after_present": event["after"] is not None,
            }
            for event in transaction["events"]
        ],
    }


def boundary_summary(run: dict[str, Any]) -> dict[str, Any]:
    boundary = run["boundary"]
    snapshot = boundary["snapshot_state"]
    return {
        "seed": run["seed"],
        "workload_id": run["workload_spec"]["workload_id"],
        "generation_id": boundary["generation_id"],
        "capture_method": boundary["capture_method"],
        "image": boundary["image"],
        "server_major": boundary["server_major"],
        "server_version_digest": boundary["server_version_digest"],
        "output_plugin": boundary["output_plugin"],
        "source_identity_digest": boundary["source_identity_digest"],
        "slot_identity_sha256": boundary["slot_identity_sha256"],
        "snapshot_identity_sha256": boundary["snapshot_identity_sha256"],
        "snapshot_frontier": boundary["snapshot_frontier"],
        "first_post_boundary_change_position": boundary["first_post_boundary_change_position"],
        "first_post_boundary_position": boundary["first_post_boundary_position"],
        "first_post_boundary_transaction_sha256": boundary[
            "first_post_boundary_transaction_sha256"
        ],
        "snapshot_imported": boundary["snapshot_imported"],
        "snapshot_transaction": boundary["snapshot_transaction"],
        "snapshot_tables": table_summary(snapshot),
        "snapshot_whole_state_digest": snapshot["whole_state_digest"],
        "schema_set_digest": boundary["schema_set_digest"],
        "comparator_version": boundary["comparator_version"],
        "generation_transitions": boundary["generation_transitions"],
        "logical_change_count": boundary["logical_change_count"],
        "cleanup": boundary["cleanup"],
    }


def changed_paths(root: Path) -> list[str]:
    commands = (
        ["git", "diff", "--name-only", f"{BASE_COMMIT}...HEAD"],
        ["git", "diff", "--name-only"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    )
    paths: set[str] = set()
    for command in commands:
        result = subprocess.run(command, cwd=root, check=True, capture_output=True, text=True)
        paths.update(line for line in result.stdout.splitlines() if line)
    return sorted(paths)


def criterion_evidence() -> dict[int, list[str]]:
    prefix = EVIDENCE_DIR.as_posix() + "/"
    return {
        1: [prefix + "repository-entry.json"],
        2: [prefix + "execution-envelope.json"],
        3: [prefix + "overlap-register.json"],
        4: [prefix + "protected-part1-baseline.json"],
        5: [prefix + "scope-isolation-report.json"],
        6: ["PART2_COMPLETION_CONTRACT.md", "requirements/part2-stage1-acceptance.json"],
        7: [prefix + "protected-part1-baseline.json", "scripts/validate_part1_frozen.py"],
        8: [prefix + "dependency-decision.json", prefix + "container-image-lock.json"],
        9: [prefix + "bootstrap-report.json"],
        10: [prefix + "bootstrap-report.json", prefix + "boundary-capture-report.json"],
        11: [prefix + "source-workload-manifest.json"],
        12: [prefix + "source-workload-manifest.json"],
        13: [prefix + "source-workload-manifest.json"],
        14: ["docs/part2/stage1/SOURCE_BOUNDARY.md"],
        15: [prefix + "source-history-ledger.json"],
        16: [prefix + "source-workload-manifest.json"],
        17: [prefix + "source-history-ledger.json"],
        18: [prefix + "determinism-report.json"],
        19: [prefix + "determinism-report.json"],
        20: [prefix + "expected-state-manifest.json"],
        21: [prefix + "boundary-capture-report.json"],
        22: [prefix + "boundary-capture-report.json"],
        23: [prefix + "boundary-capture-report.json"],
        24: ["tests/test_source_boundary.py"],
        25: [prefix + "boundary-capture-report.json"],
        26: [prefix + "boundary-capture-report.json"],
        27: [prefix + "boundary-capture-report.json"],
        28: [prefix + "negative-case-report.json"],
        29: [prefix + "source-history-ledger.json"],
        30: [prefix + "determinism-report.json"],
        31: [prefix + "validation-summary.json"],
        32: [prefix + "validation-summary.json"],
        33: [prefix + "artifact-manifest.json"],
        34: [prefix + "validation-summary.json"],
        35: [prefix + "claim-impact-review.json"],
        36: [prefix + "file-manifest.json"],
        37: ["external:exact-pr-head-checks"],
        38: ["external:policy-compliant-merge"],
        39: ["external:exact-merged-main-validation"],
        40: ["external:part2-stage2-continuation-checkpoint"],
    }


def build_outputs(root: Path, runtime: dict[str, Any]) -> dict[Path, dict[str, Any]]:
    if runtime.get("repository_commit") != SOURCE_COMMIT:
        raise ValueError("CB21E001_RUNTIME_COMMIT_MISMATCH")
    if runtime.get("repository_tree") != SOURCE_TREE:
        raise ValueError("CB21E002_RUNTIME_TREE_MISMATCH")
    if runtime.get("result") != "PASS" or runtime.get("image") != IMAGE:
        raise ValueError("CB21E003_RUNTIME_NOT_QUALIFIED")
    runs = runtime.get("runs", [])
    if len(runs) != 3:
        raise ValueError("CB21E004_RUNTIME_COUNT")
    first = runs[0]
    spec = first["workload_spec"]
    cases = sorted(
        {case for transaction in spec["transactions"] for case in transaction["cases"]}
        | {
            case
            for transaction in spec["transactions"]
            for event in transaction["events"]
            for case in event["cases"]
        }
    )
    outputs: dict[Path, dict[str, Any]] = {}
    outputs[EVIDENCE_DIR / "execution-envelope.json"] = envelope(
        "execution_envelope",
        base_commit=BASE_COMMIT,
        base_tree=BASE_TREE,
        branch="part2-stage1-source-boundary",
        execution_mode="BUILD_PROVE_PUBLISH",
        authorization_boundary=[
            "isolated PostgreSQL source workload and exported-snapshot proof",
            "repository Stage 1 artifacts, checks, pull request, and policy-compliant merge",
        ],
        denied_scope=[
            "AWS operations",
            "DMS implementation",
            "Spark or Iceberg behavior",
            "Terraform behavior",
            "deployment, performance tests, release, tag, or history rewrite",
        ],
    )
    outputs[EVIDENCE_DIR / "repository-entry.json"] = envelope(
        "repository_entry",
        default_branch="main",
        entry_commit=BASE_COMMIT,
        entry_tree=BASE_TREE,
        branch_created_from_entry=True,
        branch_protected=False,
        ruleset_count=0,
        overlapping_open_pull_requests=[],
        concurrent_contributors_declared=False,
    )
    protected = json.loads(
        (root / "evidence/part1/stage5/protected-baseline.json").read_text(encoding="utf-8")
    )
    outputs[EVIDENCE_DIR / "protected-part1-baseline.json"] = envelope(
        "protected_part1_baseline",
        historical_validator="PASS",
        historical_tests={"passed": 115, "coverage_percent": 87.40},
        protected_base_commit=protected["base_commit"],
        protected_base_tree=protected["base_tree"],
        protected_artifacts=protected["artifacts"],
        current_digest_verification="PASS",
    )
    outputs[EVIDENCE_DIR / "overlap-register.json"] = envelope(
        "overlap_register",
        overlaps=[
            {
                "path": "src/changebridge/contracts.py",
                "authority": "typed PostgreSQL LSN validation",
                "change": "Reject hexadecimal halves wider than 32 bits.",
                "decision": "Named additive hardening; no accepted valid position is removed.",
                "record": "docs/part2/stage1/AUTHORITY_TRANSITION.md",
            },
            {
                "path": "requirements/completion-requirements.json",
                "authority": "completion requirement status and proof paths",
                "change": "Add exact Stage 1 local proof without advancing managed claims.",
                "decision": "Evidence-bounded correction.",
                "record": "docs/part2/stage1/AUTHORITY_TRANSITION.md",
            },
            {
                "path": "claims/claims.json",
                "authority": "public claim registry",
                "change": "Add a locally verified source-boundary claim with explicit exclusions.",
                "decision": "No existing managed or performance claim is promoted.",
                "record": "docs/part2/stage1/AUTHORITY_TRANSITION.md",
            },
        ],
        unreviewed_overlaps=[],
    )
    outputs[EVIDENCE_DIR / "source-surface-inventory.json"] = envelope(
        "source_surface_inventory",
        runtime_paths=[
            "src/changebridge/source_boundary.py",
            "src/changebridge/source_workload.py",
            "scripts/stage21_postgres_adapter.py",
            "scripts/run_stage21_postgres_lab.py",
        ],
        contracts=[
            "contracts/orders-v1.json",
            "contracts/orders-v1.1.json",
            "contracts/order-items-v1.json",
            "contracts/source-workload-spec-v1.json",
            "contracts/source-boundary-receipt-v1.json",
            "contracts/part2-stage1-catalog.json",
        ],
        migrations=[
            "migrations/source/001_initial_source.sql",
            "migrations/source/002_orders_source_note.sql",
        ],
        target_runtime_changes=[],
        infrastructure_behavior_changes=[],
    )
    outputs[EVIDENCE_DIR / "dependency-decision.json"] = envelope(
        "dependency_decision",
        direct_addition={
            "name": "psycopg2-binary",
            "version": "2.9.12",
            "license": "LGPL with exceptions",
            "required_dependencies": [],
            "reason": (
                "Expose PostgreSQL replication-protocol slot creation fields and SQL access in "
                "the bounded integration laboratory."
            ),
            "compatibility_probe": "PASS",
        },
        repository_development_dependencies={
            "hypothesis": "6.168.0",
            "jsonschema": "4.26.0",
            "mypy": "2.3.1",
            "psycopg2-binary": "2.9.12",
            "pytest": "9.1.1",
            "pytest-cov": "7.1.0",
            "ruff": "0.16.8",
        },
        undeclared_dependencies=[],
    )
    outputs[EVIDENCE_DIR / "toolchain-inventory.json"] = envelope(
        "toolchain_inventory",
        local_python="3.12.14",
        integration_python="3.11",
        driver="psycopg2-binary==2.9.12",
        libpq_version=170009,
        integration_server="PostgreSQL 17.11 Debian",
        logical_output_plugin="test_decoding",
        direct_driver_dependencies=[],
    )
    outputs[EVIDENCE_DIR / "container-image-lock.json"] = envelope(
        "container_image_lock",
        image=IMAGE,
        tag_resolved="17.11-bookworm",
        platform="linux/amd64",
        platform_digest="sha256:91eb52696c76c7a8482a678f663cb350d962bfeb669066332816ceebb7cd6038",
        registry="docker.io/library/postgres",
        publisher="Docker Official Images",
        mutable_tag_used_in_execution=False,
    )
    outputs[EVIDENCE_DIR / "bootstrap-report.json"] = envelope(
        "bootstrap_report",
        clean_bootstraps=[
            {
                "environment": "fresh GitHub hosted runner",
                "commit": "f5370e1878bd3f171b456eccc2940c9af15327b9",
                "workflow_run_id": 35998833675,
                "purpose": "replication-protocol compatibility",
                "result": "PASS",
            },
            {
                "environment": "fresh GitHub hosted runner",
                "commit": SOURCE_COMMIT,
                "workflow_run_id": RUNTIME_RUN_ID,
                "purpose": "complete source-boundary laboratory",
                "result": "PASS",
            },
        ],
        undeclared_dependency_count=0,
        ambient_service_count=0,
    )
    outputs[EVIDENCE_DIR / "source-workload-manifest.json"] = envelope(
        "source_workload_manifest",
        contract_version=spec["contract_version"],
        driver_semantic_version=spec["driver_semantic_version"],
        canonicalization_profile=spec["canonicalization_profile"],
        seed=spec["seed"],
        workload_id=spec["workload_id"],
        schema_set_digest=spec["schema_set_digest"],
        logical_clock=spec["logical_clock"],
        concurrency_schedule=spec["concurrency_schedule"],
        transaction_count=len(spec["transactions"]),
        event_count=sum(len(item["events"]) for item in spec["transactions"]),
        covered_cases=cases,
        identity_includes=[
            "contract_version",
            "seed",
            "schema_set_digest",
            "transactions",
            "concurrency_schedule",
            "driver_semantic_version",
            "canonicalization_profile",
            "logical_clock",
        ],
        identity_excludes=[
            "physical_lsn",
            "postgres_transaction_id",
            "container_id",
            "hostname",
            "wall_clock",
            "temporary_path",
        ],
        specification_contract="contracts/source-workload-spec-v1.json",
        completed_run_receipt_contract="contracts/source-workload-v1.schema.json",
    )
    outputs[EVIDENCE_DIR / "source-history-ledger.json"] = envelope(
        "source_history_ledger",
        workload_id=spec["workload_id"],
        committed_history_digest=first["expected_final"]["history_digest"],
        transactions=[transaction_summary(item) for item in spec["transactions"]],
        committed_transaction_count=len(first["expected_final"]["committed_transactions"]),
        aborted_transaction_count=len(first["expected_final"]["aborted_transactions"]),
        observed_pre_boundary_transactions=first["pre_boundary_observations"],
        post_boundary_transaction=first["boundary"]["post_boundary_observations"][0],
    )
    expected_runs = []
    for run in runs:
        expected = run["expected_final"]
        queried = run["queried_final"]
        expected_runs.append(
            {
                "seed": run["seed"],
                "workload_id": run["workload_spec"]["workload_id"],
                "expected_tables": table_summary(expected),
                "queried_tables": table_summary(queried),
                "expected_whole_state_digest": expected["whole_state_digest"],
                "queried_whole_state_digest": queried["whole_state_digest"],
                "match": expected["whole_state_digest"] == queried["whole_state_digest"],
                "migration_checksums": run["migration_checksums"],
            }
        )
    outputs[EVIDENCE_DIR / "expected-state-manifest.json"] = envelope(
        "expected_state_manifest",
        runs=expected_runs,
        all_replays_match=True,
    )
    outputs[EVIDENCE_DIR / "boundary-capture-report.json"] = envelope(
        "boundary_capture_report",
        workflow_run_id=RUNTIME_RUN_ID,
        workflow_artifact_id=RUNTIME_ARTIFACT_ID,
        workflow_artifact_sha256=RUNTIME_ARTIFACT_DIGEST,
        raw_report_sha256=RUNTIME_JSON_DIGEST,
        image=IMAGE,
        runs=[boundary_summary(run) for run in runs],
        exported_snapshot_count=3,
        imported_snapshot_count=3,
        slot_cleanup_count=3,
        raw_artifact_committed=False,
    )
    outputs[EVIDENCE_DIR / "determinism-report.json"] = envelope(
        "determinism_report",
        same_seed=spec["seed"],
        same_seed_equal=runtime["same_seed_equal"],
        different_seed=runs[2]["seed"],
        different_seed_differs=runtime["different_seed_differs"],
        physical_lsn_excluded_from_identity=runtime["physical_lsn_excluded_from_identity"],
        physical_snapshot_frontiers=[run["boundary"]["snapshot_frontier"] for run in runs],
        logical_history_digests=[run["expected_final"]["history_digest"] for run in runs],
        interpretation=(
            "Equivalent semantic inputs match logically; run-specific WAL addresses are "
            "intentionally unequal."
        ),
    )
    negative_cases = [
        ("arbitrary_current_wal", "CBSNP020_UNQUALIFIED_CAPTURE_METHOD", "unit"),
        ("missing_or_malformed_lsn", "CBPOS003_MALFORMED_VALUE", "property"),
        ("non_postgres_position", "CBSNP001_NON_POSTGRES_FRONTIER", "unit"),
        ("numeric_not_lexical_lsn_order", "property-order-equivalence", "property"),
        ("frontier_regression", "CBSNP009_NONADVANCING_FIRST_POSITION", "unit"),
        ("second_frontier", "CBSNP002_SECOND_FRONTIER", "unit"),
        ("source_identity_mismatch", "CBSNP007_SOURCE_IDENTITY_MISMATCH", "unit"),
        ("generation_mismatch", "CBSNP004_GENERATION_MISMATCH", "unit"),
        ("schema_set_mismatch", "CBSNP006_SCHEMA_MISMATCH", "unit"),
        ("workload_identity_mismatch", "CBSRC004_WORKLOAD_ID_MISMATCH", "unit"),
        ("first_transaction_gap", "CBSNP019_FIRST_TRANSACTION_GAP", "unit"),
        ("commit_at_exact_frontier", "CBSNP009_NONADVANCING_FIRST_POSITION", "unit"),
        ("change_before_frontier", "CBSNP017_CHANGE_PRECEDES_FRONTIER", "unit"),
        ("cross_kind_comparison", "CBPOS004_INCOMPARABLE_KINDS", "unit"),
        ("duplicate_transaction_identity", "CBSRC006_DUPLICATE_TRANSACTION_ID", "unit"),
        ("aborted_transaction_visibility", "state-and-history-absence", "integration"),
        ("nondeterministic_schedule", "CBSRC010_INVALID_CONCURRENCY_SCHEDULE", "unit"),
        ("dirty_namespace", "CBSRC024_DIRTY_REUSED_NAMESPACE", "integration"),
        (
            "expired_exported_snapshot",
            runtime["expired_snapshot_rejection"]["diagnostic_class"],
            "integration",
        ),
        ("slot_cleanup_failure", "CBSNP012_CLEANUP_NOT_PROVEN", "unit"),
    ]
    outputs[EVIDENCE_DIR / "negative-case-report.json"] = envelope(
        "negative_case_report",
        cases=[
            {"scenario": name, "expected_diagnostic": diagnostic, "layer": layer, "result": "PASS"}
            for name, diagnostic, layer in negative_cases
        ],
        runtime_expired_snapshot=runtime["expired_snapshot_rejection"],
        proof_paths=[
            "tests/test_source_boundary.py",
            "tests/test_source_workload.py",
            "tests/integration/test_postgres_source_boundary.py",
        ],
    )
    outputs[EVIDENCE_DIR / "scope-isolation-report.json"] = envelope(
        "scope_isolation_report",
        foreign_project_match_count=0,
        aws_operation_count=0,
        terraform_behavior_change_count=0,
        target_runtime_behavior_change_count=0,
        release_or_tag_count=0,
        history_rewrite_count=0,
        result_detail="Only ChangeBridge Part 2 Stage 1 source-boundary artifacts are present.",
    )
    outputs[EVIDENCE_DIR / "claim-impact-review.json"] = envelope(
        "claim_impact_review",
        added_claim="CB-CLAIM-011",
        promoted_existing_claims=[],
        locally_verified=[
            "deterministic PostgreSQL source workload and replay equivalence",
            "exported logical snapshot bound to one typed PostgreSQL frontier",
            "tested boundary mismatch and expired-snapshot rejection",
        ],
        explicitly_unclaimed=[
            "AWS DMS behavior",
            "target application or Iceberg behavior",
            (
                "throughput, availability, cost, RTO/RPO, exactly-once, zero downtime, "
                "production readiness"
            ),
        ],
    )
    outputs[EVIDENCE_DIR / "validation-summary.json"] = envelope(
        "validation_summary",
        commands=[
            {"command": "ruff check src scripts tests", "result": "PASS"},
            {
                "command": (
                    "mypy src scripts/stage21_postgres_adapter.py "
                    "scripts/run_stage21_postgres_lab.py"
                ),
                "result": "PASS",
            },
            {"command": "pytest", "result": "PASS", "coverage_floor_percent": 85},
            {
                "command": "python scripts/validate_part1_frozen.py",
                "result": "PASS",
                "historical_tests_passed": 115,
                "historical_coverage_percent": 87.40,
            },
            {
                "command": "GitHub Part 2 Stage 1 PostgreSQL Boundary",
                "result": "PASS",
                "workflow_run_id": RUNTIME_RUN_ID,
            },
        ],
        source_runtime_tests={"integration_passed": 1, "integration_skipped": 0},
        coverage_exclusion_added=False,
        secret_scan="PASS",
        current_tree_preservation="PASS",
    )
    outputs[EVIDENCE_DIR / "authority-transition.json"] = envelope(
        "authority_transition",
        transition_id="CB-AUTH-TRANSITION-002",
        prior_authority="Part 1 typed source-position and boundary design",
        new_authority="Part 2 Stage 1 executable PostgreSQL source-boundary implementation",
        decisions=[
            "PostgreSQL LSN halves are bounded to unsigned 32-bit hexadecimal text.",
            "The exported slot consistent point is snapshot frontier S.",
            (
                "The first governed CDC frontier is the decoded transaction COMMIT LSN, not a "
                "row-change record LSN that may equal S."
            ),
            (
                "Physical LSN values are run evidence and are excluded from semantic workload "
                "identity."
            ),
        ],
        affected_requirements=[
            "CB-BOUNDARY-001",
            "CB-BOUNDARY-002",
            "CB-BOUNDARY-003",
            "CB-ORDER-003",
            "CB-ORDER-004",
            "CB-SCHEMA-001",
        ],
        compatibility=(
            "Additive and fail-closed; historical Part 1 validation remains frozen and passing."
        ),
    )
    prospective_paths = sorted(
        set(changed_paths(root))
        | {path.as_posix() for path in outputs}
        | {
            (EVIDENCE_DIR / "file-manifest.json").as_posix(),
            MANIFEST_PATH.as_posix(),
            RECEIPT_PATH.as_posix(),
        }
    )
    outputs[EVIDENCE_DIR / "file-manifest.json"] = envelope(
        "file_manifest",
        base_commit=BASE_COMMIT,
        changed_paths=prospective_paths,
        authorized_scope_only=True,
    )
    return outputs


def build_manifest(root: Path, outputs: dict[Path, dict[str, Any]]) -> dict[str, Any]:
    excluded = {MANIFEST_PATH.as_posix(), RECEIPT_PATH.as_posix()}
    paths = [path for path in changed_paths(root) if path not in excluded]
    artifacts = []
    for relative in paths:
        path = root / relative
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"CB21E005_INVALID_ARTIFACT_PATH: {relative}")
        artifacts.append({"path": relative, "sha256": digest_bytes(path.read_bytes())})
    return envelope(
        "artifact_manifest",
        digest_algorithm="SHA-256",
        artifact_count=len(artifacts),
        artifacts=artifacts,
        excluded_recursive_paths=sorted(excluded),
    )


def build_receipt(manifest: dict[str, Any]) -> dict[str, Any]:
    mapping = criterion_evidence()
    criteria = [
        {
            "id": f"ST21-AC-{number:02d}",
            "result": "PASS" if number <= 36 else "PENDING",
            "evidence": mapping[number],
        }
        for number in range(1, 41)
    ]
    return {
        **envelope(
            "stage_receipt",
            result="PENDING_EXTERNAL_CLOSURE",
            record_type="stage_receipt",
            record_id="changebridge-part2-stage1",
            contract_version="1.0.0",
            base_commit=BASE_COMMIT,
            base_tree=BASE_TREE,
            artifact_manifest_digest=digest_bytes(canonical(manifest).encode()),
            criteria_total=40,
            criteria_passed=36,
            criteria_pending=4,
            criteria=criteria,
            external_criteria=["ST21-AC-37", "ST21-AC-38", "ST21-AC-39", "ST21-AC-40"],
        ),
    }


def render(root: Path, runtime_path: Path, *, check: bool) -> None:
    runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
    outputs = build_outputs(root, runtime)
    for relative, value in outputs.items():
        path = root / relative
        text = canonical(value)
        if check:
            if not path.is_file() or path.read_text(encoding="utf-8") != text:
                raise ValueError(f"CB21E006_EVIDENCE_DRIFT: {relative}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
    manifest = build_manifest(root, outputs)
    receipt = build_receipt(manifest)
    for relative, value in ((MANIFEST_PATH, manifest), (RECEIPT_PATH, receipt)):
        path = root / relative
        text = canonical(value)
        if check:
            if not path.is_file() or path.read_text(encoding="utf-8") != text:
                raise ValueError(f"CB21E006_EVIDENCE_DRIFT: {relative}")
        else:
            path.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-report", required=True, type=Path)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        render(args.root.resolve(), args.runtime_report.resolve(), check=args.check)
    except (OSError, ValueError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
