from __future__ import annotations

from copy import deepcopy

import pytest
from hypothesis import given
from hypothesis import strategies as st

from changebridge.contracts import ContractError, compare_source_positions, source_position_key
from changebridge.source_boundary import (
    BOUNDARY_RECEIPT_VERSION,
    LSN_COMPARATOR_VERSION,
    FrontierRegistry,
    PostgresSettings,
    select_first_committed_transaction,
    validate_boundary_receipt,
)


def _position(high: int, low: int) -> dict[str, str]:
    return {"kind": "postgres_lsn", "value": f"{high:X}/{low:X}"}


@given(
    left_high=st.integers(min_value=0, max_value=2**32 - 1),
    left_low=st.integers(min_value=0, max_value=2**32 - 1),
    right_high=st.integers(min_value=0, max_value=2**32 - 1),
    right_low=st.integers(min_value=0, max_value=2**32 - 1),
)
def test_postgres_lsn_numeric_order_matches_u64_order(
    left_high: int, left_low: int, right_high: int, right_low: int
) -> None:
    expected = ((left_high << 32) | left_low) - ((right_high << 32) | right_low)
    actual = compare_source_positions(
        _position(left_high, left_low), _position(right_high, right_low)
    )
    assert actual == ((expected > 0) - (expected < 0))


@pytest.mark.parametrize(
    "value",
    ["0", "0/", "/0", "0x1/0", "1/G", "100000000/0", "0/100000000", "a/0"],
)
def test_malformed_or_overflow_lsn_is_rejected(value: str) -> None:
    with pytest.raises(ContractError, match="CBPOS003_MALFORMED_VALUE"):
        source_position_key({"kind": "postgres_lsn", "value": value})


def test_empty_lsn_is_rejected_as_empty() -> None:
    with pytest.raises(ContractError, match="CBPOS002_UNKNOWN_OR_EMPTY"):
        source_position_key({"kind": "postgres_lsn", "value": ""})


def _receipt() -> dict[str, object]:
    return {
        "receipt_version": BOUNDARY_RECEIPT_VERSION,
        "generation_id": "generation-" + "a" * 24,
        "workload_id": "b" * 64,
        "schema_set_digest": "c" * 64,
        "source_identity_digest": "d" * 64,
        "snapshot_frontier": _position(1, 255),
        "first_post_boundary_position": _position(1, 256),
        "comparator_version": LSN_COMPARATOR_VERSION,
        "snapshot_imported": True,
        "cleanup": {"slot_dropped": True},
    }


def _validate(receipt: dict[str, object]) -> None:
    validate_boundary_receipt(
        receipt,
        expected_generation_id="generation-" + "a" * 24,
        expected_workload_id="b" * 64,
        expected_schema_set_digest="c" * 64,
        expected_source_identity_digest="d" * 64,
    )


def test_valid_boundary_is_strictly_open_after_snapshot() -> None:
    _validate(_receipt())


def test_decoded_transaction_uses_commit_lsn_when_first_change_equals_frontier() -> None:
    frontier = _position(0, 0x194FAE8)
    selected = select_first_committed_transaction(
        [
            {"lsn": "0/194FAE8", "xid": "741", "data": "BEGIN 741"},
            {"lsn": "0/194FAE8", "xid": "741", "data": "table cb.orders: INSERT"},
            {"lsn": "0/194FC20", "xid": "741", "data": "COMMIT 741"},
        ],
        frontier,
    )
    assert selected["first_change_position"] == frontier
    assert selected["first_commit_position"] == _position(0, 0x194FC20)
    assert selected["logical_change_count"] == 1


@pytest.mark.parametrize(
    ("records", "diagnostic"),
    [
        ([], "CBSNP015_NO_POST_BOUNDARY_CHANGE"),
        (
            [{"lsn": "0/194FAA0", "xid": "741", "data": "table cb.orders: INSERT"}],
            "CBSNP017_CHANGE_PRECEDES_FRONTIER",
        ),
        (
            [{"lsn": "0/194FAE8", "xid": "741", "data": "table cb.orders: INSERT"}],
            "CBSNP018_COMMIT_RECORD_MISSING",
        ),
    ],
)
def test_decoded_transaction_selection_fails_closed(
    records: list[dict[str, str]], diagnostic: str
) -> None:
    with pytest.raises(ContractError, match=diagnostic):
        select_first_committed_transaction(records, _position(0, 0x194FAE8))


@pytest.mark.parametrize(
    ("field", "value", "diagnostic"),
    [
        ("generation_id", "generation-" + "f" * 24, "CBSNP004_GENERATION_MISMATCH"),
        ("workload_id", "e" * 64, "CBSNP005_WORKLOAD_MISMATCH"),
        ("schema_set_digest", "e" * 64, "CBSNP006_SCHEMA_MISMATCH"),
        ("source_identity_digest", "e" * 64, "CBSNP007_SOURCE_IDENTITY_MISMATCH"),
        ("snapshot_imported", False, "CBSNP011_SNAPSHOT_NOT_IMPORTED"),
    ],
)
def test_boundary_identity_and_snapshot_mismatches_fail_closed(
    field: str, value: object, diagnostic: str
) -> None:
    receipt = _receipt()
    receipt[field] = value
    with pytest.raises(ContractError, match=diagnostic):
        _validate(receipt)


@pytest.mark.parametrize("position", [_position(1, 255), _position(1, 254)])
def test_exact_s_and_regression_are_rejected(position: dict[str, str]) -> None:
    receipt = _receipt()
    receipt["first_post_boundary_position"] = position
    with pytest.raises(ContractError, match="CBSNP009_NONADVANCING_FIRST_POSITION"):
        _validate(receipt)


def test_incomparable_position_kind_is_rejected() -> None:
    receipt = _receipt()
    receipt["first_post_boundary_position"] = {"kind": "integer", "value": "256"}
    with pytest.raises(ContractError, match="CBSNP001_NON_POSTGRES_FRONTIER"):
        _validate(receipt)


def test_one_generation_cannot_bind_a_second_frontier() -> None:
    registry = FrontierRegistry()
    generation = "generation-" + "a" * 24
    registry.bind(generation, _position(1, 1))
    registry.bind(generation, _position(1, 1))
    with pytest.raises(ContractError, match="CBSNP002_SECOND_FRONTIER"):
        registry.bind(generation, _position(1, 2))


def test_cleanup_failure_is_rejected() -> None:
    receipt = deepcopy(_receipt())
    receipt["cleanup"] = {"slot_dropped": False}
    with pytest.raises(ContractError, match="CBSNP012_CLEANUP_NOT_PROVEN"):
        _validate(receipt)


def test_postgres_settings_are_explicit_and_do_not_leak_ambient_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = {
        "PGHOST": "postgres.invalid",
        "PGPORT": "5432",
        "PGDATABASE": "changebridge",
        "PGUSER": "changebridge",
        "PGPASSWORD": "local-only",
        "CB_SOURCE_SCHEMA": "cb_stage21_test",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    settings = PostgresSettings.from_environment()
    arguments = settings.connect_arguments()
    assert settings.schema == "cb_stage21_test"
    assert arguments["options"] == "-csearch_path=cb_stage21_test"
    assert arguments["connect_timeout"] == 10


def test_missing_postgres_environment_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD", "CB_SOURCE_SCHEMA"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ContractError, match="CBPG001_MISSING_CONNECTION_ENV"):
        PostgresSettings.from_environment()


def test_invalid_source_namespace_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    values = {
        "PGHOST": "postgres.invalid",
        "PGPORT": "5432",
        "PGDATABASE": "changebridge",
        "PGUSER": "changebridge",
        "PGPASSWORD": "local-only",
        "CB_SOURCE_SCHEMA": "public;drop schema public",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    with pytest.raises(ContractError, match="CBSRC023_INVALID_NAMESPACE"):
        PostgresSettings.from_environment()


def test_frontier_registry_rejects_non_postgres_kind() -> None:
    with pytest.raises(ContractError, match="CBSNP001_NON_POSTGRES_FRONTIER"):
        FrontierRegistry().bind("generation-a", {"kind": "integer", "value": "1"})


@pytest.mark.parametrize(
    ("mutation", "diagnostic"),
    [
        ({"receipt_version": "unknown"}, "CBSNP003_UNKNOWN_RECEIPT_VERSION"),
        ({"snapshot_frontier": None}, "CBSNP008_MISSING_BOUNDARY_POSITION"),
        ({"comparator_version": "unknown"}, "CBSNP010_COMPARATOR_VERSION_MISMATCH"),
    ],
)
def test_receipt_protocol_mutations_fail_closed(
    mutation: dict[str, object], diagnostic: str
) -> None:
    receipt = _receipt()
    receipt.update(mutation)
    with pytest.raises(ContractError, match=diagnostic):
        _validate(receipt)
