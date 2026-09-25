from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from changebridge.generation_registry import (
    GenerationRegistry,
    GenerationRegistryError,
    deterministic_generation_id,
    generation_namespace,
    generation_warehouse,
)

WORKLOAD_ID = "34edddda5aee96dc7236aaf31187cff845e7d409ad073a4b79c10a1a22b54ff8"


def generation_record(tmp_path: Path) -> dict[str, object]:
    generation_id = deterministic_generation_id(WORKLOAD_ID)
    namespace = generation_namespace(generation_id)
    warehouse = generation_warehouse((tmp_path / "warehouse").resolve(), generation_id)
    return {
        "generation_id": generation_id,
        "workload_id": WORKLOAD_ID,
        "run_id": "stage23-full-snapshot-handoff-001",
        "snapshot_frontier": "0/194FB20",
        "schema_set_digest": "5bfe6ecf0e7576a91f9e1a8aed715b7653d3aa98009162b65dc8a5f2bff93979",
        "canonicalization_profile": "changebridge-canonical-json/1.0.0",
        "warehouse_path": str(warehouse),
        "namespace": namespace,
        "table_map": {
            "order_items": f"stage23.{namespace}.order_items",
            "orders": f"stage23.{namespace}.orders",
        },
    }


def test_generation_registration_transition_and_idempotent_replay(tmp_path: Path) -> None:
    record = generation_record(tmp_path)
    generation_id = str(record["generation_id"])
    with GenerationRegistry(tmp_path / "control.db") as registry:
        first = registry.register_generation(record)
        second = registry.register_generation(record)
        assert first == second
        loading = registry.transition(
            generation_id,
            expected_revision=0,
            to_state="SNAPSHOT_LOADING",
            actor="test",
            decision={"reason": "test"},
        )
        assert (loading["state"], loading["revision"]) == ("SNAPSHOT_LOADING", 1)
        replay = registry.transition(
            generation_id,
            expected_revision=0,
            to_state="SNAPSHOT_LOADING",
            actor="test",
            decision={"reason": "test"},
        )
        assert replay == loading


def test_generation_replay_conflict_and_stale_revision_fail(tmp_path: Path) -> None:
    record = generation_record(tmp_path)
    generation_id = str(record["generation_id"])
    with GenerationRegistry(tmp_path / "control.db") as registry:
        registry.register_generation(record)
        conflicting = {**record, "snapshot_frontier": "0/194FB21"}
        with pytest.raises(GenerationRegistryError, match="CBG009_GENERATION_REPLAY_CONFLICT"):
            registry.register_generation(conflicting)
        registry.transition(
            generation_id,
            expected_revision=0,
            to_state="SNAPSHOT_LOADING",
            actor="test",
            decision={"reason": "test"},
        )
        with pytest.raises(GenerationRegistryError, match="CBG013_STALE_REVISION"):
            registry.transition(
                generation_id,
                expected_revision=0,
                to_state="CDC_APPLYING",
                actor="test",
                decision={"reason": "stale"},
            )


def test_shard_conflict_and_protected_generation_write_fail(tmp_path: Path) -> None:
    record = generation_record(tmp_path)
    generation_id = str(record["generation_id"])
    with GenerationRegistry(tmp_path / "control.db") as registry:
        registry.register_generation(record)
        registry.transition(
            generation_id,
            expected_revision=0,
            to_state="SNAPSHOT_LOADING",
            actor="test",
            decision={"reason": "test"},
        )
        values = {
            "generation_id": generation_id,
            "shard_id": "snapshot-orders-001",
            "source_table": "orders",
            "input_digest": "a" * 64,
            "row_count": 6,
            "idempotency_key": "b" * 64,
            "commit_token": "c" * 64,
        }
        assert registry.claim_shard(**values) == registry.claim_shard(**values)
        with pytest.raises(GenerationRegistryError, match="CBG016_SHARD_REPLAY_CONFLICT"):
            registry.claim_shard(**{**values, "input_digest": "d" * 64})
        with pytest.raises(GenerationRegistryError, match="CBG025_ADMISSION_PROOF_REQUIRED"):
            registry.transition(
                generation_id,
                expected_revision=1,
                to_state="CDC_APPLYING",
                actor="test",
                decision={"reason": "missing proof"},
            )
        with registry.connection:
            registry.connection.execute(
                "UPDATE generation_registry SET state = 'CDC_APPLYING' WHERE generation_id = ?",
                (generation_id,),
            )
        with pytest.raises(GenerationRegistryError, match="CBG015_GENERATION_NOT_WRITABLE"):
            registry.claim_shard(**{**values, "shard_id": "snapshot-orders-002"})


@given(st.text(min_size=0, max_size=40))
def test_workload_identity_is_fail_closed(value: str) -> None:
    if len(value) == 64 and set(value) <= set("0123456789abcdef"):
        assert deterministic_generation_id(value) == f"generation-{value[:24]}"
    else:
        with pytest.raises(GenerationRegistryError, match="CBG001_INVALID_WORKLOAD_ID"):
            deterministic_generation_id(value)


def test_symlink_warehouse_root_is_rejected(tmp_path: Path) -> None:
    actual = tmp_path / "actual"
    actual.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(actual, target_is_directory=True)
    with pytest.raises(GenerationRegistryError, match="CBG003_WAREHOUSE_ROOT_SYMLINK"):
        generation_warehouse(alias, "generation-abc")


def test_generation_registration_rejects_foreign_warehouse(tmp_path: Path) -> None:
    record = generation_record(tmp_path)
    record["warehouse_path"] = str((tmp_path / "foreign").resolve())
    with (
        GenerationRegistry(tmp_path / "control.db") as registry,
        pytest.raises(GenerationRegistryError, match="CBG024_WAREHOUSE_OWNERSHIP"),
    ):
        registry.register_generation(record)
