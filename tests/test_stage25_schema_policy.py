from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st
from jsonschema import Draft202012Validator

from changebridge.schema_control import SchemaControlError, SchemaControlStore
from changebridge.schema_policy import (
    POLICY_DIGEST,
    ContractIdentity,
    SchemaPolicy,
    SchemaPolicyError,
    SchemaRegistry,
    assert_key_values_unchanged,
    registered_schema,
)

ROOT = Path(__file__).resolve().parents[1]
GENERATION = "generation-34edddda5aee96dc7236aaf3"


def load(name: str) -> dict[str, object]:
    return json.loads((ROOT / name).read_text())


def authority() -> tuple[SchemaPolicy, ContractIdentity, ContractIdentity]:
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
    return SchemaPolicy(registry), old.identity, new.identity


def test_accepted_nullable_non_key_addition_is_deterministic() -> None:
    policy, old, new = authority()
    first = policy.decide(
        generation_id=GENERATION, source_table="orders", previous=old, candidate=new
    )
    second = policy.decide(
        generation_id=GENERATION, source_table="orders", previous=old, candidate=new
    )
    assert first == second
    assert first.verdict == "COMPATIBLE"
    assert [(field.name, field.nullable) for field in first.added_fields] == [("source_note", True)]
    assert first.previous_primary_key == first.candidate_primary_key


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (lambda value: value["properties"].pop("amount"), "CB25S021_FIELD_REMOVED"),
        (
            lambda value: value["properties"]["amount"].update(type="string"),
            "CB25S022_TYPE_CHANGED",
        ),
        (
            lambda value: value["properties"]["campaign_id"].update(type="string"),
            "CB25S023_NULLABILITY_NARROWED",
        ),
        (
            lambda value: value["properties"].update(priority={"type": "string"}),
            "CB25S024_REQUIRED_FIELD_ADDED",
        ),
    ],
)
def test_incompatible_fields_fail_closed(mutation: object, code: str) -> None:
    schema = copy.deepcopy(load("contracts/orders-v1.json"))
    assert callable(mutation)
    mutation(schema)
    if code == "CB25S024_REQUIRED_FIELD_ADDED":
        schema["required"].append("priority")
    registry = SchemaRegistry()
    old = registered_schema(
        contract_id="orders",
        version="1.0.0",
        source_table="orders",
        schema=load("contracts/orders-v1.json"),
        primary_key=("order_id",),
    )
    candidate = registered_schema(
        contract_id="orders",
        version="2.0.0",
        source_table="orders",
        schema=schema,
        primary_key=("order_id",),
    )
    registry.add(old)
    registry.add(candidate)
    decision = SchemaPolicy(registry).decide(
        generation_id=GENERATION,
        source_table="orders",
        previous=old.identity,
        candidate=candidate.identity,
    )
    assert decision.verdict == "INCOMPATIBLE"
    assert code in decision.reason_codes


def test_primary_key_definition_and_value_changes_fail_closed() -> None:
    registry = SchemaRegistry()
    schema = load("contracts/orders-v1.1.json")
    old = registered_schema(
        contract_id="orders",
        version="1.1.0",
        source_table="orders",
        schema=schema,
        primary_key=("order_id",),
    )
    changed = registered_schema(
        contract_id="orders",
        version="2.0.0",
        source_table="orders",
        schema=schema,
        primary_key=("customer_id",),
    )
    registry.add(old)
    registry.add(changed)
    decision = SchemaPolicy(registry).decide(
        generation_id=GENERATION,
        source_table="orders",
        previous=old.identity,
        candidate=changed.identity,
    )
    assert decision.verdict == "INCOMPATIBLE"
    assert "CB25S020_PRIMARY_KEY_CHANGED" in decision.reason_codes
    compatible = SchemaPolicy(registry).decide(
        generation_id=GENERATION,
        source_table="orders",
        previous=old.identity,
        candidate=old.identity,
    )
    event = {
        "event_id": "event",
        "operation": "update",
        "before": {"order_id": "a"},
        "after": {"order_id": "b"},
    }
    with pytest.raises(SchemaPolicyError, match="CB25S031_PRIMARY_KEY_VALUE_CHANGED"):
        assert_key_values_unchanged(event, compatible)


def test_unknown_and_policy_mismatch_quarantine() -> None:
    policy, old, new = authority()
    unknown = policy.decide(
        generation_id=GENERATION,
        source_table="orders",
        previous=old,
        candidate=ContractIdentity(new.contract_id, new.version, "0" * 64),
    )
    mismatch = policy.decide(
        generation_id=GENERATION,
        source_table="orders",
        previous=old,
        candidate=new,
        policy_digest="f" * 64,
    )
    assert (unknown.verdict, unknown.required_action) == ("UNKNOWN", "QUARANTINE")
    assert (mismatch.verdict, mismatch.required_action) == ("UNKNOWN", "QUARANTINE")


def test_control_store_is_idempotent_and_quarantine_blocks_admission(tmp_path: Path) -> None:
    policy, old, new = authority()
    decision = policy.decide(
        generation_id=GENERATION, source_table="orders", previous=old, candidate=new
    )
    unknown = policy.decide(
        generation_id=GENERATION,
        source_table="orders",
        previous=old,
        candidate=ContractIdentity(new.contract_id, new.version, "0" * 64),
    )
    with SchemaControlStore(tmp_path / "control.db") as control:
        assert control.record_decision(decision) == control.record_decision(decision)
        control.record_decision(unknown)
        control.open_quarantine(unknown, frontier="0/194FE20", target_metadata_location="meta-v1")
        with pytest.raises(SchemaControlError, match="CB25C005_GENERATION_QUARANTINED"):
            control.require_admission(
                generation_id=GENERATION,
                source_table="orders",
                candidate_digest=new.digest,
                policy_digest=POLICY_DIGEST,
            )


@given(st.permutations(["order_id", "customer_id", "amount", "campaign_id", "source_note"]))
def test_property_order_does_not_change_identity(order: list[str]) -> None:
    schema = load("contracts/orders-v1.1.json")
    schema["properties"] = {name: schema["properties"][name] for name in order}
    definition = registered_schema(
        contract_id="orders_source_contract",
        version="1.1.0",
        source_table="orders",
        schema=schema,
        primary_key=("order_id",),
    )
    _, _, accepted = authority()
    assert definition.identity.digest == accepted.digest


def test_stage5_contract_catalog_is_complete_and_schemas_are_valid() -> None:
    catalog = load("contracts/part2-stage5-catalog.json")
    records = catalog["records"]
    assert [record["id"] for record in records] == [
        "schema_policy",
        "primary_key_definition",
        "schema_decision",
        "schema_quarantine",
        "schema_apply_receipt",
        "reason_codes",
    ]
    for record in records:
        path = ROOT / record["path"]
        assert path.is_file()
        value = json.loads(path.read_text(encoding="utf-8"))
        if record["id"] in {
            "primary_key_definition",
            "schema_decision",
            "schema_quarantine",
            "schema_apply_receipt",
        }:
            Draft202012Validator.check_schema(value)
