"""Deterministic source-history specification and independent replay oracle.

Logical identity deliberately excludes PostgreSQL transaction identifiers, WAL
positions, host identity, wall-clock time, and temporary execution paths.
"""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any, Literal

from changebridge.contracts import ContractError, semantic_digest

WORKLOAD_CONTRACT_VERSION = "source-workload-spec/1.0.0"
DRIVER_SEMANTIC_VERSION = "changebridge-source-driver/1.0.0"
LOGICAL_CLOCK = {
    "epoch": "2024-02-29T23:59:58.000000Z",
    "increment_microseconds": 250000,
}
_PHASES = ("PRE_BOUNDARY", "POST_BOUNDARY")


def _failure(code: str, detail: str) -> ContractError:
    return ContractError(code, detail)


def _order(
    order_id: str,
    customer_id: str,
    amount: int,
    campaign_id: str | None,
    *,
    source_note: str | None | Literal["ABSENT"] = "ABSENT",
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "amount": amount,
        "campaign_id": campaign_id,
        "customer_id": customer_id,
        "order_id": order_id,
    }
    if source_note != "ABSENT":
        row["source_note"] = source_note
    return row


def _item(
    item_id: str,
    order_id: str,
    quantity: int,
    unit_price: str,
    note: str | None,
    timestamp: str,
) -> dict[str, Any]:
    return {
        "created_at": timestamp,
        "item_id": item_id,
        "note": note,
        "order_id": order_id,
        "quantity": quantity,
        "unit_price": unit_price,
    }


def _event(
    sequence: int,
    table: str,
    operation: str,
    key: str,
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
    schema_version: str,
    cases: Sequence[str],
) -> dict[str, Any]:
    body = {
        "after": deepcopy(after),
        "before": deepcopy(before),
        "cases": list(cases),
        "event_sequence": sequence,
        "key": key,
        "operation": operation,
        "schema_version": schema_version,
        "table": table,
    }
    return {
        **body,
        "event_digest": semantic_digest(body, domain="source-history-event"),
    }


def _transaction(
    transaction_id: str,
    sequence: int,
    commit_ordinal: int | None,
    outcome: str,
    phase: str,
    events: Sequence[Mapping[str, Any]],
    cases: Sequence[str],
) -> dict[str, Any]:
    body = {
        "cases": list(cases),
        "commit_ordinal": commit_ordinal,
        "events": [dict(event) for event in events],
        "outcome": outcome,
        "phase": phase,
        "transaction_id": transaction_id,
        "transaction_sequence": sequence,
    }
    return {
        **body,
        "transaction_digest": semantic_digest(body, domain="source-history-transaction"),
    }


def materialize_workload(seed: int, schema_set_digest: str) -> dict[str, Any]:
    """Build the complete deterministic transaction plan before execution."""

    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < 2**63:
        raise _failure("CBSRC001_INVALID_SEED", repr(seed))
    if len(schema_set_digest) != 64 or any(c not in "0123456789abcdef" for c in schema_set_digest):
        raise _failure("CBSRC002_INVALID_SCHEMA_SET_DIGEST", schema_set_digest)

    rng = random.Random(seed)
    suffix = f"{rng.randrange(1_000_000):06d}"
    o1 = _order("order-001", f"José-🧪-{suffix}", 1250, None)
    o2 = _order("order-002", f"customer-{suffix}-2", 2000, "campaign-a")
    o2_updated = _order("order-002", f"customer-{suffix}-2", 2350, None)
    o3 = _order("order-003", f"customer-{suffix}-3", 3000, "campaign-b")
    o4 = _order("order-004", f"customer-{suffix}-4", 4500, None)
    o4_null = _order("order-004", f"customer-{suffix}-4", 4500, None, source_note=None)
    o5 = _order("order-005", f"writer-a-{suffix}", 5000, None)
    o6 = _order("order-006", f"writer-b-{suffix}", 6000, None)
    o7 = _order("order-007", f"large-{suffix}", 6400, None)
    o1_null = _order("order-001", f"José-🧪-{suffix}", 1250, None, source_note=None)
    o1_v11 = _order("order-001", f"José-🧪-{suffix}", 1250, None, source_note="reviewed")
    post_o4 = _order(
        "order-004",
        f"customer-{suffix}-4",
        4750,
        "post-boundary",
        source_note=None,
    )
    abort_order = _order("order-abort", f"abort-{suffix}", 9999, None, source_note="rollback")

    large_items = [
        _event(
            index + 2,
            "order_items",
            "insert",
            f"item-007-{index:03d}",
            None,
            _item(
                f"item-007-{index:03d}",
                "order-007",
                1,
                "100.00",
                None if index % 2 == 0 else f"batch-{index:03d}",
                "2024-03-01T00:00:00.000000Z",
            ),
            "order_items/1.0.0",
            ("large_transaction", "decimal", "null_vs_value"),
        )
        for index in range(64)
    ]

    transactions = [
        _transaction(
            "tx-001-single-insert",
            1,
            1,
            "COMMIT",
            "PRE_BOUNDARY",
            [
                _event(
                    1,
                    "orders",
                    "insert",
                    "order-001",
                    None,
                    o1,
                    "orders/1.0.0",
                    ("single_row_insert", "unicode", "null"),
                )
            ],
            ("single_row_insert", "unicode", "null"),
        ),
        _transaction(
            "tx-002-multi-row",
            2,
            2,
            "COMMIT",
            "PRE_BOUNDARY",
            [
                _event(
                    1,
                    "orders",
                    "insert",
                    "order-002",
                    None,
                    o2,
                    "orders/1.0.0",
                    ("multi_row_insert",),
                ),
                _event(
                    2,
                    "orders",
                    "insert",
                    "order-003",
                    None,
                    o3,
                    "orders/1.0.0",
                    ("multi_row_insert",),
                ),
            ],
            ("multi_row_insert",),
        ),
        _transaction(
            "tx-003-multi-table",
            3,
            3,
            "COMMIT",
            "PRE_BOUNDARY",
            [
                _event(
                    1,
                    "orders",
                    "insert",
                    "order-004",
                    None,
                    o4,
                    "orders/1.0.0",
                    ("multi_table_transaction",),
                ),
                _event(
                    2,
                    "order_items",
                    "insert",
                    "item-004-001",
                    None,
                    _item(
                        "item-004-001",
                        "order-004",
                        2,
                        "12.50",
                        "café",
                        "2024-02-29T23:59:58.000000Z",
                    ),
                    "order_items/1.0.0",
                    ("multi_table_transaction", "decimal", "unicode", "utc_timestamp_edge"),
                ),
                _event(
                    3,
                    "order_items",
                    "insert",
                    "item-004-002",
                    None,
                    _item(
                        "item-004-002", "order-004", 1, "25.00", None, "2024-02-29T23:59:58.250000Z"
                    ),
                    "order_items/1.0.0",
                    ("multi_table_transaction", "decimal", "null"),
                ),
            ],
            ("multi_table_transaction", "decimal", "utc_timestamp_edge"),
        ),
        _transaction(
            "tx-004-update",
            4,
            4,
            "COMMIT",
            "PRE_BOUNDARY",
            [
                _event(
                    1,
                    "orders",
                    "update",
                    "order-002",
                    o2,
                    o2_updated,
                    "orders/1.0.0",
                    ("update", "null_vs_value"),
                )
            ],
            ("update", "null_vs_value"),
        ),
        _transaction(
            "tx-005-delete",
            5,
            5,
            "COMMIT",
            "PRE_BOUNDARY",
            [_event(1, "orders", "delete", "order-003", o3, None, "orders/1.0.0", ("delete",))],
            ("delete",),
        ),
        _transaction(
            "tx-006-writer-a",
            6,
            7,
            "COMMIT",
            "PRE_BOUNDARY",
            [
                _event(
                    1,
                    "orders",
                    "insert",
                    "order-005",
                    None,
                    o5,
                    "orders/1.0.0",
                    ("concurrent_writers",),
                )
            ],
            ("concurrent_writers",),
        ),
        _transaction(
            "tx-007-writer-b",
            7,
            6,
            "COMMIT",
            "PRE_BOUNDARY",
            [
                _event(
                    1,
                    "orders",
                    "insert",
                    "order-006",
                    None,
                    o6,
                    "orders/1.0.0",
                    ("concurrent_writers",),
                )
            ],
            ("concurrent_writers",),
        ),
        _transaction(
            "tx-008-large",
            8,
            8,
            "COMMIT",
            "PRE_BOUNDARY",
            [
                _event(
                    1,
                    "orders",
                    "insert",
                    "order-007",
                    None,
                    o7,
                    "orders/1.0.0",
                    ("large_transaction",),
                ),
                *large_items,
            ],
            ("large_transaction",),
        ),
        _transaction(
            "tx-009-schema-change",
            9,
            9,
            "COMMIT",
            "PRE_BOUNDARY",
            [
                _event(
                    1,
                    "__schema__",
                    "schema_change",
                    "orders",
                    {"version": "1.0.0"},
                    {"version": "1.1.0", "change": "add nullable source_note"},
                    "orders/1.1.0",
                    ("controlled_schema_change",),
                )
            ],
            ("controlled_schema_change",),
        ),
        _transaction(
            "tx-010-null-versus-absent",
            10,
            10,
            "COMMIT",
            "PRE_BOUNDARY",
            [
                _event(
                    1,
                    "orders",
                    "update",
                    "order-001",
                    o1_null,
                    o1_v11,
                    "orders/1.1.0",
                    ("null_vs_absent", "controlled_schema_change"),
                )
            ],
            ("null_vs_absent", "controlled_schema_change"),
        ),
        _transaction(
            "tx-011-abort",
            11,
            None,
            "ABORT",
            "PRE_BOUNDARY",
            [
                _event(
                    1,
                    "orders",
                    "insert",
                    "order-abort",
                    None,
                    abort_order,
                    "orders/1.1.0",
                    ("rollback",),
                )
            ],
            ("rollback",),
        ),
        _transaction(
            "tx-012-post-boundary",
            12,
            11,
            "COMMIT",
            "POST_BOUNDARY",
            [
                _event(
                    1,
                    "orders",
                    "update",
                    "order-004",
                    o4_null,
                    post_o4,
                    "orders/1.1.0",
                    ("post_boundary",),
                )
            ],
            ("post_boundary",),
        ),
    ]

    material = {
        "canonicalization_profile": "changebridge-canonical-json/1.0.0",
        "concurrency_schedule": [
            {
                "barrier": "writers-ready",
                "commit_order": ["tx-007-writer-b", "tx-006-writer-a"],
                "transactions": ["tx-006-writer-a", "tx-007-writer-b"],
            }
        ],
        "contract_version": WORKLOAD_CONTRACT_VERSION,
        "driver_semantic_version": DRIVER_SEMANTIC_VERSION,
        "logical_clock": LOGICAL_CLOCK,
        "schema_set_digest": schema_set_digest,
        "seed": seed,
        "transactions": transactions,
    }
    spec = {**material, "workload_id": semantic_digest(material, domain="source-workload-identity")}
    validate_workload(spec)
    return spec


def validate_workload(spec: Mapping[str, Any]) -> None:
    if spec.get("contract_version") != WORKLOAD_CONTRACT_VERSION:
        raise _failure("CBSRC003_UNKNOWN_WORKLOAD_VERSION", str(spec.get("contract_version")))
    expected = {key: deepcopy(value) for key, value in spec.items() if key != "workload_id"}
    if spec.get("workload_id") != semantic_digest(expected, domain="source-workload-identity"):
        raise _failure("CBSRC004_WORKLOAD_ID_MISMATCH", str(spec.get("workload_id")))
    transactions = spec.get("transactions")
    if not isinstance(transactions, list) or not transactions:
        raise _failure("CBSRC005_INVALID_TRANSACTION_PLAN", "transactions")
    ids: set[str] = set()
    sequences: set[int] = set()
    commits: set[int] = set()
    for transaction in transactions:
        if not isinstance(transaction, Mapping):
            raise _failure("CBSRC005_INVALID_TRANSACTION_PLAN", "transaction")
        tx_id = transaction.get("transaction_id")
        sequence = transaction.get("transaction_sequence")
        phase = transaction.get("phase")
        outcome = transaction.get("outcome")
        commit = transaction.get("commit_ordinal")
        if not isinstance(tx_id, str) or tx_id in ids:
            raise _failure("CBSRC006_DUPLICATE_TRANSACTION_ID", str(tx_id))
        if not isinstance(sequence, int) or sequence in sequences:
            raise _failure("CBSRC007_DUPLICATE_TRANSACTION_SEQUENCE", str(sequence))
        if phase not in _PHASES or outcome not in {"COMMIT", "ABORT"}:
            raise _failure("CBSRC005_INVALID_TRANSACTION_PLAN", tx_id)
        if outcome == "ABORT" and commit is not None:
            raise _failure("CBSRC008_ABORT_HAS_COMMIT_ORDINAL", tx_id)
        if outcome == "COMMIT":
            if not isinstance(commit, int) or commit <= 0 or commit in commits:
                raise _failure("CBSRC009_INVALID_COMMIT_SCHEDULE", tx_id)
            commits.add(commit)
        events = transaction.get("events")
        if not isinstance(events, list) or not events:
            raise _failure("CBSRC005_INVALID_TRANSACTION_PLAN", f"{tx_id}:events")
        for event in events:
            if not isinstance(event, Mapping):
                raise _failure("CBSRC005_INVALID_TRANSACTION_PLAN", f"{tx_id}:event")
            event_body = {
                key: deepcopy(value) for key, value in event.items() if key != "event_digest"
            }
            if event.get("event_digest") != semantic_digest(
                event_body, domain="source-history-event"
            ):
                raise _failure("CBSRC028_EVENT_DIGEST_MISMATCH", f"{tx_id}:{event.get('key')}")
        transaction_body = {
            key: deepcopy(value)
            for key, value in transaction.items()
            if key != "transaction_digest"
        }
        if transaction.get("transaction_digest") != semantic_digest(
            transaction_body, domain="source-history-transaction"
        ):
            raise _failure("CBSRC029_TRANSACTION_DIGEST_MISMATCH", str(tx_id))
        ids.add(tx_id)
        sequences.add(sequence)
    if commits != set(range(1, len(commits) + 1)):
        raise _failure("CBSRC009_INVALID_COMMIT_SCHEDULE", repr(sorted(commits)))
    schedules = spec.get("concurrency_schedule")
    if not isinstance(schedules, list) or len(schedules) != 1:
        raise _failure("CBSRC010_INVALID_CONCURRENCY_SCHEDULE", repr(schedules))
    schedule = schedules[0]
    if not isinstance(schedule, Mapping):
        raise _failure("CBSRC010_INVALID_CONCURRENCY_SCHEDULE", "shape")
    scheduled = schedule.get("transactions")
    commit_order = schedule.get("commit_order")
    if set(scheduled or []) != {"tx-006-writer-a", "tx-007-writer-b"} or commit_order != [
        "tx-007-writer-b",
        "tx-006-writer-a",
    ]:
        raise _failure("CBSRC010_INVALID_CONCURRENCY_SCHEDULE", repr(schedule))


def replay_workload(
    spec: Mapping[str, Any],
    *,
    through_phase: Literal["PRE_BOUNDARY", "POST_BOUNDARY"] = "POST_BOUNDARY",
) -> dict[str, Any]:
    """Independently replay committed logical events and return canonical truth."""

    validate_workload(spec)
    state: dict[str, dict[str, dict[str, Any]]] = {"order_items": {}, "orders": {}}
    committed: list[dict[str, Any]] = []
    aborted: list[dict[str, Any]] = []
    transactions = list(spec["transactions"])
    phase_limit = _PHASES.index(through_phase)
    eligible = [tx for tx in transactions if _PHASES.index(tx["phase"]) <= phase_limit]
    eligible.sort(key=lambda tx: tx["commit_ordinal"] or 2**31)
    for transaction in eligible:
        if transaction["outcome"] == "ABORT":
            aborted.append(deepcopy(transaction))
            continue
        for event in transaction["events"]:
            table = event["table"]
            operation = event["operation"]
            if operation == "schema_change":
                for row in state["orders"].values():
                    row["source_note"] = None
                continue
            rows = state[table]
            key = event["key"]
            before = event["before"]
            after = event["after"]
            current = rows.get(key)
            if operation == "insert":
                if current is not None or before is not None or after is None:
                    raise _failure("CBSRC011_REPLAY_INSERT_CONFLICT", f"{table}:{key}")
                rows[key] = deepcopy(after)
            elif operation == "update":
                if current != before or after is None:
                    raise _failure("CBSRC012_REPLAY_BEFORE_MISMATCH", f"{table}:{key}")
                rows[key] = deepcopy(after)
            elif operation == "delete":
                if current != before or after is not None:
                    raise _failure("CBSRC012_REPLAY_BEFORE_MISMATCH", f"{table}:{key}")
                del rows[key]
            else:
                raise _failure("CBSRC013_UNKNOWN_OPERATION", str(operation))
        committed.append(deepcopy(transaction))

    tables: dict[str, Any] = {}
    for table, keyed_rows in sorted(state.items()):
        row_list = [keyed_rows[key] for key in sorted(keyed_rows)]
        tables[table] = {
            "row_count": len(row_list),
            "rows": row_list,
            "state_digest": semantic_digest(row_list, domain=f"source-table-state:{table}"),
        }
    whole = {name: value["state_digest"] for name, value in sorted(tables.items())}
    return {
        "aborted_transactions": aborted,
        "committed_transactions": committed,
        "history_digest": semantic_digest(committed, domain="source-committed-history"),
        "phase": through_phase,
        "tables": tables,
        "whole_state_digest": semantic_digest(whole, domain="source-whole-state"),
        "workload_id": spec["workload_id"],
    }
