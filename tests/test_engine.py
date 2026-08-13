from __future__ import annotations

import pytest

from changebridge.engine import ChangeBridgeEngine, FrontierGap, ReplayConflict
from changebridge.model import CdcBatch, CdcTransaction
from changebridge.simulator import fixture


@pytest.fixture
def engine() -> ChangeBridgeEngine:
    instance = ChangeBridgeEngine()
    yield instance
    instance.close()


def test_snapshot_batch_and_replay(engine: ChangeBridgeEngine) -> None:
    snapshot, batch = fixture()
    engine.create_generation("g-1", 100, "v1")
    engine.load_snapshot("g-1", snapshot)
    assert engine.apply_batch("g-1", batch) == "applied"
    assert engine.apply_batch("g-1", batch) == "replayed"
    assert engine.get_generation("g-1").current_lsn == 130
    assert engine.state("g-1")["customers"]["c-001"]["tier"] == "gold"


def test_frontier_gap_is_rejected(engine: ChangeBridgeEngine) -> None:
    snapshot, _ = fixture()
    engine.create_generation("g-1", 100, "v1")
    engine.load_snapshot("g-1", snapshot)
    with pytest.raises(FrontierGap, match="expected start LSN"):
        engine.apply_batch("g-1", CdcBatch("gap", 101, 110, ()))


def test_transaction_conflict_rolls_back_batch(engine: ChangeBridgeEngine) -> None:
    snapshot, batch = fixture()
    engine.create_generation("g-1", 100, "v1")
    engine.load_snapshot("g-1", snapshot)
    engine.apply_batch("g-1", batch)
    changed = CdcTransaction("tx-110", 131, "later", ())
    with pytest.raises(ReplayConflict):
        engine.apply_batch("g-1", CdcBatch("new", 130, 131, (changed,)))
    assert engine.get_generation("g-1").current_lsn == 130


def test_injected_crash_does_not_advance_frontier(engine: ChangeBridgeEngine) -> None:
    snapshot, batch = fixture()
    engine.create_generation("g-1", 100, "v1")
    engine.load_snapshot("g-1", snapshot)
    with pytest.raises(RuntimeError, match="injected crash"):
        engine.apply_batch("g-1", batch, fail_before_commit=True)
    assert engine.get_generation("g-1").current_lsn == 100
    assert engine.state("g-1") == snapshot
