from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts.run_stage24_iceberg_lab import clean_run, recovery_run

pytestmark = pytest.mark.iceberg_integration


def _jar() -> Path:
    value = os.environ.get("CB_ICEBERG_JAR")
    if not value:
        pytest.fail("CB_ICEBERG_JAR is required; the real Iceberg lane cannot skip")
    path = Path(value)
    if not path.is_file():
        pytest.fail(f"CB_ICEBERG_JAR does not exist: {path}")
    return path


def test_real_transactional_apply_matches_independent_reference(tmp_path: Path) -> None:
    result = clean_run(tmp_path / "clean", _jar())
    assert result["differential_equal"] is True
    assert result["checkpoint"]["source_frontier"] == "0/194FE20"
    assert result["idempotent_replay"] is True
    assert result["generation_state"] == "CDC_APPLYING"
    assert result["published"] is False


def test_process_exit_recovers_commit_without_rewrite(tmp_path: Path) -> None:
    result = recovery_run(tmp_path / "recovery", _jar())
    assert result["crash_exit_code"] == 87
    assert result["checkpoint_after_crash"]["source_frontier"] == "0/194FB20"
    assert result["receipts_after_crash"] == 0
    assert result["recovered_receipt"] is True
    assert result["recovered_without_rewrite"] is True
    assert result["final_checkpoint"]["source_frontier"] == "0/194FE20"
