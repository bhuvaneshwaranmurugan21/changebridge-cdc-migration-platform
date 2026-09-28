from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from changebridge.reference_cdc import ReferenceCDCError, ReferenceCDCStore
from changebridge.snapshot_handoff import reconstruct_snapshot
from changebridge.transaction_assembler import assemble_transactions

ROOT = Path(__file__).resolve().parents[1]


def _plan() -> dict[str, object]:
    events = json.loads(
        (ROOT / "tests/fixtures/part2-stage4/canonical-events.json").read_text()
    )
    manifest = json.loads(
        (ROOT / "tests/fixtures/part2-stage4/apply-manifest.json").read_text()
    )
    return assemble_transactions(
        events,
        manifest,
        admitted_schema_digests={str(events[0]["source_schema_digest"])},
    )[0]


def test_reference_apply_and_replay(tmp_path: Path) -> None:
    _, truth, _ = reconstruct_snapshot(ROOT)
    plan = _plan()
    with ReferenceCDCStore(tmp_path / "reference.db") as reference:
        reference.initialize(truth["tables"])
        assert reference.apply(plan)["idempotent_replay"] is False
        assert reference.apply(plan)["idempotent_replay"] is True
        orders = reference.rows("orders")
        changed = next(row for row in orders if row["order_id"] == "order-004")
        assert changed["amount"] == 4750
        assert changed["campaign_id"] == "post-boundary"
        assert reference.table_result("orders")["row_count"] == 6
        assert reference.table_result("order_items")["row_count"] == 66


def test_reference_before_image_mismatch_detects_target_drift(tmp_path: Path) -> None:
    _, truth, _ = reconstruct_snapshot(ROOT)
    plan = copy.deepcopy(_plan())
    plan["events"][0]["before"]["amount"] = 999
    with ReferenceCDCStore(tmp_path / "reference.db") as reference:
        reference.initialize(truth["tables"])
        with pytest.raises(ReferenceCDCError, match="CB24R003_BEFORE_IMAGE_MISMATCH"):
            reference.apply(plan)
