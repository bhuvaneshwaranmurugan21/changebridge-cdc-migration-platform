from __future__ import annotations

import pytest

from changebridge.cutover import evaluate_cutover
from changebridge.engine import ChangeBridgeEngine, CompareAndSwapConflict, InvalidGenerationState
from changebridge.reconciliation import reconcile
from changebridge.schema import Field, check_compatibility
from changebridge.simulator import expected_state, fixture


def test_schema_policy() -> None:
    old = (Field("id", "string", False), Field("amount", "integer", False))
    additive = check_compatibility(old, old + (Field("campaign", "string", True),))
    breaking = check_compatibility(old, (Field("id", "integer", False),))
    assert additive.compatible
    assert not breaking.compatible
    assert "type change: id string->integer" in breaking.reasons
    assert "removed field: amount" in breaking.reasons


def test_cutover_requires_every_proof_and_cas() -> None:
    snapshot, batch = fixture()
    engine = ChangeBridgeEngine()
    engine.create_generation("g-1", 100, "v1")
    engine.load_snapshot("g-1", snapshot)
    with pytest.raises(InvalidGenerationState):
        engine.activate("g-1", 0)
    engine.apply_batch("g-1", batch)
    report = reconcile("g-1", 130, expected_state(snapshot), engine.state("g-1"))
    schema = check_compatibility((Field("id", "string", False),), (Field("id", "string", False),))
    gate = evaluate_cutover(
        report,
        schema,
        lag_seconds=1,
        max_lag_seconds=30,
        pre_migration_checks_passed=True,
        rollback_generation_available=True,
    )
    assert gate.allowed
    engine.mark_ready("g-1")
    assert engine.activate("g-1", 0) == 1
    with pytest.raises(CompareAndSwapConflict):
        engine.activate("g-1", 0)
    engine.close()


def test_cutover_reports_all_failed_gates() -> None:
    report = reconcile("g", 10, {"t": {"1": {"v": 1}}}, {"t": {}})
    schema = check_compatibility((Field("id", "string", False),), ())
    result = evaluate_cutover(
        report,
        schema,
        lag_seconds=31,
        max_lag_seconds=30,
        pre_migration_checks_passed=False,
        rollback_generation_available=False,
    )
    assert not result.allowed
    assert len(result.failures) == 5
