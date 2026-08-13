from changebridge.canonical import canonical_json, digest, table_digest
from changebridge.reconciliation import reconcile


def test_canonical_digest_ignores_mapping_order() -> None:
    assert canonical_json({"b": 2, "a": 1}) == canonical_json({"a": 1, "b": 2})
    assert digest({"b": 2, "a": 1}) == digest({"a": 1, "b": 2})
    assert table_digest({"2": {"v": 2}, "1": {"v": 1}}) == table_digest(
        {"1": {"v": 1}, "2": {"v": 2}}
    )


def test_reconciliation_detects_value_mismatch() -> None:
    report = reconcile("g", 10, {"orders": {"1": {"v": 1}}}, {"orders": {"1": {"v": 2}}})
    assert not report.matched
    assert report.tables[0].expected_count == report.tables[0].actual_count
    assert report.tables[0].expected_digest != report.tables[0].actual_digest
