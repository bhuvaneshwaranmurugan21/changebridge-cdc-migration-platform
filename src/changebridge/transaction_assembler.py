"""Manifest-bound, deterministic CDC transaction assembly."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from typing import Any, NoReturn

from changebridge.cdc_ordering import admit_interval, normalize_lsn, ordered_events
from changebridge.contracts import semantic_digest


class TransactionAssemblyError(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


def _fail(code: str, detail: str) -> NoReturn:
    raise TransactionAssemblyError(code, detail)


def _event_projection(event: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: event[key]
        for key in (
            "generation_id",
            "run_id",
            "transaction_id",
            "transaction_sequence",
            "event_sequence",
            "event_id",
            "payload_digest",
            "operation",
            "source_table",
            "primary_key",
            "before",
            "after",
            "source_position",
            "source_contract_digest",
            "source_schema_digest",
        )
    }


def transaction_digest(events: list[dict[str, Any]], manifest_id: str) -> str:
    ordered = ordered_events(events)
    material = {
        "profile": "changebridge-stage24-transaction/1.0.0",
        "manifest_id": manifest_id,
        "events": [_event_projection(event) for event in ordered],
    }
    return semantic_digest(material, domain="stage24-transaction")


def build_apply_manifest(
    events: list[dict[str, Any]],
    *,
    generation_id: str,
    previous_frontier: str,
    terminal_frontier: str,
    source_history_digest: str,
    predecessor_manifest_digest: str,
) -> dict[str, Any]:
    admit_interval(events, previous_frontier, terminal_frontier)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in ordered_events(events):
        if event.get("generation_id") != generation_id:
            _fail("CB24A001_FOREIGN_GENERATION", str(event.get("generation_id")))
        grouped[str(event["transaction_id"])].append(event)
    descriptors: list[dict[str, Any]] = []
    for transaction_id, rows in sorted(
        grouped.items(), key=lambda item: (int(item[1][0]["transaction_sequence"]), item[0])
    ):
        sequences = [int(row["event_sequence"]) for row in rows]
        if sequences != list(range(1, len(rows) + 1)):
            _fail("CB24A002_NONCONTIGUOUS_EVENT_SEQUENCE", transaction_id)
        event_ids = [str(row["event_id"]) for row in rows]
        descriptors.append(
            {
                "transaction_id": transaction_id,
                "transaction_sequence": int(rows[0]["transaction_sequence"]),
                "commit_lsn": normalize_lsn(str(rows[-1]["source_position"]["value"])),
                "expected_event_count": len(rows),
                "ordered_event_ids": event_ids,
                "event_set_digest": semantic_digest(event_ids, domain="stage24-event-set"),
                "tables": sorted({str(row["source_table"]) for row in rows}),
            }
        )
    authority = {
        "contract_version": "changebridge-cdc-apply-manifest/1.0.0",
        "generation_id": generation_id,
        "previous_frontier": normalize_lsn(previous_frontier),
        "terminal_frontier": normalize_lsn(terminal_frontier),
        "source_history_digest": source_history_digest,
        "predecessor_manifest_digest": predecessor_manifest_digest,
        "canonicalization_profile": "changebridge-canonical-json/1.0.0",
        "transactions": descriptors,
    }
    return {
        **authority,
        "manifest_id": semantic_digest(authority, domain="stage24-apply-manifest"),
    }


def assemble_transactions(
    events: list[dict[str, Any]],
    manifest: Mapping[str, Any],
    *,
    admitted_schema_digests: set[str],
) -> list[dict[str, Any]]:
    generation_id = str(manifest.get("generation_id"))
    previous = str(manifest.get("previous_frontier"))
    terminal = str(manifest.get("terminal_frontier"))
    manifest_id = str(manifest.get("manifest_id"))
    admit_interval(events, previous, terminal)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in ordered_events(events):
        if event.get("generation_id") != generation_id:
            _fail("CB24A001_FOREIGN_GENERATION", str(event.get("generation_id")))
        if event.get("operation") not in {"insert", "update", "delete"}:
            _fail("CB24A003_OPERATION", str(event.get("operation")))
        if event.get("source_schema_digest") not in admitted_schema_digests:
            _fail("CB24A004_STAGE5_POLICY_REQUIRED", str(event.get("event_id")))
        before, after = event.get("before"), event.get("after")
        if event["operation"] == "insert" and (before is not None or not isinstance(after, dict)):
            _fail("CB24A005_IMAGE_SHAPE", str(event["event_id"]))
        if event["operation"] == "update" and not all(
            isinstance(value, dict) for value in (before, after)
        ):
            _fail("CB24A005_IMAGE_SHAPE", str(event["event_id"]))
        if event["operation"] == "delete" and (
            not isinstance(before, dict) or after is not None
        ):
            _fail("CB24A005_IMAGE_SHAPE", str(event["event_id"]))
        if event["operation"] == "update":
            if not isinstance(before, dict) or not isinstance(after, dict):
                _fail("CB24A005_IMAGE_SHAPE", str(event["event_id"]))
            keys = [str(row["name"]) for row in event["primary_key"]]
            if any(before.get(key) != after.get(key) for key in keys):
                _fail("CB24A004_STAGE5_POLICY_REQUIRED", str(event["event_id"]))
        grouped[str(event["transaction_id"])].append(event)
    descriptors = manifest.get("transactions")
    if not isinstance(descriptors, list):
        _fail("CB24A006_MANIFEST_SHAPE", "transactions")
    descriptor_map = {
        str(row.get("transaction_id")): row for row in descriptors if isinstance(row, Mapping)
    }
    if set(descriptor_map) != set(grouped):
        _fail("CB24A007_TRANSACTION_SET", repr(sorted(set(descriptor_map) ^ set(grouped))))
    plans: list[dict[str, Any]] = []
    for transaction_id, rows in grouped.items():
        rows = ordered_events(rows)
        descriptor = descriptor_map[transaction_id]
        if descriptor is None:
            _fail("CB24A006_MANIFEST_SHAPE", transaction_id)
        event_ids = [str(row["event_id"]) for row in rows]
        if (
            descriptor.get("expected_event_count") != len(rows)
            or descriptor.get("ordered_event_ids") != event_ids
            or descriptor.get("event_set_digest")
            != semantic_digest(event_ids, domain="stage24-event-set")
        ):
            _fail("CB24A008_INCOMPLETE_TRANSACTION", transaction_id)
        commit_lsn = normalize_lsn(str(rows[-1]["source_position"]["value"]))
        if descriptor.get("commit_lsn") != commit_lsn:
            _fail("CB24A009_COMMIT_LSN", transaction_id)
        tables = sorted({str(row["source_table"]) for row in rows})
        if descriptor.get("tables") != tables:
            _fail("CB24A010_TABLE_SET", transaction_id)
        plans.append(
            {
                "generation_id": generation_id,
                "transaction_id": transaction_id,
                "transaction_sequence": int(rows[0]["transaction_sequence"]),
                "commit_lsn": commit_lsn,
                "previous_frontier": previous,
                "terminal_frontier": terminal,
                "manifest_id": manifest_id,
                "events": rows,
                "tables": tables,
                "transaction_digest": transaction_digest(rows, manifest_id),
            }
        )
    return sorted(plans, key=lambda row: (row["transaction_sequence"], row["transaction_id"]))
