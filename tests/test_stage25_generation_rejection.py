from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from changebridge.schema_control import SchemaControlError, SchemaControlStore
from changebridge.schema_policy import SchemaPolicy, SchemaRegistry, registered_schema

ROOT = Path(__file__).resolve().parents[1]
GENERATION = "generation-34edddda5aee96dc7236aaf3"


def incompatible_decision() -> object:
    original = json.loads((ROOT / "contracts/orders-v1.json").read_text(encoding="utf-8"))
    changed = copy.deepcopy(original)
    changed["properties"].pop("amount")
    registry = SchemaRegistry()
    old = registered_schema(
        contract_id="orders_source_contract",
        version="1.0.0",
        source_table="orders",
        schema=original,
        primary_key=("order_id",),
    )
    new = registered_schema(
        contract_id="orders_source_contract",
        version="2.0.0",
        source_table="orders",
        schema=changed,
        primary_key=("order_id",),
    )
    registry.add(old)
    registry.add(new)
    return SchemaPolicy(registry).decide(
        generation_id=GENERATION,
        source_table="orders",
        previous=old.identity,
        candidate=new.identity,
    )


def test_stage5_generation_rejection_is_guarded_and_idempotent(tmp_path: Path) -> None:
    decision = incompatible_decision()
    with SchemaControlStore(tmp_path / "control.db") as control:
        control.record_decision(decision)  # type: ignore[arg-type]
        quarantine = control.open_quarantine(
            decision,  # type: ignore[arg-type]
            frontier="0/194FE20",
            target_metadata_location="file:///bounded/metadata/v1.metadata.json",
        )
        first = control.reject_generation(
            decision,  # type: ignore[arg-type]
            quarantine_id=quarantine["quarantine_id"],
            expected_revision=2,
        )
        replay = control.reject_generation(
            decision,  # type: ignore[arg-type]
            quarantine_id=quarantine["quarantine_id"],
            expected_revision=2,
        )
        assert first == replay
        assert (first["predecessor_state"], first["state"], first["revision"]) == (
            "CDC_APPLYING",
            "REJECTED",
            3,
        )
        with pytest.raises(SchemaControlError, match="CB25C009_GENERATION_REJECTED"):
            control.require_admission(
                generation_id=GENERATION,
                source_table="orders",
                candidate_digest=decision.candidate.digest,  # type: ignore[attr-defined]
                policy_digest=decision.policy_digest,  # type: ignore[attr-defined]
            )
