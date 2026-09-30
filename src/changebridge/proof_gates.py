"""Fail-closed Stage 6 gate records and proof-manifest assembly."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, NoReturn

from changebridge.contracts import semantic_digest

REQUIRED_GATES = (
    "continuity",
    "schema",
    "deletes",
    "reconciliation",
    "lag",
    "pre_migration",
    "rollback_readiness",
    "evidence_integrity",
)


class ProofGateError(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        self.code, self.detail = code, detail
        super().__init__(f"{code}: {detail}")


def _fail(code: str, detail: str) -> NoReturn:
    raise ProofGateError(code, detail)


def gate_record(
    gate_id: str,
    *,
    generation_id: str,
    frontier: str,
    schema_set_digest: str,
    input_revision: int,
    input_digests: Sequence[str],
    evidence_refs: Sequence[str],
    producer: str,
    producer_version: str,
    limitations: Sequence[str],
    invalidation_conditions: Sequence[str],
    verdict: str = "PASS",
) -> dict[str, Any]:
    body = {
        "record_type": "gate_result",
        "contract_version": "2.0.0",
        "gate_id": gate_id,
        "generation_id": generation_id,
        "frontier": {"kind": "postgres_lsn", "value": frontier},
        "schema_set_digest": schema_set_digest,
        "input_revision": input_revision,
        "input_digests": sorted(set(input_digests)),
        "evidence_refs": sorted(set(evidence_refs)),
        "producer": producer,
        "producer_version": producer_version,
        "verdict": verdict,
        "limitations": list(limitations),
        "invalidation_conditions": list(invalidation_conditions),
    }
    validate_gate(body)
    return {**body, "gate_digest": semantic_digest(body, domain="stage26-gate-result")}


def validate_gate(gate: Mapping[str, Any]) -> None:
    gate_id = gate.get("gate_id")
    if gate_id not in REQUIRED_GATES:
        _fail("CB26G001_UNKNOWN_GATE", str(gate_id))
    if gate.get("verdict") not in {"PASS", "FAIL"}:
        _fail("CB26G005_VERDICT_INVALID", str(gate_id))
    frontier = gate.get("frontier")
    if (
        not isinstance(frontier, Mapping)
        or frontier.get("kind") != "postgres_lsn"
        or not frontier.get("value")
    ):
        _fail("CB26G003_FRONTIER_INVALID", str(gate_id))
    for field in ("generation_id", "schema_set_digest", "producer", "producer_version"):
        if not isinstance(gate.get(field), str) or not gate[field]:
            _fail("CB26G002_UNBOUND_GATE", str(gate_id))
    if not isinstance(gate.get("input_revision"), int) or gate["input_revision"] < 0:
        _fail("CB26G006_REVISION_INVALID", str(gate_id))
    for field in ("input_digests", "evidence_refs", "limitations", "invalidation_conditions"):
        value = gate.get(field)
        if not isinstance(value, Sequence) or isinstance(value, str) or not value:
            _fail("CB26G004_EVIDENCE_INCOMPLETE", f"{gate_id}:{field}")
    if gate.get("gate_digest") is not None:
        body = {key: value for key, value in gate.items() if key != "gate_digest"}
        if gate["gate_digest"] != semantic_digest(body, domain="stage26-gate-result"):
            _fail("CB26G015_GATE_DIGEST_MISMATCH", str(gate_id))


def validate_bootstrap_policy(receipt: Mapping[str, Any]) -> None:
    expected = {
        "policy": "FIRST_PUBLICATION_SOURCE_FALLBACK",
        "active_pointer_before_publication": None,
        "source_authoritative": True,
        "publication_stage": 7,
        "rollback_target": "ABSENT_ACTIVE_POINTER",
        "represents_prior_published_generation": False,
    }
    if any(receipt.get(key) != value for key, value in expected.items()):
        _fail("CB26G007_BOOTSTRAP_POLICY_INVALID", repr(receipt))
    if not receipt.get("evidence_refs"):
        _fail("CB26G004_EVIDENCE_INCOMPLETE", "rollback_readiness:evidence_refs")


def assemble_manifest(
    gates: Sequence[Mapping[str, Any]],
    *,
    generation_id: str,
    frontier: str,
    schema_set_digest: str,
    input_revision: int,
    seal_digest: str,
) -> dict[str, Any]:
    by_id: dict[str, Mapping[str, Any]] = {}
    for gate in gates:
        validate_gate(gate)
        gate_id = str(gate["gate_id"])
        if gate_id in by_id:
            _fail("CB26G008_DUPLICATE_GATE", gate_id)
        if gate["generation_id"] != generation_id:
            _fail("CB26G009_GENERATION_MISMATCH", gate_id)
        if gate["frontier"]["value"] != frontier:
            _fail("CB26G010_FRONTIER_MISMATCH", gate_id)
        if gate["schema_set_digest"] != schema_set_digest:
            _fail("CB26G011_SCHEMA_MISMATCH", gate_id)
        if gate["input_revision"] != input_revision:
            _fail("CB26G012_STALE_GATE", gate_id)
        if gate["verdict"] != "PASS":
            _fail("CB26G013_FAILED_GATE", gate_id)
        by_id[gate_id] = gate
    missing = [gate for gate in REQUIRED_GATES if gate not in by_id]
    if missing:
        _fail("CB26G014_MISSING_GATE", ",".join(missing))
    body = {
        "record_type": "proof_manifest",
        "contract_version": "2.0.0",
        "protocol": "changebridge-frontier-proof/2.0.0",
        "generation_id": generation_id,
        "frontier": {"kind": "postgres_lsn", "value": frontier},
        "schema_set_digest": schema_set_digest,
        "input_revision": input_revision,
        "seal_digest": seal_digest,
        "state": "SEALED",
        "gates": [dict(by_id[gate]) for gate in REQUIRED_GATES],
    }
    return {**body, "proof_manifest_digest": semantic_digest(body, domain="stage26-proof-manifest")}
