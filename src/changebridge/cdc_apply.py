"""Stage 4 deterministic apply, receipt recovery, and checkpoint coordinator."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any, NoReturn

from changebridge.cdc_control import CDCControlStore
from changebridge.generation_registry import GenerationRegistry
from changebridge.iceberg_cdc import IcebergCDCAdapter, IcebergCDCError


class CDCApplyError(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


def _fail(code: str, detail: str) -> NoReturn:
    raise CDCApplyError(code, detail)


class CDCApplyCoordinator:
    def __init__(
        self,
        *,
        registry: GenerationRegistry,
        control: CDCControlStore,
        iceberg: IcebergCDCAdapter,
    ) -> None:
        self.registry = registry
        self.control = control
        self.iceberg = iceberg

    def apply_transaction(
        self, plan: Mapping[str, Any], *, fault: str | None = None
    ) -> dict[str, Any]:
        generation_id = str(plan["generation_id"])
        transaction_id = str(plan["transaction_id"])
        generation = self.registry.get_generation(generation_id)
        if generation is None or generation["state"] != "CDC_APPLYING":
            _fail("CB24P001_GENERATION_NOT_CDC_APPLYING", generation_id)
        checkpoint = self.control.initialize_checkpoint(
            generation_id, str(plan["previous_frontier"])
        )
        claimed = self.control.claim(plan)
        if claimed["state"] == "CHECKPOINTED":
            return {
                "transaction_id": transaction_id,
                "idempotent_replay": True,
                "receipts": self.control.receipts(generation_id, transaction_id),
                "checkpoint": self.control.checkpoint(generation_id),
            }
        table_tokens: dict[str, str] = {}
        grouped = {
            table: [event for event in plan["events"] if event["source_table"] == table]
            for table in plan["tables"]
        }
        for table in sorted(grouped):
            events = grouped[table]
            table_digest = self.iceberg.table_input_digest(events)
            token = self.iceberg.commit_token(
                generation_id, transaction_id, table, table_digest
            )
            table_tokens[table] = token
            receipt = self.control.receipt(generation_id, transaction_id, table)
            if receipt is not None:
                if (
                    receipt["commit_token"] != token
                    or receipt["table_input_digest"] != table_digest
                ):
                    _fail("CB24P002_RECEIPT_MISMATCH", table)
                continue
            committed = self.iceberg.snapshot_for_token(table, token)
            if committed is not None:
                summary = committed["summary"]
                if (
                    summary.get("changebridge_transaction_digest")
                    != plan["transaction_digest"]
                    or summary.get("changebridge_table_input_digest") != table_digest
                ):
                    _fail("CB24P003_RECOVERY_CONFLICT", table)
                logical_digest = self.iceberg.verify_table(table)["state_digest"]
                recovered = True
            else:
                committed = self.iceberg.apply_table(
                    generation_id=generation_id,
                    transaction_id=transaction_id,
                    transaction_digest=str(plan["transaction_digest"]),
                    source_table=table,
                    events=events,
                    manifest_id=str(plan["manifest_id"]),
                    source_frontier=str(plan["commit_lsn"]),
                )
                logical_digest = committed["logical_digest"]
                recovered = bool(committed["recovered"])
            if fault == f"process_exit_after_table_commit:{table}":
                os._exit(87)
            self.control.record_receipt(
                {
                    "generation_id": generation_id,
                    "transaction_id": transaction_id,
                    "source_table": table,
                    "transaction_digest": str(plan["transaction_digest"]),
                    "table_input_digest": table_digest,
                    "commit_token": token,
                    "physical_snapshot_id": committed["snapshot_id"],
                    "logical_digest": logical_digest,
                    "recovered": recovered,
                }
            )
        if fault == "after_all_commits_before_finalize":
            raise IcebergCDCError("CB24I010_INJECTED_BEFORE_FINALIZE", transaction_id)
        self.control.record_tombstones(plan, table_tokens)
        finalized = self.control.finalize(plan, expected_revision=int(checkpoint["revision"]))
        return {
            "transaction_id": transaction_id,
            "idempotent_replay": bool(finalized["idempotent"]),
            "receipts": self.control.receipts(generation_id, transaction_id),
            "checkpoint": finalized["checkpoint"],
        }
