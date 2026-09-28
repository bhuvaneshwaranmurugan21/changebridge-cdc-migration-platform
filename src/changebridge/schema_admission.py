"""Stage 5 CDC admission wrapper; predecessor transaction assembly remains unchanged."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, NoReturn

from changebridge.contracts import semantic_digest
from changebridge.schema_control import SchemaControlStore
from changebridge.schema_policy import POLICY_DIGEST, SchemaDecision, assert_key_values_unchanged
from changebridge.transaction_assembler import assemble_transactions


class SchemaAdmissionError(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


def _fail(code: str, detail: str) -> NoReturn:
    raise SchemaAdmissionError(code, detail)


def assemble_policy_bound_transactions(
    events: list[dict[str, Any]],
    manifest: Mapping[str, Any],
    *,
    control: SchemaControlStore,
    decisions: Mapping[str, SchemaDecision],
) -> list[dict[str, Any]]:
    """Assemble only after exact Stage 5 decision and apply receipts are durable."""

    admissions: dict[str, dict[str, Any]] = {}
    for event in events:
        table = str(event.get("source_table"))
        decision = decisions.get(table)
        if decision is None or decision.verdict != "COMPATIBLE":
            _fail("CB25A001_SCHEMA_DECISION_REQUIRED", table)
        digest = str(event.get("source_schema_digest"))
        if digest != decision.candidate.digest:
            _fail("CB25A002_SCHEMA_DECISION_MISMATCH", str(event.get("event_id")))
        assert_key_values_unchanged(event, decision)
        admissions[table] = control.require_admission(
            generation_id=str(event.get("generation_id")),
            source_table=table,
            candidate_digest=digest,
            policy_digest=POLICY_DIGEST,
        )
    plans = assemble_transactions(
        events,
        manifest,
        admitted_schema_digests={decision.candidate.digest for decision in decisions.values()},
    )
    for plan in plans:
        plan["schema_admissions"] = {
            table: {
                "decision_id": decisions[table].decision_id,
                "decision_digest": decisions[table].decision_digest,
                "receipt_id": admissions[table]["receipt_id"],
                "apply_token": admissions[table]["apply_token"],
                "policy_digest": admissions[table]["policy_digest"],
            }
            for table in plan["tables"]
        }
        plan["schema_admission_digest"] = semantic_digest(
            plan["schema_admissions"], domain="stage25-schema-admissions"
        )
    return plans
