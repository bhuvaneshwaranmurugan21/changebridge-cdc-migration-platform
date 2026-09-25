from __future__ import annotations

from pathlib import Path

import pytest

from changebridge.snapshot_handoff import (
    EXPECTED_COUNTS,
    EXPECTED_FRONTIER,
    EXPECTED_WHOLE_STATE_DIGEST,
    build_full_handoff,
    normalize_full_handoff,
    reconstruct_snapshot,
)
from changebridge.snapshot_loader import SnapshotLoadError, validate_snapshot_events

ROOT = Path(__file__).resolve().parents[1]


def test_complete_snapshot_reconstruction_matches_accepted_stage1() -> None:
    _, truth, run = reconstruct_snapshot(ROOT)
    assert {name: table["row_count"] for name, table in truth["tables"].items()} == (
        EXPECTED_COUNTS
    )
    assert truth["whole_state_digest"] == EXPECTED_WHOLE_STATE_DIGEST
    assert run["snapshot_frontier"] == {"kind": "postgres_lsn", "value": EXPECTED_FRONTIER}


def test_full_handoff_uses_unchanged_normalizer_and_separates_cdc(tmp_path: Path) -> None:
    handoff = tmp_path / "handoff"
    manifest = build_full_handoff(ROOT, handoff)
    bundle = normalize_full_handoff(ROOT, handoff)
    snapshot = [event for event in bundle.canonical if event["operation"] == "snapshot"]
    cdc = [event for event in bundle.canonical if event["operation"] != "snapshot"]
    assert bundle.report["result"] == "PASS"
    assert bundle.report["quarantined_count"] == 0
    assert len(snapshot) == 72
    assert len(cdc) == 1
    assert {
        table: sum(row["source_table"] == table for row in snapshot) for table in EXPECTED_COUNTS
    } == EXPECTED_COUNTS
    assert all(row["source_position"]["value"] == EXPECTED_FRONTIER for row in snapshot)
    assert cdc[0]["source_position"]["value"] != EXPECTED_FRONTIER
    assert manifest["provenance"] == "SYNTHETIC_CONTRACT_FIXTURE"


def test_loader_rejects_post_s_cdc_and_duplicate_keys(tmp_path: Path) -> None:
    handoff = tmp_path / "handoff"
    build_full_handoff(ROOT, handoff)
    canonical = list(normalize_full_handoff(ROOT, handoff).canonical)
    snapshot = [row for row in canonical if row["operation"] == "snapshot"]
    cdc = next(row for row in canonical if row["operation"] != "snapshot")
    generation_id = snapshot[0]["generation_id"]
    with pytest.raises(SnapshotLoadError, match="CBL002_NON_SNAPSHOT_RECORD"):
        validate_snapshot_events([cdc], generation_id=generation_id, table="orders")
    duplicate = [snapshot[0], snapshot[0]]
    with pytest.raises(SnapshotLoadError, match="CBL008_DUPLICATE_KEY"):
        validate_snapshot_events(duplicate, generation_id=generation_id, table="orders")


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("generation_id", "generation-wrong", "CBL003_GENERATION_MISMATCH"),
        ("source_table", "order_items", "CBL004_TABLE_MISMATCH"),
        ("source_contract_version", "9.9.9", "CBL018_LINEAGE_MISMATCH"),
        ("source_schema_digest", "0" * 64, "CBL018_LINEAGE_MISMATCH"),
        ("run_id", "wrong-run", "CBL019_RUN_MISMATCH"),
    ],
)
def test_loader_rejects_wrong_lineage(tmp_path: Path, field: str, value: str, code: str) -> None:
    handoff = tmp_path / "handoff"
    build_full_handoff(ROOT, handoff)
    event = next(
        row
        for row in normalize_full_handoff(ROOT, handoff).canonical
        if row["operation"] == "snapshot" and row["source_table"] == "orders"
    )
    altered = {**event, field: value}
    with pytest.raises(SnapshotLoadError, match=code):
        validate_snapshot_events(
            [altered],
            generation_id=event["generation_id"],
            table="orders",
            expected_run_id=event["run_id"],
        )
