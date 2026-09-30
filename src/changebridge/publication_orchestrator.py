"""Restartable Stage 7 orchestration that never overrides component verdicts."""

from __future__ import annotations

from typing import Any

from changebridge.consumer import ConsumerResolver, TableReader
from changebridge.publication import AmbiguousPublication, PublicationStore


class PublicationOrchestrator:
    def __init__(self, store: PublicationStore) -> None:
        self.store = store
        self.resolver = ConsumerResolver(store)

    def publish_and_verify(
        self,
        *,
        run_id: str,
        product_id: str,
        generation_id: str,
        expected_revision: int,
        attempt_id: str,
        authorization: str,
        pin_id: str,
        read_table: TableReader,
        lose_acknowledgement: bool = False,
    ) -> dict[str, Any]:
        run = self.store.start_run(run_id, product_id)
        if run["state"] == "PLANNED":
            run = self.store.transition_run(
                run_id,
                expected_revision=int(run["revision"]),
                to_state="ELIGIBLE",
                attempt_id=None,
                detail={"generation_id": generation_id},
            )
        if run["state"] == "ELIGIBLE":
            run = self.store.transition_run(
                run_id,
                expected_revision=int(run["revision"]),
                to_state="PUBLISHING",
                attempt_id=attempt_id,
                detail={"expected_revision": expected_revision},
            )
        try:
            receipt = self.store.publish(
                product_id=product_id,
                generation_id=generation_id,
                expected_revision=expected_revision,
                attempt_id=attempt_id,
                authorization=authorization,
                lose_acknowledgement=lose_acknowledgement,
            )
        except AmbiguousPublication:
            receipt = self.store.reconcile_attempt(attempt_id)
        run = self.store.run(run_id)
        if run["state"] == "PUBLISHING":
            run = self.store.transition_run(
                run_id,
                expected_revision=int(run["revision"]),
                to_state="VERIFYING",
                attempt_id=attempt_id,
                detail=receipt,
            )
        try:
            verification = self.resolver.resolve_and_verify(
                product_id, pin_id=pin_id, read_table=read_table
            )
        except Exception as exc:
            run = self.store.run(run_id)
            if run["state"] == "VERIFYING":
                self.store.transition_run(
                    run_id,
                    expected_revision=int(run["revision"]),
                    to_state="INCIDENT",
                    attempt_id=attempt_id,
                    detail={"error": str(exc)},
                )
            raise
        run = self.store.run(run_id)
        if run["state"] == "VERIFYING":
            self.store.transition_run(
                run_id,
                expected_revision=int(run["revision"]),
                to_state="ACTIVE",
                attempt_id=attempt_id,
                detail={
                    "consumer_verification_digest": verification[
                        "consumer_verification_digest"
                    ]
                },
            )
        return {"publication": receipt, "consumer": verification, "run": self.store.run(run_id)}

    def fallback(
        self,
        *,
        run_id: str,
        product_id: str,
        expected_revision: int,
        attempt_id: str,
        authorization: str,
        lose_acknowledgement: bool = False,
    ) -> dict[str, Any]:
        run = self.store.run(run_id)
        if run["state"] == "ACTIVE":
            # A bounded fallback drill deliberately opens an incident before recovery.
            run = self.store.transition_run(
                run_id,
                expected_revision=int(run["revision"]),
                to_state="INCIDENT",
                attempt_id=attempt_id,
                detail={"reason": "AUTHORIZED_FIRST_PUBLICATION_FALLBACK_DRILL"},
            )
        if run["state"] == "INCIDENT":
            run = self.store.transition_run(
                run_id,
                expected_revision=int(run["revision"]),
                to_state="RECOVERING",
                attempt_id=attempt_id,
                detail={"authorization": authorization},
            )
        try:
            receipt = self.store.first_publication_fallback(
                product_id=product_id,
                expected_revision=expected_revision,
                attempt_id=attempt_id,
                authorization=authorization,
                lose_acknowledgement=lose_acknowledgement,
            )
        except AmbiguousPublication:
            receipt = self.store.reconcile_attempt(attempt_id)
        source = self.resolver.resolve_and_verify(
            product_id,
            pin_id=f"{attempt_id}:source-pin",
            read_table=lambda _table, _binding: {},
        )
        run = self.store.run(run_id)
        if run["state"] == "RECOVERING":
            self.store.transition_run(
                run_id,
                expected_revision=int(run["revision"]),
                to_state="SOURCE_FALLBACK_VERIFIED",
                attempt_id=attempt_id,
                detail=receipt,
            )
        return {"fallback": receipt, "consumer": source, "run": self.store.run(run_id)}
