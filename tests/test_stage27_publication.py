from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from changebridge.consumer import ConsumerResolver
from changebridge.contracts import semantic_digest
from changebridge.proof_gates import REQUIRED_GATES, gate_record
from changebridge.publication import (
    AmbiguousPublication,
    PublicationError,
    PublicationStore,
    publication_binding_manifest,
)
from changebridge.publication_orchestrator import PublicationOrchestrator


def proof(generation: str, seal: str) -> dict[str, Any]:
    gates = [
        gate_record(
            gate,
            generation_id=generation,
            frontier="0/194FE20",
            schema_set_digest="schema",
            input_revision=1,
            input_digests=[seal, "logical-reconciliation"],
            evidence_refs=["evidence"],
            producer="stage27-test",
            producer_version="1",
            limitations=["local"],
            invalidation_conditions=["input-change"],
        )
        for gate in REQUIRED_GATES
    ]
    body = {
        "record_type": "proof_manifest",
        "contract_version": "2.0.0",
        "protocol": "changebridge-frontier-proof/2.0.0",
        "generation_id": generation,
        "frontier": {"kind": "postgres_lsn", "value": "0/194FE20"},
        "schema_set_digest": "schema",
        "input_revision": 1,
        "seal_digest": seal,
        "state": "SEALED",
        "gates": gates,
    }
    return {**body, "proof_manifest_digest": semantic_digest(body, domain="stage26-proof-manifest")}


def binding(generation: str = "generation-g") -> dict[str, Any]:
    accepted, execution = proof(generation, "accepted-seal"), proof(generation, "execution-seal")
    return publication_binding_manifest(
        accepted_manifest=accepted,
        execution_manifest=execution,
        table_map={
            "order_items": {
                "identifier": "catalog.ns.order_items",
                "snapshot_id": "11",
                "manifest_list_digest": "a",
                "row_count": 66,
            },
            "orders": {
                "identifier": "catalog.ns.orders",
                "snapshot_id": "12",
                "manifest_list_digest": "b",
                "row_count": 6,
            },
        },
        accepted_reconciliation_digest="logical-reconciliation",
        execution_reconciliation_digest="logical-reconciliation",
    )


def reader(table: str, expected: dict[str, Any]) -> dict[str, Any]:
    return {
        "table": table,
        "snapshot_id": expected["snapshot_id"],
        "row_count": expected["row_count"],
        "representative_key": "key-1",
    }


def setup(path: Path, generation: str = "generation-g") -> PublicationStore:
    store = PublicationStore(path)
    store.initialize_product("orders-product")
    store.register_generation(binding(generation), consumer_contract="orders-reader/1.1.0")
    return store


def test_binding_rejects_logical_or_identity_drift() -> None:
    accepted = proof("generation-g", "accepted")
    execution = proof("generation-other", "execution")
    with pytest.raises(PublicationError, match="CB27B001_PREDECESSOR_MISMATCH"):
        publication_binding_manifest(
            accepted_manifest=accepted,
            execution_manifest=execution,
            table_map={},
            accepted_reconciliation_digest="a",
            execution_reconciliation_digest="b",
        )


def test_publish_pin_fallback_and_aba_rejection(tmp_path: Path) -> None:
    with setup(tmp_path / "control.db") as store:
        receipt = store.publish(
            product_id="orders-product",
            generation_id="generation-g",
            expected_revision=0,
            attempt_id="publish-1",
            authorization="approved",
        )
        assert receipt["resulting_revision"] == 1
        pin = ConsumerResolver(store).resolve_and_verify(
            "orders-product", pin_id="long-reader", read_table=reader
        )
        assert pin["revision"] == 1 and pin["verification"].endswith("VERIFIED")
        fallback = store.first_publication_fallback(
            product_id="orders-product",
            expected_revision=1,
            attempt_id="fallback-1",
            authorization="incident-approval",
        )
        assert fallback["resulting_revision"] == 2
        assert store.current("orders-product") == {
            "product_id": "orders-product",
            "revision": 2,
            "route": "SOURCE_FALLBACK",
            "pointer": None,
        }
        assert pin["generation_id"] == "generation-g"
        with pytest.raises(PublicationError, match="CB27P007_STALE_REVISION"):
            store.publish(
                product_id="orders-product",
                generation_id="generation-g",
                expected_revision=0,
                attempt_id="stale-after-fallback",
                authorization="stale",
            )


def test_attempt_replay_conflict_and_ambiguous_reconciliation(tmp_path: Path) -> None:
    with setup(tmp_path / "control.db") as store:
        with pytest.raises(AmbiguousPublication, match="CB27P008_ACK_AMBIGUOUS"):
            store.publish(
                product_id="orders-product",
                generation_id="generation-g",
                expected_revision=0,
                attempt_id="publish-ambiguous",
                authorization="approved",
                lose_acknowledgement=True,
            )
        receipt = store.reconcile_attempt("publish-ambiguous")
        assert receipt["verdict"] == "PUBLISHED"
        assert store.current("orders-product")["revision"] == 1
        assert (
            store.publish(
                product_id="orders-product",
                generation_id="generation-g",
                expected_revision=0,
                attempt_id="publish-ambiguous",
                authorization="approved",
            )
            == receipt
        )
        with pytest.raises(PublicationError, match="CB27P005_ATTEMPT_REPLAY_CONFLICT"):
            store.publish(
                product_id="orders-product",
                generation_id="generation-g",
                expected_revision=0,
                attempt_id="publish-ambiguous",
                authorization="changed",
            )


def test_consumer_snapshot_mismatch_fails_after_pointer_write(tmp_path: Path) -> None:
    with setup(tmp_path / "control.db") as store:
        store.publish(
            product_id="orders-product",
            generation_id="generation-g",
            expected_revision=0,
            attempt_id="publish-1",
            authorization="approved",
        )
        with pytest.raises(PublicationError, match="CB27C005_SNAPSHOT_MISMATCH"):
            ConsumerResolver(store).resolve_and_verify(
                "orders-product",
                pin_id="bad-reader",
                read_table=lambda table, expected: {
                    "table": table,
                    "snapshot_id": "wrong",
                    "row_count": expected["row_count"],
                },
            )
        assert store.current("orders-product")["revision"] == 1


def test_ordinary_rollback_requires_eligible_prior_publication(tmp_path: Path) -> None:
    with setup(tmp_path / "control.db", "generation-a") as store:
        store.register_generation(binding("generation-b"), consumer_contract="orders-reader/1.1.0")
        store.publish(
            product_id="orders-product",
            generation_id="generation-a",
            expected_revision=0,
            attempt_id="publish-a",
            authorization="approved",
        )
        store.publish(
            product_id="orders-product",
            generation_id="generation-b",
            expected_revision=1,
            attempt_id="publish-b",
            authorization="approved",
        )
        receipt = store.rollback(
            product_id="orders-product",
            target_generation_id="generation-a",
            expected_revision=2,
            attempt_id="rollback-a",
            authorization="incident-42",
        )
        assert receipt["verdict"] == "ROLLBACK_VERIFIED"
        assert store.current("orders-product")["pointer"]["generation_id"] == "generation-a"

        store.set_eligibility("generation-b", readable=False)
        with pytest.raises(PublicationError, match="CB27P006_GENERATION_INELIGIBLE"):
            store.rollback(
                product_id="orders-product",
                target_generation_id="generation-b",
                expected_revision=3,
                attempt_id="rollback-ineligible",
                authorization="incident-43",
            )


def test_orchestration_recovers_ack_loss_and_performs_explicit_fallback(tmp_path: Path) -> None:
    with setup(tmp_path / "control.db") as store:
        orchestrator = PublicationOrchestrator(store)
        result = orchestrator.publish_and_verify(
            run_id="run-1",
            product_id="orders-product",
            generation_id="generation-g",
            expected_revision=0,
            attempt_id="publish-1",
            authorization="approved",
            pin_id="consumer-1",
            read_table=reader,
            lose_acknowledgement=True,
        )
        assert result["run"]["state"] == "ACTIVE"
        fallback = orchestrator.fallback(
            run_id="run-1",
            product_id="orders-product",
            expected_revision=1,
            attempt_id="fallback-1",
            authorization="explicit-incident-approval",
            lose_acknowledgement=True,
        )
        assert fallback["run"]["state"] == "SOURCE_FALLBACK_VERIFIED"
        assert fallback["consumer"]["route"] == "SOURCE_FALLBACK"


def test_binding_digest_detects_mutation(tmp_path: Path) -> None:
    value = binding()
    value = copy.deepcopy(value)
    value["table_map"]["orders"]["row_count"] = 7
    with (
        PublicationStore(tmp_path / "control.db") as store,
        pytest.raises(PublicationError, match="CB27B005_BINDING_DIGEST"),
    ):
        store.register_generation(value, consumer_contract="orders-reader/1.1.0")
