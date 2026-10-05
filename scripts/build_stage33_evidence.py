#!/usr/bin/env python3
"""Refresh Stage 3 artifact hashes without overwriting observations or run receipts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evidence/part3/stage3"


def write(name: str, payload: dict[str, Any]) -> None:
    (OUT / name).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_manifest() -> None:
    """Refresh current artifact hashes without rewriting observation or run evidence."""
    roots = [
        "requirements/part3-stage3-contract.json",
        "requirements/part3-stage3-acceptance.json",
        "deployment/stage3",
        "docs/part3/stage3",
        "scripts/collect_stage33_readonly.sh",
        "scripts/collect_stage33_access_diagnostic.sh",
        "scripts/build_stage33_evidence.py",
        "scripts/install_stage33_role_observer.sh",
        "scripts/validate_part3_stage3.py",
        "scripts/validate_stage33_access_evidence.py",
        "tests/test_part3_stage3_validator.py",
        "tests/test_stage33_oidc_qualification.py",
        "tests/test_stage33_role_observer_installation.py",
        "tests/test_stage33_access_diagnostic.py",
        "tests/test_stage33_access_evidence.py",
        "scripts/prepare_stage33_bootstrap.py",
        "tests/test_stage33_bootstrap_package.py",
        "scripts/stage33_bootstrap_journal.py",
        "scripts/qualify_stage33_bootstrap.py",
        "tests/test_stage33_bootstrap_journal.py",
        "tests/test_stage33_bootstrap_qualification.py",
        "scripts/prepare_stage33_cleanup.py",
        "tests/test_stage33_cleanup_plan.py",
        "scripts/stage33_mutation_journal.py",
        "tests/test_stage33_mutation_journal.py",
        "scripts/verify_stage33_role_controls.py",
        "tests/test_stage33_role_controls.py",
        "scripts/verify_stage33_key_controls.py",
        "tests/test_stage33_key_controls.py",
        "scripts/verify_stage33_storage_controls.py",
        "tests/test_stage33_storage_controls.py",
        "scripts/verify_stage33_lock_controls.py",
        "tests/test_stage33_lock_controls.py",
        "scripts/reconcile_stage33_key_attempt.py",
        "tests/test_stage33_key_attempt.py",
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


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest-only", action="store_true")
    args = parser.parse_args()
    build_manifest()
