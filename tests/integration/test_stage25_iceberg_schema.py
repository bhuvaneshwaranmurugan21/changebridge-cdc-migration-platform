from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from changebridge.iceberg_schema import IcebergSchemaAdapter
from changebridge.schema_control import SchemaControlStore
from changebridge.schema_migration import SchemaMigrationCoordinator
from changebridge.schema_policy import SchemaPolicy, SchemaRegistry, registered_schema

ROOT = Path(__file__).resolve().parents[2]
GENERATION = "generation-34edddda5aee96dc7236aaf3"
pytestmark = pytest.mark.iceberg_integration


def load(relative: str) -> dict[str, object]:
    return json.loads((ROOT / relative).read_text())


def jar() -> Path:
    value = os.environ.get("CB_ICEBERG_JAR")
    if not value:
        pytest.fail("CB_ICEBERG_JAR is required; Stage 5 real Iceberg proof cannot skip")
    path = Path(value)
    if not path.is_file():
        pytest.fail(f"CB_ICEBERG_JAR does not exist: {path}")
    return path


def policy() -> tuple[SchemaPolicy, object, object]:
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


def rows() -> list[dict[str, object]]:
    return [
        {"order_id": "order-001", "customer_id": "customer-1", "amount": 1250, "campaign_id": None},
        {
            "order_id": "order-002",
            "customer_id": "customer-2",
            "amount": 2500,
            "campaign_id": "spring",
        },
    ]


def test_real_nullable_addition_is_atomic_and_idempotent(tmp_path: Path) -> None:
    schema_policy, old, new = policy()
    with (
        IcebergSchemaAdapter(warehouse=tmp_path / "warehouse", iceberg_jar=jar()) as iceberg,
        SchemaControlStore(tmp_path / "control.db") as control,
    ):
        iceberg.create_predecessor(rows())
        before = iceberg.metadata()
        coordinator = SchemaMigrationCoordinator(
            policy=schema_policy, control=control, iceberg=iceberg
        )
        first = coordinator.execute(
            generation_id=GENERATION,
            source_table="orders",
            previous=old,
            candidate=new,
            frontier="0/194FE20",
        )
        second = coordinator.execute(
            generation_id=GENERATION,
            source_table="orders",
            previous=old,
            candidate=new,
            frontier="0/194FE20",
        )
        assert first["apply"]["recovered"] is False
        assert second["apply"]["recovered"] is True
        assert first["apply"]["metadata_location"] == second["apply"]["metadata_location"]
        assert before["snapshot_count"] == first["apply"]["snapshot_count"]
        assert all(row["source_note"] is None for row in first["rows"])
        admission = control.require_admission(
            generation_id=GENERATION,
            source_table="orders",
            candidate_digest=new.digest,
            policy_digest=first["decision"]["policy_digest"],
        )
        assert admission["receipt_id"] == first["receipt"]["receipt_id"]
