from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from changebridge.contracts import ContractError, semantic_digest
from changebridge.source_workload import materialize_workload, replay_workload, validate_workload

SCHEMA_SET_DIGEST = "a" * 64


def _rebind_workload_id(spec: dict[str, Any]) -> None:
    material = {key: deepcopy(value) for key, value in spec.items() if key != "workload_id"}
    spec["workload_id"] = semantic_digest(material, domain="source-workload-identity")


def test_same_seed_is_byte_semantically_deterministic() -> None:
    first = materialize_workload(424242, SCHEMA_SET_DIGEST)
    second = materialize_workload(424242, SCHEMA_SET_DIGEST)
    assert first == second
    assert replay_workload(first) == replay_workload(second)


def test_different_seed_changes_identity_and_history() -> None:
    first = materialize_workload(424242, SCHEMA_SET_DIGEST)
    second = materialize_workload(424243, SCHEMA_SET_DIGEST)
    assert first["workload_id"] != second["workload_id"]
    assert replay_workload(first)["history_digest"] != replay_workload(second)["history_digest"]


def test_reference_replay_preserves_boundaries_and_expected_state() -> None:
    spec = materialize_workload(424242, SCHEMA_SET_DIGEST)
    pre = replay_workload(spec, through_phase="PRE_BOUNDARY")
    final = replay_workload(spec)
    assert pre["tables"]["orders"]["row_count"] == 6
    assert pre["tables"]["order_items"]["row_count"] == 66
    assert len(pre["committed_transactions"]) == 10
    assert [tx["transaction_id"] for tx in pre["aborted_transactions"]] == ["tx-011-abort"]
    assert all(row["order_id"] != "order-abort" for row in pre["tables"]["orders"]["rows"])
    assert final["tables"]["orders"]["row_count"] == 6
    assert final["whole_state_digest"] != pre["whole_state_digest"]


def test_workload_covers_every_required_semantic_case() -> None:
    spec = materialize_workload(424242, SCHEMA_SET_DIGEST)
    cases = {case for transaction in spec["transactions"] for case in transaction["cases"]}
    assert {
        "single_row_insert",
        "multi_row_insert",
        "update",
        "delete",
        "multi_table_transaction",
        "concurrent_writers",
        "large_transaction",
        "null_vs_absent",
        "unicode",
        "decimal",
        "utc_timestamp_edge",
        "controlled_schema_change",
        "rollback",
    } <= cases


@pytest.mark.parametrize("seed", [-1, 2**63, True, "424242"])
def test_invalid_seeds_fail_closed(seed: object) -> None:
    with pytest.raises(ContractError, match="CBSRC001_INVALID_SEED"):
        materialize_workload(seed, SCHEMA_SET_DIGEST)  # type: ignore[arg-type]


def test_tampered_workload_identity_fails_closed() -> None:
    spec = materialize_workload(424242, SCHEMA_SET_DIGEST)
    spec["workload_id"] = "0" * 64
    with pytest.raises(ContractError, match="CBSRC004_WORKLOAD_ID_MISMATCH"):
        validate_workload(spec)


def test_tampered_event_digest_fails_closed() -> None:
    spec = materialize_workload(424242, SCHEMA_SET_DIGEST)
    spec["transactions"][0]["events"][0]["event_digest"] = "0" * 64
    spec["transactions"][0]["transaction_digest"] = semantic_digest(
        {
            key: deepcopy(value)
            for key, value in spec["transactions"][0].items()
            if key != "transaction_digest"
        },
        domain="source-history-transaction",
    )
    _rebind_workload_id(spec)
    with pytest.raises(ContractError, match="CBSRC028_EVENT_DIGEST_MISMATCH"):
        validate_workload(spec)


def test_invalid_commit_schedule_fails_closed() -> None:
    spec = materialize_workload(424242, SCHEMA_SET_DIGEST)
    spec["transactions"][1]["commit_ordinal"] = 1
    spec["transactions"][1]["transaction_digest"] = semantic_digest(
        {
            key: deepcopy(value)
            for key, value in spec["transactions"][1].items()
            if key != "transaction_digest"
        },
        domain="source-history-transaction",
    )
    _rebind_workload_id(spec)
    with pytest.raises(ContractError, match="CBSRC009_INVALID_COMMIT_SCHEDULE"):
        validate_workload(spec)


def test_replay_rejects_before_image_drift() -> None:
    spec = materialize_workload(424242, SCHEMA_SET_DIGEST)
    event = spec["transactions"][3]["events"][0]
    event["before"]["amount"] = 1
    event_body = {key: deepcopy(value) for key, value in event.items() if key != "event_digest"}
    event["event_digest"] = semantic_digest(event_body, domain="source-history-event")
    transaction = spec["transactions"][3]
    transaction_body = {
        key: deepcopy(value) for key, value in transaction.items() if key != "transaction_digest"
    }
    transaction["transaction_digest"] = semantic_digest(
        transaction_body, domain="source-history-transaction"
    )
    _rebind_workload_id(spec)
    with pytest.raises(ContractError, match="CBSRC012_REPLAY_BEFORE_MISMATCH"):
        replay_workload(spec)
