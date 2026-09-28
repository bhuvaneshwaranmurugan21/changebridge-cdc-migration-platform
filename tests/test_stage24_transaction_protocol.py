from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from changebridge.cdc_control import CDCControlError, CDCControlStore
from changebridge.cdc_ordering import CDCOrderingError, admit_interval, parse_lsn
from changebridge.transaction_assembler import (
    TransactionAssemblyError,
    assemble_transactions,
    build_apply_manifest,
)

ROOT = Path(__file__).resolve().parents[1]


def _fixture() -> tuple[list[dict[str, object]], dict[str, object]]:
    events = json.loads(
        (ROOT / "tests/fixtures/part2-stage4/canonical-events.json").read_text()
    )
    manifest = json.loads(
        (ROOT / "tests/fixtures/part2-stage4/apply-manifest.json").read_text()
    )
    return events, manifest


def _plans() -> list[dict[str, object]]:
    events, manifest = _fixture()
    return assemble_transactions(
        events,
        manifest,
        admitted_schema_digests={str(events[0]["source_schema_digest"])},
    )


@given(st.integers(min_value=0, max_value=2**64 - 1))
def test_lsn_round_trip_is_numeric(value: int) -> None:
    rendered = f"{value >> 32:X}/{value & 0xFFFFFFFF:X}"
    assert parse_lsn(rendered) == value


def test_lsn_order_is_not_lexicographic() -> None:
    assert "0/10" < "0/F"
    assert parse_lsn("0/10") > parse_lsn("0/F")


def test_boundary_is_open_closed() -> None:
    events, _ = _fixture()
    event = copy.deepcopy(events[0])
    event["source_position"]["value"] = "0/194FB20"
    with pytest.raises(CDCOrderingError, match="CB24O006_EVENT_OUTSIDE_INTERVAL"):
        admit_interval([event], "0/194FB20", "0/194FE20")


def test_manifest_and_transaction_are_deterministic() -> None:
    events, manifest = _fixture()
    rebuilt = build_apply_manifest(
        events,
        generation_id=str(manifest["generation_id"]),
        previous_frontier=str(manifest["previous_frontier"]),
        terminal_frontier=str(manifest["terminal_frontier"]),
        source_history_digest=str(manifest["source_history_digest"]),
        predecessor_manifest_digest=str(manifest["predecessor_manifest_digest"]),
    )
    assert rebuilt == manifest
    first = _plans()
    second = _plans()
    assert first == second
    assert first[0]["transaction_id"] == "tx-012-post-boundary"


def test_incomplete_transaction_fails_closed() -> None:
    events, manifest = _fixture()
    damaged = copy.deepcopy(manifest)
    damaged["transactions"][0]["expected_event_count"] = 2
    with pytest.raises(TransactionAssemblyError, match="CB24A008_INCOMPLETE_TRANSACTION"):
        assemble_transactions(
            events,
            damaged,
            admitted_schema_digests={str(events[0]["source_schema_digest"])},
        )


def test_schema_and_primary_key_evolution_are_stage5_authority() -> None:
    events, manifest = _fixture()
    with pytest.raises(TransactionAssemblyError, match="CB24A004_STAGE5_POLICY_REQUIRED"):
        assemble_transactions(events, manifest, admitted_schema_digests={"not-admitted"})
    damaged = copy.deepcopy(events)
    damaged[0]["after"]["order_id"] = "changed-key"
    with pytest.raises(TransactionAssemblyError, match="CB24A004_STAGE5_POLICY_REQUIRED"):
        assemble_transactions(
            damaged,
            manifest,
            admitted_schema_digests={str(events[0]["source_schema_digest"])},
        )


def test_checkpoint_requires_all_receipts_and_is_idempotent(tmp_path: Path) -> None:
    plan = _plans()[0]
    generation = str(plan["generation_id"])
    transaction = str(plan["transaction_id"])
    with CDCControlStore(tmp_path / "control.db") as control:
        control.initialize_checkpoint(generation, str(plan["previous_frontier"]))
        control.claim(plan)
        with pytest.raises(CDCControlError, match="CB24C005_RECEIPTS_INCOMPLETE"):
            control.finalize(plan, expected_revision=0)
        control.record_receipt(
            {
                "generation_id": generation,
                "transaction_id": transaction,
                "source_table": "orders",
                "transaction_digest": plan["transaction_digest"],
                "table_input_digest": "a" * 64,
                "commit_token": "b" * 64,
                "physical_snapshot_id": "123",
                "logical_digest": "c" * 64,
            }
        )
        finalized = control.finalize(plan, expected_revision=0)
        assert finalized["checkpoint"]["source_frontier"] == "0/194FE20"
        assert finalized["checkpoint"]["revision"] == 1
        replay = control.finalize(plan, expected_revision=0)
        assert replay["idempotent"] is True


def test_replay_identity_conflict_fails_closed(tmp_path: Path) -> None:
    plan = _plans()[0]
    with CDCControlStore(tmp_path / "control.db") as control:
        control.claim(plan)
        changed = {**plan, "transaction_digest": "f" * 64}
        with pytest.raises(CDCControlError, match="CB24C002_TRANSACTION_REPLAY_CONFLICT"):
            control.claim(changed)
