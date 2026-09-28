from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts.run_stage25_schema_lab import recovery_run

pytestmark = pytest.mark.iceberg_integration


def test_process_loss_after_schema_commit_recovers_exact_receipt(tmp_path: Path) -> None:
    jar_value = os.environ.get("CB_ICEBERG_JAR")
    if not jar_value or not Path(jar_value).is_file():
        pytest.fail("CB_ICEBERG_JAR is required; Stage 5 recovery proof cannot skip")
    result = recovery_run(tmp_path / "recovery", Path(jar_value))
    assert result == {
        "crash_exit_code": 88,
        "receipts_after_crash": 0,
        "recovered_receipt": True,
        "metadata_changed_once": True,
        "snapshot_count_unchanged": True,
        "schema_id": 1,
        "frontier_unchanged": "0/194FE20",
    }
