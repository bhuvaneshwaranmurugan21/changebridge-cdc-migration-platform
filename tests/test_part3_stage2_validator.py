from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

from scripts.package_stage32_runtime import build
from scripts.validate_part3_stage2 import validate


def test_stage32_authority_passes() -> None:
    assert validate()["result"] == "PASS"


def test_runtime_bundle_is_reproducible() -> None:
    with tempfile.TemporaryDirectory() as directory:
        first = Path(directory) / "first.zip"
        second = Path(directory) / "second.zip"
        assert build(first)["sha256"] == build(second)["sha256"]
        assert (
            hashlib.sha256(first.read_bytes()).digest()
            == hashlib.sha256(second.read_bytes()).digest()
        )


def test_orchestration_rejects_unproven_generation() -> None:
    root = Path(__file__).resolve().parents[1]
    definition = json.loads((root / "deployment/orchestration/migration.asl.json").read_text())
    gate = definition["States"]["ProofGate"]
    assert gate["Default"] == "Rejected"
    assert gate["Choices"] == [
        {"Variable": "$.proof.status", "StringEquals": "PROVEN", "Next": "Publish"}
    ]


def test_no_protected_evidence_change() -> None:
    root = Path(__file__).resolve().parents[1]
    changed = subprocess.run(
        [
            "git",
            "diff",
            "--name-only",
            "963db655922b0209a4ce9790c5224b3ca0e642ef",
            "--",
            "evidence/part1",
            "evidence/part2",
            "evidence/part3/stage1",
        ],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert changed == ""
