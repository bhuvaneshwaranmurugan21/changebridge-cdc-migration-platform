from __future__ import annotations

from copy import deepcopy

import pytest

from scripts import validate_part1_preservation as preservation
from scripts import validate_part2_stage1 as validator


def _registry() -> dict[str, object]:
    return {
        "criteria": [
            {"id": f"ST21-AC-{number:02d}", "statement": "governed"} for number in range(1, 41)
        ]
    }


def _receipt() -> dict[str, object]:
    return {
        "criteria_total": 40,
        "criteria_passed": 36,
        "criteria_pending": 4,
        "result": "PENDING_EXTERNAL_CLOSURE",
        "criteria": [
            {
                "id": f"ST21-AC-{number:02d}",
                "result": "PASS" if number <= 36 else "PENDING",
                "evidence": ["evidence.json"],
            }
            for number in range(1, 41)
        ],
    }


def test_acceptance_registry_and_receipt_are_complete() -> None:
    validator.validate_acceptance(_registry(), _receipt())


@pytest.mark.parametrize("mutation", ["duplicate", "missing", "early_pass", "empty_evidence"])
def test_acceptance_mutations_fail_closed(mutation: str) -> None:
    registry = _registry()
    receipt = _receipt()
    if mutation == "duplicate":
        registry["criteria"][1]["id"] = "ST21-AC-01"  # type: ignore[index]
    elif mutation == "missing":
        receipt["criteria"].pop()  # type: ignore[union-attr]
    elif mutation == "early_pass":
        receipt["criteria"][36]["result"] = "PASS"  # type: ignore[index]
    else:
        receipt["criteria"][0]["evidence"] = []  # type: ignore[index]
    with pytest.raises(validator.Stage21Error):
        validator.validate_acceptance(registry, receipt)


def test_runtime_boundary_summary_is_accepted() -> None:
    run = {
        "capture_method": "postgres-logical-slot-exported-snapshot/1.0.0",
        "snapshot_imported": True,
        "cleanup": {"slot_dropped": True},
        "generation_transitions": ["CREATED", "SNAPSHOT_LOADING", "CDC_APPLYING"],
        "snapshot_frontier": {"kind": "postgres_lsn", "value": "0/FFFFFFF0"},
        "first_post_boundary_position": {"kind": "postgres_lsn", "value": "1/10"},
    }
    boundary = {
        "source_commit": validator.SOURCE_COMMIT,
        "source_tree": validator.SOURCE_TREE,
        "image": validator.IMAGE,
        "workflow_run_id": 36036471399,
        "runs": [
            run,
            {
                **deepcopy(run),
                "snapshot_frontier": {"kind": "postgres_lsn", "value": "1/20"},
                "first_post_boundary_position": {"kind": "postgres_lsn", "value": "1/30"},
            },
            {
                **deepcopy(run),
                "snapshot_frontier": {"kind": "postgres_lsn", "value": "1/40"},
                "first_post_boundary_position": {"kind": "postgres_lsn", "value": "1/50"},
            },
        ],
    }
    determinism = {
        "same_seed_equal": {"workload_id": True, "history_digest": True},
        "different_seed_differs": True,
    }
    validator.validate_runtime(boundary, determinism)


def test_nonadvancing_runtime_commit_fails_closed() -> None:
    run = {
        "capture_method": "postgres-logical-slot-exported-snapshot/1.0.0",
        "snapshot_imported": True,
        "cleanup": {"slot_dropped": True},
        "generation_transitions": ["CREATED", "SNAPSHOT_LOADING", "CDC_APPLYING"],
        "snapshot_frontier": {"kind": "postgres_lsn", "value": "1/20"},
        "first_post_boundary_position": {"kind": "postgres_lsn", "value": "1/20"},
    }
    boundary = {
        "source_commit": validator.SOURCE_COMMIT,
        "source_tree": validator.SOURCE_TREE,
        "image": validator.IMAGE,
        "workflow_run_id": 36036471399,
        "runs": [run, run, run],
    }
    with pytest.raises(validator.Stage21Error, match="CB21V023_NONADVANCING_COMMIT"):
        validator.validate_runtime(
            boundary,
            {"same_seed_equal": {"workload_id": True}, "different_seed_differs": True},
        )


def test_current_tree_preserves_part1_evidence() -> None:
    result = preservation.validate(validator.ROOT)
    assert result["result"] == "PASS"
    assert result["count"] == 8
