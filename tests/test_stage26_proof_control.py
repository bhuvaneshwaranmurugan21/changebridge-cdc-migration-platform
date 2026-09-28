from pathlib import Path

import pytest

from changebridge.contracts import semantic_digest
from changebridge.proof_control import ProofControlStore
from changebridge.proof_gates import REQUIRED_GATES, ProofGateError, gate_record


def gates(revision: int) -> list[dict[str, object]]:
    return [
        gate_record(
            gate,
            generation_id="g",
            frontier="0/2",
            schema_set_digest="s",
            input_revision=revision,
            input_digests=["d"],
            evidence_refs=["e"],
            producer="p",
            producer_version="1",
            limitations=["l"],
            invalidation_conditions=["i"],
        )
        for gate in REQUIRED_GATES
    ]


def test_state_machine_and_replay(tmp_path: Path) -> None:
    body = {"generation_id": "g", "frontier": "0/2"}
    seal = {**body, "seal_digest": semantic_digest(body, domain="stage26-generation-seal")}
    with ProofControlStore(tmp_path / "proof.db") as store:
        store.register_candidate("g", frontier="0/2", schema_set_digest="s")
        store.seal("g", seal)
        attempt = store.begin_proof("g")
        for gate in gates(attempt["input_revision"]):
            store.record_gate(attempt["attempt_id"], gate)
        first = store.seal_manifest(attempt["attempt_id"])
        second = store.seal_manifest(attempt["attempt_id"])
        assert first == second and store.generation("g")["state"] == "PROVEN"


def test_missing_gate_fails_closed(tmp_path: Path) -> None:
    body = {"generation_id": "g", "frontier": "0/2"}
    seal = {**body, "seal_digest": semantic_digest(body, domain="stage26-generation-seal")}
    with ProofControlStore(tmp_path / "proof.db") as store:
        store.register_candidate("g", frontier="0/2", schema_set_digest="s")
        store.seal("g", seal)
        attempt = store.begin_proof("g")
        for gate in gates(attempt["input_revision"])[:-1]:
            store.record_gate(attempt["attempt_id"], gate)
        with pytest.raises(ProofGateError, match="CB26G014_MISSING_GATE"):
            store.seal_manifest(attempt["attempt_id"])
