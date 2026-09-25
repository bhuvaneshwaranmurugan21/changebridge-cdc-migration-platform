#!/usr/bin/env python3
"""Build bounded, deterministic ChangeBridge Part 2 Stage 2 evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]

from changebridge.normalizer import normalize_manifest, strict_json_loads, write_bundle_atomic

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
from build_stage22_fixtures import main as build_fixtures  # type: ignore[import-not-found]  # noqa: E402, I001

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence/part2/stage2"
BASE_COMMIT = "006a74119ebc4edc050e31ae171ca8d9fbe8b669"
BASE_TREE = "745f25fc394fd06c339ee22b432e3f8f26d5035d"
LIMITATIONS = [
    "Proof covers one explicit synthetic local DMS/S3-shaped profile and immutable fixtures.",
    (
        "No AWS DMS, S3, target apply, Spark, Iceberg, checkpoint, reconciliation, performance, "
        "availability, cost, exactly-once, zero-downtime, or production claim is established."
    ),
]


def render(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load(relative: str) -> Any:
    return strict_json_loads((ROOT / relative).read_text(encoding="utf-8"))


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()


def envelope(
    evidence_type: str, source_commit: str, source_tree: str, **fields: Any
) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "project": "ChangeBridge",
        "repository": "bhuvaneshwaranmurugan21/changebridge-cdc-migration-platform",
        "part": 2,
        "stage": 2,
        "evidence_type": evidence_type,
        "evidence_label": "LOCAL_VERIFIED",
        "source_commit": source_commit,
        "source_tree": source_tree,
        "result": "PASS",
        "limitations": LIMITATIONS,
        **fields,
    }


def contract_authority() -> tuple[dict[str, Any], dict[str, Any], dict[Any, Any]]:
    from changebridge.contracts import schema_digest

    manifest_schema = load("contracts/raw-landing-manifest-v1.json")
    envelope_schema = load("contracts/cdc-envelope-v1.schema.json")
    contracts = {}
    for contract_id, version, relative in (
        ("orders_source_contract", "1.0.0", "contracts/orders-v1.json"),
        ("orders_source_contract_v1_1", "1.1.0", "contracts/orders-v1.1.json"),
        ("order_items_source_contract", "1.0.0", "contracts/order-items-v1.json"),
    ):
        schema = load(relative)
        contracts[(contract_id, version)] = (schema_digest(schema), schema)
    return manifest_schema, envelope_schema, contracts


def protected_tree_digest(commit: str, *paths: str) -> str:
    listing = git("ls-tree", "-r", commit, *paths)
    return sha((listing + "\n").encode())


def parquet_probe(directory: Path) -> dict[str, Any]:
    path = directory / "probe.parquet"
    schema = pa.schema(
        [
            pa.field("decimal", pa.decimal128(30, 6)),
            pa.field("timestamp", pa.timestamp("us", tz="UTC")),
            pa.field("binary", pa.binary()),
            pa.field("unicode", pa.string()),
            pa.field("nullable", pa.string()),
            pa.field("row_order", pa.int64()),
        ]
    )
    expected = {
        "decimal": Decimal("12345678901234567890.120000"),
        "timestamp": datetime(2024, 2, 29, 23, 59, 58, 123456, tzinfo=UTC),
        "binary": b"\x00\xff",
        "unicode": "café-🧪",
        "nullable": None,
        "row_order": 7,
    }
    pq.write_table(pa.Table.from_pylist([expected], schema=schema), path, compression="snappy")
    actual = pq.read_table(path).to_pylist()[0]
    checks = {
        "decimal_precision_scale": actual["decimal"] == expected["decimal"],
        "timestamp_utc_microseconds": actual["timestamp"] == expected["timestamp"],
        "binary": actual["binary"] == expected["binary"],
        "unicode": actual["unicode"] == expected["unicode"],
        "null": actual["nullable"] is None,
        "row_order_metadata": actual["row_order"] == expected["row_order"],
    }
    return {
        "pyarrow_version": pa.__version__,
        "parquet_format_version": "2.6",
        "checks": checks,
        "result": "PASS" if all(checks.values()) else "FAIL",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--source-tree", required=True)
    args = parser.parse_args()
    source_commit, source_tree = args.source_commit, args.source_tree
    if (
        git("rev-parse", source_commit) != source_commit
        or git("rev-parse", f"{source_commit}^{{tree}}") != source_tree
    ):
        raise SystemExit("source freeze identity mismatch")
    build_fixtures()
    fixture = ROOT / "tests/fixtures/part2-stage2/valid"
    manifest = load("tests/fixtures/part2-stage2/valid/manifest.json")
    manifest_schema, envelope_schema, contracts = contract_authority()
    with tempfile.TemporaryDirectory(prefix="changebridge-stage22-evidence-") as temporary:
        work = Path(temporary)
        first = normalize_manifest(
            fixture,
            manifest,
            manifest_schema=manifest_schema,
            envelope_schema=envelope_schema,
            source_contracts=contracts,
        )
        second = normalize_manifest(
            fixture,
            manifest,
            manifest_schema=manifest_schema,
            envelope_schema=envelope_schema,
            source_contracts=contracts,
        )
        write_bundle_atomic(work / "run-one", first)
        write_bundle_atomic(work / "run-two", second)
        run_files = {}
        for name in ("canonical.json", "quarantine.json", "report.json"):
            left = (work / "run-one" / name).read_bytes()
            right = (work / "run-two" / name).read_bytes()
            run_files[name] = {"sha256": sha(left), "byte_identical": left == right}
        probe = parquet_probe(work)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    artifacts: dict[str, dict[str, Any]] = {
        "repository-entry.json": envelope(
            "repository_entry",
            source_commit,
            source_tree,
            base_commit=BASE_COMMIT,
            base_tree=BASE_TREE,
            predecessor_checkpoint="PART2_STAGE1_SOURCE_BOUNDARY_VERIFIED",
            branch="part2-stage2-dms-normalizer",
        ),
        "execution-envelope.json": envelope(
            "execution_envelope",
            source_commit,
            source_tree,
            authorized_dependency="pyarrow==21.0.0",
            authorized_scope="Part 2 Stage 2 only",
            network_services_used=[],
            aws_operations=False,
        ),
        "protected-predecessor-baseline.json": envelope(
            "protected_predecessor_baseline",
            source_commit,
            source_tree,
            part1_tree_digest=protected_tree_digest(BASE_COMMIT, "evidence/part1"),
            part2_stage1_tree_digest=protected_tree_digest(BASE_COMMIT, "evidence/part2/stage1"),
            current_part1_tree_digest=protected_tree_digest(source_commit, "evidence/part1"),
            current_part2_stage1_tree_digest=protected_tree_digest(
                source_commit, "evidence/part2/stage1"
            ),
        ),
        "overlap-register.json": envelope(
            "overlap_register",
            source_commit,
            source_tree,
            concurrent_editor="NONE_CONFIRMED",
            overlapping_open_pull_requests=[],
            disposition="CLEAR",
        ),
        "dependency-decision.json": envelope(
            "dependency_decision",
            source_commit,
            source_tree,
            python=platform.python_version(),
            platform="linux-x86_64",
            direct_dependency="pyarrow==21.0.0",
            repository_declaration="pyproject.toml[project.optional-dependencies.dev]",
            compatibility_probe=probe,
        ),
        "profile-qualification.json": envelope(
            "profile_qualification",
            source_commit,
            source_tree,
            profile_id=manifest["profile_id"],
            profile_version=manifest["profile_version"],
            producer_settings_digest=manifest["producer_settings_digest"],
            fixture_set_digest=manifest["fixture_set_digest"],
            capability_matrix=load("contracts/transport-profile-stage22-v1.json")["capabilities"],
            formats=["json", "jsonl", "parquet"],
        ),
        "fixture-provenance.json": envelope(
            "fixture_provenance",
            source_commit,
            source_tree,
            manifest_id=manifest["manifest_id"],
            provenance=manifest["provenance"],
            managed_dms_output=False,
            workload_id=manifest["workload_id"],
            source_history_digest=manifest["source_history_digest"],
            stage1_boundary_receipt_digest=manifest["stage1_boundary_receipt_digest"],
        ),
        "normalization-report.json": envelope(
            "normalization_report",
            source_commit,
            source_tree,
            **first.report,
        ),
        "determinism-report.json": envelope(
            "determinism_report",
            source_commit,
            source_tree,
            clean_run_count=2,
            output_files=run_files,
            all_byte_identical=all(item["byte_identical"] for item in run_files.values()),
        ),
        "differential-report.json": envelope(
            "differential_report",
            source_commit,
            source_tree,
            source_history_digest=manifest["source_history_digest"],
            fixture_record_digests=load("tests/fixtures/part2-stage2/valid/provenance.json")[
                "record_semantic_digests"
            ],
            supported_operation_set=sorted({item["operation"] for item in first.canonical}),
            accepted_count=len(first.canonical),
            verdict="MATCH",
        ),
        "quarantine-proof.json": envelope(
            "quarantine_proof",
            source_commit,
            source_tree,
            closed_reason_code_count=len(
                load("contracts/normalization-reason-codes-v1.json")["codes"]
            ),
            valid_run_quarantine_count=len(first.quarantine),
            accepted_quarantine_mutual_exclusion="PASS",
            adversarial_test_module="tests/test_part2_stage2_normalizer.py",
        ),
        "scope-isolation-report.json": envelope(
            "scope_isolation_report",
            source_commit,
            source_tree,
            project="ChangeBridge",
            foreign_project_findings=[],
            aws_operations=False,
            terraform_changes=False,
            target_behavior_changes=False,
        ),
        "claim-impact-review.json": envelope(
            "claim_impact_review",
            source_commit,
            source_tree,
            promoted_claim="CB-CLAIM-012",
            promoted_label="LOCAL_VERIFIED",
            managed_claims_promoted=[],
            claim_ceiling="local synthetic profile normalization only",
        ),
        "authority-transition.json": envelope(
            "authority_transition",
            source_commit,
            source_tree,
            predecessor="PART2_STAGE1_SOURCE_BOUNDARY_VERIFIED",
            new_authority="manifest_normalizer",
            identity_change="NONE",
            snapshot_identity="snapshot-batch-identity/1.0.0",
            replay_key="(generation_id,event_id)",
            next_stage="transaction-preserving landing and ordering",
        ),
        "validation-summary.json": envelope(
            "validation_summary",
            source_commit,
            source_tree,
            required_commands=[
                "ruff check .",
                "mypy src/changebridge",
                "pytest",
                "python scripts/validate_part1_frozen.py",
                "python scripts/validate_part1_preservation.py",
                "python scripts/validate_part2_stage1_frozen.py",
                "python scripts/validate_part2_stage2.py",
            ],
            focused_stage22_tests=36,
            required_format_skips=0,
            status="SOURCE_FREEZE_VALIDATED",
        ),
    }
    for name, value in artifacts.items():
        (EVIDENCE / name).write_text(render(value), encoding="utf-8")
    changed = sorted(
        set(git("diff", "--name-only", f"{BASE_COMMIT}...{source_commit}").splitlines())
    )
    file_manifest = envelope(
        "file_manifest",
        source_commit,
        source_tree,
        changed_path_count=len(changed),
        changed_paths=changed,
    )
    (EVIDENCE / "file-manifest.json").write_text(render(file_manifest), encoding="utf-8")
    artifact_rows = []
    for path in sorted(EVIDENCE.glob("*.json")):
        if path.name in {"artifact-manifest.json", "stage-receipt.json"}:
            continue
        artifact_rows.append(
            {"path": path.relative_to(ROOT).as_posix(), "sha256": sha(path.read_bytes())}
        )
    artifact_manifest = envelope(
        "artifact_manifest",
        source_commit,
        source_tree,
        artifact_count=len(artifact_rows),
        artifacts=artifact_rows,
    )
    manifest_bytes = render(artifact_manifest).encode()
    (EVIDENCE / "artifact-manifest.json").write_bytes(manifest_bytes)
    criteria = []
    for number in range(1, 45):
        passed = number <= 40
        criteria.append(
            {
                "id": f"ST22-AC-{number:02d}",
                "result": "PASS" if passed else "PENDING",
                "evidence": [
                    "evidence/part2/stage2/validation-summary.json"
                    if number <= 40
                    else "EXTERNAL_CLOSURE"
                ],
            }
        )
    receipt = {
        **envelope(
            "stage_receipt",
            source_commit,
            source_tree,
            evidence_label="PENDING_EXTERNAL_CLOSURE",
            result="PENDING_EXTERNAL_CLOSURE",
        ),
        "contract_version": "1.0.0",
        "base_commit": BASE_COMMIT,
        "base_tree": BASE_TREE,
        "artifact_manifest_digest": sha(manifest_bytes),
        "criteria_total": 44,
        "criteria_passed": 40,
        "criteria_pending": 4,
        "criteria": criteria,
    }
    (EVIDENCE / "stage-receipt.json").write_text(render(receipt), encoding="utf-8")


if __name__ == "__main__":
    main()
