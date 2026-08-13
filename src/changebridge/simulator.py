"""Deterministic failure lab used by CI and interview walkthroughs."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from typing import Any

from changebridge.canonical import digest
from changebridge.cutover import evaluate_cutover
from changebridge.engine import (
    ChangeBridgeEngine,
    CompareAndSwapConflict,
    FrontierGap,
    ReplayConflict,
)
from changebridge.model import CdcBatch, CdcTransaction, ChangeEvent, Operation
from changebridge.reconciliation import reconcile
from changebridge.schema import Field, check_compatibility


def _event(
    table: str,
    key: str,
    operation: Operation,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> ChangeEvent:
    return ChangeEvent(table, key, operation, before, after)


def fixture() -> tuple[dict[str, dict[str, dict[str, Any]]], CdcBatch]:
    snapshot: dict[str, dict[str, dict[str, Any]]] = {
        "customers": {
            "c-001": {"customer_id": "c-001", "email": "ada@example.com", "tier": "silver"}
        },
        "orders": {
            "o-001": {"amount": 1200, "customer_id": "c-001", "order_id": "o-001"},
            "o-002": {"amount": 800, "customer_id": "c-001", "order_id": "o-002"},
        },
    }
    transactions = (
        CdcTransaction(
            "tx-110",
            110,
            "2026-01-01T00:00:01Z",
            (
                _event(
                    "customers",
                    "c-001",
                    Operation.UPDATE,
                    snapshot["customers"]["c-001"],
                    {"customer_id": "c-001", "email": "ada@example.com", "tier": "gold"},
                ),
            ),
        ),
        CdcTransaction(
            "tx-120",
            120,
            "2026-01-01T00:00:02Z",
            (
                _event(
                    "orders", "o-002", Operation.DELETE, snapshot["orders"]["o-002"], None
                ),
            ),
        ),
        CdcTransaction(
            "tx-130",
            130,
            "2026-01-01T00:00:03Z",
            (
                _event(
                    "orders",
                    "o-003",
                    Operation.INSERT,
                    None,
                    {"amount": 2500, "customer_id": "c-001", "order_id": "o-003"},
                ),
            ),
        ),
    )
    return snapshot, CdcBatch("batch-100-130", 100, 130, transactions)


def expected_state(
    snapshot: dict[str, dict[str, dict[str, Any]]],
) -> dict[str, dict[str, dict[str, Any]]]:
    result = deepcopy(snapshot)
    result["customers"]["c-001"]["tier"] = "gold"
    del result["orders"]["o-002"]
    result["orders"]["o-003"] = {
        "amount": 2500,
        "customer_id": "c-001",
        "order_id": "o-003",
    }
    return result


def _expect_failure(error_type: type[Exception], operation: Callable[[], object]) -> bool:
    try:
        operation()
    except error_type:
        return True
    return False


def run_failure_lab() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def record(name: str, passed: bool, proof: Any) -> None:
        checks.append({"check": name, "passed": passed, "proof": proof})

    snapshot, batch = fixture()
    engine = ChangeBridgeEngine()
    engine.create_generation("g-20260101", 100, "orders-v1")
    engine.load_snapshot("g-20260101", snapshot)
    record("contiguous_batch", engine.apply_batch("g-20260101", batch) == "applied", "100->130")
    record(
        "idempotent_batch_replay",
        engine.apply_batch("g-20260101", batch) == "replayed",
        batch.batch_id,
    )
    record("delete_tombstone", len(engine.tombstones("g-20260101")) == 1, "orders/o-002@120")

    gap_batch = CdcBatch("batch-gap", 140, 150, ())
    record(
        "frontier_gap_blocked",
        _expect_failure(FrontierGap, lambda: engine.apply_batch("g-20260101", gap_batch)),
        "expected start=130, received=140",
    )

    changed_transaction = CdcTransaction(
        "tx-110",
        131,
        "2026-01-01T00:00:04Z",
        (
            _event(
                "customers",
                "c-001",
                Operation.UPDATE,
                None,
                {"customer_id": "c-001", "email": "changed@example.com", "tier": "gold"},
            ),
        ),
    )
    conflicting = CdcBatch("batch-conflict", 130, 131, (changed_transaction,))
    record(
        "conflicting_transaction_replay_blocked",
        _expect_failure(ReplayConflict, lambda: engine.apply_batch("g-20260101", conflicting)),
        "tx-110 digest mismatch",
    )

    crash_engine = ChangeBridgeEngine()
    crash_engine.create_generation("g-crash", 100, "orders-v1")
    crash_engine.load_snapshot("g-crash", snapshot)
    crashed = _expect_failure(
        RuntimeError,
        lambda: crash_engine.apply_batch("g-crash", batch, fail_before_commit=True),
    )
    record(
        "crash_atomicity",
        crashed and crash_engine.get_generation("g-crash").current_lsn == 100,
        "frontier unchanged after injected crash",
    )

    previous_schema = (
        Field("order_id", "string", False),
        Field("amount", "integer", False),
    )
    compatible = check_compatibility(
        previous_schema, previous_schema + (Field("campaign_id", "string", True),)
    )
    breaking = check_compatibility(previous_schema, (Field("order_id", "string", False),))
    record("nullable_schema_addition", compatible.compatible, "campaign_id nullable")
    record("breaking_schema_blocked", not breaking.compatible, breaking.reasons)

    actual = engine.state("g-20260101")
    report = reconcile("g-20260101", 130, expected_state(snapshot), actual)
    record("frontier_reconciliation", report.matched, report.as_dict())
    mismatch_expected = expected_state(snapshot)
    mismatch_expected["orders"]["o-003"]["amount"] = 9999
    mismatch = reconcile("g-20260101", 130, mismatch_expected, actual)
    record("settlement_mismatch_detected", not mismatch.matched, mismatch.as_dict())

    lag_gate = evaluate_cutover(
        report,
        compatible,
        lag_seconds=31,
        max_lag_seconds=30,
        pre_migration_checks_passed=True,
        rollback_generation_available=True,
    )
    record("lag_gate", not lag_gate.allowed, lag_gate.failures)
    gate = evaluate_cutover(
        report,
        compatible,
        lag_seconds=2.5,
        max_lag_seconds=30,
        pre_migration_checks_passed=True,
        rollback_generation_available=True,
    )
    if gate.allowed:
        engine.mark_ready("g-20260101")
        new_version = engine.activate("g-20260101", expected_version=0)
    else:
        new_version = -1
    record("proof_gated_cutover", new_version == 1, engine.active_pointer())
    record(
        "concurrent_cutover_blocked",
        _expect_failure(
            CompareAndSwapConflict, lambda: engine.activate("g-20260101", expected_version=0)
        ),
        "stale pointer version=0",
    )

    engine.close()
    crash_engine.close()
    return {
        "architecture": "frontier-bound-migration-generations",
        "claim_level": "LOCAL_SIMULATION",
        "checks": checks,
        "evidence_digest": digest(checks),
        "metrics": {
            "checks_passed": sum(item["passed"] for item in checks),
            "checks_total": len(checks),
        },
        "production_claim": False,
        "result": "PASS" if all(item["passed"] for item in checks) else "FAIL",
        "scope": "SQLite correctness oracle; no managed AWS service was invoked",
    }
