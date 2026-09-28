"""Stage 5 coordinator: decide, quarantine/reject, or apply and receipt."""

from __future__ import annotations

import os
from typing import Any

from changebridge.iceberg_schema import IcebergSchemaAdapter
from changebridge.schema_control import SchemaControlStore
from changebridge.schema_policy import ContractIdentity, SchemaPolicy


class SchemaMigrationCoordinator:
    def __init__(
        self,
        *,
        policy: SchemaPolicy,
        control: SchemaControlStore,
        iceberg: IcebergSchemaAdapter,
    ) -> None:
        self.policy = policy
        self.control = control
        self.iceberg = iceberg

    def execute(
        self,
        *,
        generation_id: str,
        source_table: str,
        previous: ContractIdentity,
        candidate: ContractIdentity,
        frontier: str,
        expected_generation_revision: int | None = None,
        policy_digest: str | None = None,
        fault: str | None = None,
    ) -> dict[str, Any]:
        arguments: dict[str, Any] = {
            "generation_id": generation_id,
            "source_table": source_table,
            "previous": previous,
            "candidate": candidate,
        }
        if policy_digest is not None:
            arguments["policy_digest"] = policy_digest
        decision = self.policy.decide(**arguments)
        self.control.record_decision(decision)
        before = self.iceberg.metadata()
        if decision.verdict != "COMPATIBLE":
            quarantine = self.control.open_quarantine(
                decision,
                frontier=frontier,
                target_metadata_location=str(before["metadata_location"]),
            )
            if fault == "after_quarantine_before_rejection":
                raise RuntimeError("CB25F001_INJECTED_AFTER_QUARANTINE")
            rejection: dict[str, Any] | None = None
            if decision.verdict == "INCOMPATIBLE":
                if expected_generation_revision is None:
                    raise RuntimeError("CB25M001_EXPECTED_GENERATION_REVISION_REQUIRED")
                rejection = self.control.reject_generation(
                    decision,
                    quarantine_id=str(quarantine["quarantine_id"]),
                    expected_revision=expected_generation_revision,
                )
            after = self.iceberg.metadata()
            if after["metadata_location"] != before["metadata_location"]:
                raise RuntimeError("CB25M002_QUARANTINE_MUTATED_TARGET")
            return {
                "decision": decision.record(),
                "quarantine": quarantine,
                "rejection": rejection,
                "target_unchanged": True,
            }
        applied = self.iceberg.apply(decision)
        if fault == "process_exit_after_schema_commit":
            os._exit(88)
        receipt = self.control.record_apply_receipt(
            {
                "receipt_id": f"schema-receipt-{applied['apply_token'][:24]}",
                "apply_token": applied["apply_token"],
                "generation_id": generation_id,
                "source_table": source_table,
                "decision_id": decision.decision_id,
                "candidate_digest": candidate.digest,
                "policy_digest": decision.policy_digest,
                "iceberg_schema_id": applied["schema_id"],
                "metadata_location": applied["metadata_location"],
                "recovered": int(bool(applied["recovered"])),
            }
        )
        return {
            "decision": decision.record(),
            "apply": applied,
            "receipt": receipt,
            "rows": self.iceberg.logical_rows(),
        }
