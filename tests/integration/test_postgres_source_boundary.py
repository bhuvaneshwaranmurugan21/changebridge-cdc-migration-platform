from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from scripts.run_stage21_postgres_lab import ROOT, build_report


@pytest.mark.postgres_integration
def test_real_postgres_exported_snapshot_boundary() -> None:
    if os.environ.get("CB_RUN_POSTGRES_INTEGRATION") != "1":
        pytest.skip("requires the digest-pinned Stage 2.1 PostgreSQL service")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    tree = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT, text=True).strip()
    report = build_report(commit, tree)
    assert report["result"] == "PASS"
    assert all(report["same_seed_equal"].values())
    assert report["different_seed_differs"] is True
    assert all(run["boundary"]["cleanup"]["slot_dropped"] for run in report["runs"])
    output = Path(os.environ["STAGE21_LAB_OUTPUT"])
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
