"""Executable bounded predicates for the sixteen ChangeBridge invariants."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from changebridge.contracts import REQUIRED_PROOF_GATES, compare_source_positions

Oracle = Callable[[Mapping[str, Any]], bool]


def _boundary(case: Mapping[str, Any]) -> bool:
    snapshot = case["snapshot_frontier"]
    terminal = case["terminal_frontier"]
    positions = case["cdc_positions"]
    return all(
        compare_source_positions(snapshot, item) < 0
        and compare_source_positions(item, terminal) <= 0
        for item in positions
    )


def _continuity(case: Mapping[str, Any]) -> bool:
    intervals = case["intervals"]
    return bool(intervals) and all(
        intervals[index][1] == intervals[index + 1][0] for index in range(len(intervals) - 1)
    )


def _order(case: Mapping[str, Any]) -> bool:
    keys = [tuple(item) for item in case["order_keys"]]
    return keys == sorted(keys) and len(keys) == len(set(keys))


def _idempotency(case: Mapping[str, Any]) -> bool:
    return bool(case["before_digest"] == case["after_replay_digest"])


def _conflict_detection(case: Mapping[str, Any]) -> bool:
    return not case["same_identity_different_payload_applied"]


def _checkpoint_coupling(case: Mapping[str, Any]) -> bool:
    return bool(
        case["checkpoint_frontier"] <= case["durable_target_frontier"]
        and case["target_commit_receipt_matches"]
    )


def _failure_atomicity(case: Mapping[str, Any]) -> bool:
    return case["visible_before"] == case["visible_after_failure"] or (
        case["recovered"] and not case["double_applied"]
    )


def _delete_correctness(case: Mapping[str, Any]) -> bool:
    return bool(
        case["deleted_row_absent"]
        and case["tombstone_present"]
        and case["reconciliation_includes_delete"]
    )


def _schema_safety(case: Mapping[str, Any]) -> bool:
    return not case["incompatible_reached_active"] and case["incompatible_quarantined"]


def _generation_isolation(case: Mapping[str, Any]) -> bool:
    return bool(case["attempted_generation"] != case["active_generation"] or case["write_rejected"])


def _proof_before_publication(case: Mapping[str, Any]) -> bool:
    gates = case["gates"]
    return (
        set(gates) == set(REQUIRED_PROOF_GATES)
        and all(gate["verdict"] == "PASS" for gate in gates.values())
        and len({gate["boundary_digest"] for gate in gates.values()}) == 1
        and len({gate["input_revision"] for gate in gates.values()}) == 1
    )


def _single_publisher_cas(case: Mapping[str, Any]) -> bool:
    return bool(case["success_count"] <= 1 and case["expected_revision_enforced"])


def _stale_writer_rejection(case: Mapping[str, Any]) -> bool:
    return not case["stale_write_applied"] and case["pointer_unchanged"]


def _replay_determinism(case: Mapping[str, Any]) -> bool:
    return bool(
        case["logical_digest_first"] == case["logical_digest_second"]
        and case["proof_digest_first"] == case["proof_digest_second"]
    )


def _rollback_safety(case: Mapping[str, Any]) -> bool:
    return all(
        case[key]
        for key in ("target_proven", "target_retained", "target_readable", "decision_auditable")
    )


def _evidence_binding(case: Mapping[str, Any]) -> bool:
    return all(
        case[key]
        for key in (
            "artifact_digests_verified",
            "commit_verified",
            "run_verified",
            "references_resolve",
        )
    )


ORACLES: dict[str, Oracle] = {
    "boundary": _boundary,
    "continuity": _continuity,
    "order": _order,
    "idempotency": _idempotency,
    "conflict_detection": _conflict_detection,
    "checkpoint_coupling": _checkpoint_coupling,
    "failure_atomicity": _failure_atomicity,
    "delete_correctness": _delete_correctness,
    "schema_safety": _schema_safety,
    "generation_isolation": _generation_isolation,
    "proof_before_publication": _proof_before_publication,
    "single_publisher_cas": _single_publisher_cas,
    "stale_writer_rejection": _stale_writer_rejection,
    "replay_determinism": _replay_determinism,
    "rollback_safety": _rollback_safety,
    "evidence_binding": _evidence_binding,
}


def evaluate(invariant_id: str, case: Mapping[str, Any]) -> bool:
    try:
        oracle = ORACLES[invariant_id]
    except KeyError as exc:
        raise ValueError(f"CBORC001_UNKNOWN_INVARIANT: {invariant_id}") from exc
    return oracle(case)
