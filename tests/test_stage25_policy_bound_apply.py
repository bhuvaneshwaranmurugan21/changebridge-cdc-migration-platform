from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from changebridge.schema_admission import SchemaAdmissionError, assemble_policy_bound_transactions
from changebridge.schema_control import SchemaControlError, SchemaControlStore
from changebridge.schema_policy import (
    POLICY_DIGEST,
    SchemaPolicy,
    SchemaRegistry,
    registered_schema,
)

ROOT = Path(__file__).resolve().parents[1]
GENERATION = "generation-34edddda5aee96dc7236aaf3"


def load(relative: str) -> dict[str, object]:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def authority() -> tuple[object, object]:
    registry = SchemaRegistry()
    old = registered_schema(
        contract_id="orders_source_contract",
        version="1.0.0",
        source_table="orders",
        schema=load("contracts/orders-v1.json"),
        primary_key=("order_id",),
    )
    new = registered_schema(
        contract_id="orders_source_contract",
        version="1.1.0",
        source_table="orders",
        schema=load("contracts/orders-v1.1.json"),
        primary_key=("order_id",),
    )
    registry.add(old)
    registry.add(new)
    return SchemaPolicy(registry).decide(
        generation_id=GENERATION,
        source_table="orders",
        previous=old.identity,
        candidate=new.identity,
    ), new.identity


def accepted_input(candidate_digest: str) -> tuple[list[dict[str, object]], dict[str, object]]:
    events = load("tests/fixtures/part2-stage4/canonical-events.json")
    assert isinstance(events, list)
    rows = copy.deepcopy(events)
    for event in rows:
        event["source_schema_digest"] = candidate_digest
    manifest = load("tests/fixtures/part2-stage4/apply-manifest.json")
    return rows, manifest


def record_receipt(control: SchemaControlStore, decision: object) -> None:
    control.record_decision(decision)  # type: ignore[arg-type]
    control.record_apply_receipt(
        {
            "receipt_id": "schema-receipt-test",
            "apply_token": "a" * 64,
            "generation_id": GENERATION,
            "source_table": "orders",
            "decision_id": decision.decision_id,  # type: ignore[attr-defined]
            "candidate_digest": decision.candidate.digest,  # type: ignore[attr-defined]
            "policy_digest": POLICY_DIGEST,
            "iceberg_schema_id": 1,
            "metadata_location": "file:///bounded/metadata/v2.metadata.json",
            "recovered": 0,
        }
    )


def test_exact_schema_receipt_is_required_and_bound(tmp_path: Path) -> None:
    decision, candidate = authority()
    events, manifest = accepted_input(candidate.digest)  # type: ignore[attr-defined]
    with SchemaControlStore(tmp_path / "control.db") as control:
        control.record_decision(decision)  # type: ignore[arg-type]
        with pytest.raises(SchemaControlError, match="CB25C006_ADMISSION_REQUIRED"):
            assemble_policy_bound_transactions(
                events, manifest, control=control, decisions={"orders": decision}
            )
        record_receipt(control, decision)
        plans = assemble_policy_bound_transactions(
            events, manifest, control=control, decisions={"orders": decision}
        )
    assert len(plans) == 1
    assert plans[0]["schema_admissions"]["orders"]["receipt_id"] == "schema-receipt-test"
    assert len(plans[0]["schema_admission_digest"]) == 64


def test_schema_digest_and_primary_key_value_drift_fail_closed(tmp_path: Path) -> None:
    decision, candidate = authority()
    events, manifest = accepted_input(candidate.digest)  # type: ignore[attr-defined]
    with SchemaControlStore(tmp_path / "control.db") as control:
        record_receipt(control, decision)
        wrong_digest = copy.deepcopy(events)
        wrong_digest[0]["source_schema_digest"] = "0" * 64
        with pytest.raises(SchemaAdmissionError, match="CB25A002_SCHEMA_DECISION_MISMATCH"):
            assemble_policy_bound_transactions(
                wrong_digest, manifest, control=control, decisions={"orders": decision}
            )
        key_change = copy.deepcopy(events)
        update = key_change[0]
        assert update["operation"] == "update"
        update["after"]["order_id"] = "order-rekeyed"  # type: ignore[index]
        with pytest.raises(Exception, match="CB25S031_PRIMARY_KEY_VALUE_CHANGED"):
            assemble_policy_bound_transactions(
                key_change, manifest, control=control, decisions={"orders": decision}
            )
