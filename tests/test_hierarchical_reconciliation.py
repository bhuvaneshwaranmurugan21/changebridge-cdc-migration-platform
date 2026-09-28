from copy import deepcopy

from changebridge.hierarchical_reconciliation import reconcile

SCHEMAS = {"orders": "orders/1.1.0"}


def test_equal_rows_produce_deterministic_pass() -> None:
    rows = {"orders": [{"order_id": "o1", "amount": 1}, {"order_id": "o2", "amount": 2}]}
    first = reconcile(
        rows, deepcopy(rows), generation_id="g", frontier="0/2", schema_identities=SCHEMAS
    )
    second = reconcile(
        deepcopy(rows), rows, generation_id="g", frontier="0/2", schema_identities=SCHEMAS
    )
    assert first == second
    assert first["verdict"] == "PASS"


def test_mismatches_are_localized() -> None:
    source = {"orders": [{"order_id": "o1", "amount": 1}, {"order_id": "o2", "amount": 2}]}
    target = {"orders": [{"order_id": "o1", "amount": 9}, {"order_id": "o3", "amount": 3}]}
    report = reconcile(source, target, generation_id="g", frontier="0/2", schema_identities=SCHEMAS)
    assert report["verdict"] == "FAIL"
    assert {row["kind"] for row in report["tables"]["orders"]["mismatches"]} == {
        "VALUE_MISMATCH",
        "MISSING_CANDIDATE_ROW",
        "UNEXPECTED_CANDIDATE_ROW",
    }
