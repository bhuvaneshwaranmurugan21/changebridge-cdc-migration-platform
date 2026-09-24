"""Pure Stage 4 contract, canonicalization, and publication reference oracles.

This module is intentionally disconnected from runtime adapters.  It makes the
accepted architecture decidable without implying managed-service proof.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import unicodedata
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, NoReturn

from jsonschema import Draft202012Validator, FormatChecker  # type: ignore[import-untyped]

CANONICALIZATION_VERSION = "changebridge-canonical-json/1.0.0"
REQUIRED_PROOF_GATES = (
    "continuity",
    "deletes",
    "evidence_integrity",
    "lag",
    "pre_migration",
    "reconciliation",
    "rollback_readiness",
    "schema",
)
SOURCE_POSITION_KINDS = {"integer", "mysql_binlog", "oracle_scn", "postgres_lsn"}
_HEX_LSN = re.compile(r"^(?P<high>[0-9A-F]{1,8})/(?P<low>[0-9A-F]{1,8})$")
_BINLOG = re.compile(r"^(?P<file>[A-Za-z0-9_.-]+):(?P<offset>[0-9]+)$")


class ContractError(ValueError):
    """Stable, fail-closed contract diagnostic."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


def fail(code: str, detail: str) -> NoReturn:
    raise ContractError(code, detail)


def _decimal_text(value: Decimal) -> str:
    if not value.is_finite():
        fail("CBCAN004_NONFINITE_DECIMAL", str(value))
    normalized = value.normalize()
    rendered = format(normalized, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return "0" if rendered in {"-0", ""} else rendered


def _timestamp_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        fail("CBCAN005_NAIVE_TIMESTAMP", value.isoformat())
    utc = value.astimezone(UTC)
    rendered = utc.isoformat(timespec="microseconds")
    return rendered.replace("+00:00", "Z")


def canonical_value(value: Any) -> Any:
    """Normalize supported semantic values; reject lossy identity material."""

    if value is None or isinstance(value, bool | int):
        return value
    if isinstance(value, float):
        fail("CBCAN003_FLOAT_FORBIDDEN", repr(value))
    if isinstance(value, Decimal):
        return {"$decimal": _decimal_text(value)}
    if isinstance(value, datetime):
        return {"$timestamp": _timestamp_text(value)}
    if isinstance(value, bytes):
        encoded = base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")
        return {"$binary_base64url": encoded}
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, child in value.items():
            if not isinstance(key, str):
                fail("CBCAN002_NONSTRING_KEY", repr(key))
            normalized_key = unicodedata.normalize("NFC", key)
            if normalized_key in result:
                fail("CBCAN007_NORMALIZED_KEY_COLLISION", normalized_key)
            result[normalized_key] = canonical_value(child)
        return result
    if isinstance(value, Sequence):
        return [canonical_value(child) for child in value]
    fail("CBCAN001_UNSUPPORTED_TYPE", type(value).__name__)


def canonical_bytes(value: Any, *, domain: str) -> bytes:
    """Return domain-separated UTF-8 canonical JSON bytes."""

    normalized_domain = unicodedata.normalize("NFC", domain)
    if not normalized_domain or "\n" in normalized_domain:
        fail("CBCAN006_INVALID_DOMAIN", domain)
    body = json.dumps(
        canonical_value(value),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    ).encode("utf-8")
    return f"{CANONICALIZATION_VERSION}\n{normalized_domain}\n".encode() + body


def semantic_digest(value: Any, *, domain: str) -> str:
    return hashlib.sha256(canonical_bytes(value, domain=domain)).hexdigest()


def schema_digest(schema: Mapping[str, Any]) -> str:
    return semantic_digest(schema, domain="contract-schema")


def source_position_key(position: Mapping[str, Any]) -> tuple[str, tuple[int | str, ...]]:
    """Parse a position into a comparable key; unlike kinds are incomparable."""

    if set(position) != {"kind", "value"}:
        fail("CBPOS001_INVALID_SHAPE", repr(sorted(position)))
    kind = position["kind"]
    value = position["value"]
    if kind not in SOURCE_POSITION_KINDS or not isinstance(value, str) or not value:
        fail("CBPOS002_UNKNOWN_OR_EMPTY", repr(position))
    try:
        if kind in {"integer", "oracle_scn"}:
            if not value.isdigit():
                raise ValueError
            parsed: tuple[int | str, ...] = (int(value),)
        elif kind == "postgres_lsn":
            match = _HEX_LSN.fullmatch(value)
            if match is None:
                raise ValueError
            parsed = (int(match["high"], 16), int(match["low"], 16))
        else:
            match = _BINLOG.fullmatch(value)
            if match is None:
                raise ValueError
            parsed = (match["file"], int(match["offset"]))
    except ValueError:
        fail("CBPOS003_MALFORMED_VALUE", f"{kind}:{value}")
    return str(kind), parsed


def compare_source_positions(left: Mapping[str, Any], right: Mapping[str, Any]) -> int:
    left_kind, left_key = source_position_key(left)
    right_kind, right_key = source_position_key(right)
    if left_kind != right_kind:
        fail("CBPOS004_INCOMPARABLE_KINDS", f"{left_kind}!={right_kind}")
    return (left_key > right_key) - (left_key < right_key)


def event_order_key(event: Mapping[str, Any]) -> tuple[Any, ...]:
    kind, position = source_position_key(event["source_position"])
    return (
        kind,
        *position,
        event["transaction_sequence"],
        event["event_sequence"],
        event["event_id"],
    )


def _event_identity_material(event: Mapping[str, Any]) -> dict[str, Any]:
    fields = (
        "source_system",
        "source_database",
        "source_schema",
        "source_table",
        "source_position",
        "transaction_id",
        "transaction_sequence",
        "event_sequence",
        "primary_key",
        "operation",
    )
    return {field: event[field] for field in fields}


def _event_payload_material(event: Mapping[str, Any]) -> dict[str, Any]:
    excluded = {"event_id", "payload_digest", "ingested_at", "quarantine_reason"}
    return {key: value for key, value in event.items() if key not in excluded}


def event_id(event: Mapping[str, Any]) -> str:
    return semantic_digest(_event_identity_material(event), domain="cdc-event-identity")


def event_payload_digest(event: Mapping[str, Any]) -> str:
    return semantic_digest(_event_payload_material(event), domain="cdc-event-payload")


def validate_json_schema(instance: Any, schema: Mapping[str, Any], *, owner: str) -> None:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(instance), key=lambda item: list(item.absolute_path))
    if errors:
        error = errors[0]
        location = ".".join(str(part) for part in error.absolute_path) or "$"
        fail("CBCON001_SCHEMA_REJECTED", f"{owner}:{location}:{error.validator}")


def validate_cdc_event(event: Mapping[str, Any], schema: Mapping[str, Any]) -> None:
    validate_json_schema(event, schema, owner="cdc-envelope-v1")
    source_position_key(event["source_position"])
    operation = event["operation"]
    before = event.get("before")
    after = event.get("after")
    if operation in {"snapshot", "insert"} and (before is not None or after is None):
        fail("CBEVT002_INVALID_IMAGE_COMBINATION", operation)
    if operation == "update" and (before is None or after is None):
        fail("CBEVT002_INVALID_IMAGE_COMBINATION", operation)
    if operation == "delete" and (before is None or after is not None):
        fail("CBEVT002_INVALID_IMAGE_COMBINATION", operation)
    if event["source_contract_digest"] != event["source_schema_digest"]:
        fail("CBEVT005_SCHEMA_IDENTITY_MISMATCH", event["source_contract_id"])
    if event["event_id"] != event_id(event):
        fail("CBEVT003_EVENT_ID_MISMATCH", event["event_id"])
    if event["payload_digest"] != event_payload_digest(event):
        fail("CBEVT004_PAYLOAD_DIGEST_MISMATCH", event["payload_digest"])


def classify_replay(first: Mapping[str, Any], second: Mapping[str, Any]) -> str:
    if first["event_id"] != second["event_id"]:
        return "distinct"
    if first["payload_digest"] == second["payload_digest"]:
        return "duplicate"
    return "conflict"


def validate_proof_manifest(manifest: Mapping[str, Any]) -> None:
    gates = manifest.get("gates")
    if not isinstance(gates, list):
        fail("CBPRF001_GATE_SET_INVALID", "gates must be a list")
    identities: list[str] = []
    for gate in gates:
        if not isinstance(gate, Mapping) or not isinstance(gate.get("gate_id"), str):
            fail("CBPRF001_GATE_SET_INVALID", "gate identity must be a string")
        identities.append(gate["gate_id"])
    if len(identities) != len(set(identities)):
        fail("CBPRF002_DUPLICATE_GATE", repr(identities))
    if tuple(sorted(identities)) != REQUIRED_PROOF_GATES:
        fail("CBPRF001_GATE_SET_INVALID", repr(sorted(identities)))
    boundary = (
        manifest.get("generation_id"),
        manifest.get("frontier"),
        manifest.get("schema_set_digest"),
    )
    for gate in gates:
        if gate.get("verdict") != "PASS":
            fail("CBPRF003_GATE_NOT_PASSING", str(gate.get("gate_id")))
        gate_boundary = (
            gate.get("generation_id"),
            gate.get("frontier"),
            gate.get("schema_set_digest"),
        )
        if gate_boundary != boundary:
            fail("CBPRF004_CROSS_BOUNDARY_GATE", str(gate.get("gate_id")))
        if gate.get("input_revision") != manifest.get("input_revision"):
            fail("CBPRF005_STALE_GATE", str(gate.get("gate_id")))


def publication_verdict(candidate: Mapping[str, Any]) -> tuple[bool, str]:
    """Apply the complete publication eligibility conjunction."""

    checks = (
        (candidate.get("generation_state") == "PROVEN", "CBPUB001_GENERATION_NOT_PROVEN"),
        (candidate.get("proof_state") == "SEALED", "CBPUB002_PROOF_NOT_SEALED"),
        (candidate.get("proof_valid") is True, "CBPUB003_PROOF_INVALID"),
        (candidate.get("table_map_complete") is True, "CBPUB004_TABLE_MAP_INCOMPLETE"),
        (
            candidate.get("expected_revision") == candidate.get("current_revision"),
            "CBPUB005_STALE_REVISION",
        ),
        (
            candidate.get("generation_id") == candidate.get("proof_generation_id"),
            "CBPUB006_GENERATION_MISMATCH",
        ),
    )
    for passed, diagnostic in checks:
        if not passed:
            return False, diagnostic
    return True, "CBPUB000_ELIGIBLE"


def validate_control_record(record: Mapping[str, Any], schema: Mapping[str, Any]) -> None:
    """Validate one control record structurally and enforce its local semantics."""

    record_type = record.get("record_type")
    definitions = schema.get("$defs", {})
    if record_type not in definitions or record_type in {
        "artifact",
        "base",
        "digest",
        "generation_base",
        "position",
        "sha",
    }:
        fail("CBCTL001_UNKNOWN_RECORD_TYPE", str(record_type))
    wrapper = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$ref": f"#/$defs/{record_type}",
        "$defs": definitions,
    }
    validate_json_schema(record, wrapper, owner=str(record_type))
    if record_type == "frontier_checkpoint":
        if compare_source_positions(record["previous_frontier"], record["current_frontier"]) >= 0:
            fail("CBCTL002_CHECKPOINT_REGRESSION", str(record["record_id"]))
        if record["expected_revision"] != record["revision"] - 1:
            fail("CBCTL003_CHECKPOINT_REVISION_MISMATCH", str(record["record_id"]))
    elif record_type == "schema_contract":
        unsafe = record["compatibility_verdict"] in {"INCOMPATIBLE", "UNKNOWN"}
        if unsafe != record["quarantine_required"]:
            fail("CBCTL004_SCHEMA_QUARANTINE_MISMATCH", str(record["record_id"]))
    elif record_type == "reconciliation_run":
        passing = (
            record["mismatch_count"] == 0 and record["source_digest"] == record["candidate_digest"]
        )
        if passing != (record["verdict"] == "PASS"):
            fail("CBCTL005_RECONCILIATION_VERDICT_MISMATCH", str(record["record_id"]))
    elif record_type == "proof_manifest":
        validate_proof_manifest(record)
        if record["state"] != "SEALED":
            fail("CBCTL006_PROOF_NOT_SEALED", str(record["record_id"]))
    elif record_type == "publication_event":
        if record["verdict"] == "PUBLISHED":
            if record["new_revision"] != record["expected_revision"] + 1:
                fail("CBCTL007_PUBLICATION_REVISION_MISMATCH", str(record["record_id"]))
            if record["diagnostic"] != "CBPUB000_ELIGIBLE":
                fail("CBCTL008_PUBLICATION_DIAGNOSTIC_MISMATCH", str(record["record_id"]))
    elif record_type == "rollback_event":
        if record["new_revision"] != record["prior_revision"] + 1:
            fail("CBCTL009_ROLLBACK_REVISION_MISMATCH", str(record["record_id"]))
    elif record_type == "stage_receipt":
        if record["criteria_passed"] + record["criteria_pending"] != record["criteria_total"]:
            fail("CBCTL010_RECEIPT_COUNT_MISMATCH", str(record["record_id"]))
        expected = "PASS" if record["criteria_pending"] == 0 else "PENDING"
        if record["result"] != expected:
            fail("CBCTL011_RECEIPT_RESULT_MISMATCH", str(record["record_id"]))
        criteria = record.get("criteria")
        if criteria is not None:
            expected_ids = {f"ST4-AC-{index:02d}" for index in range(1, 41)}
            ids = [item.get("id") for item in criteria]
            if len(ids) != record["criteria_total"] or set(ids) != expected_ids:
                fail("CBCTL012_RECEIPT_CRITERIA_MISMATCH", str(record["record_id"]))


def verify_artifact_manifest(root: Path, manifest: Mapping[str, Any]) -> None:
    for artifact in manifest.get("artifacts", []):
        relative = Path(artifact["path"])
        if relative.is_absolute() or ".." in relative.parts:
            fail("CBEVD001_UNSAFE_ARTIFACT_PATH", str(relative))
        path = root / relative
        if not path.is_file():
            fail("CBEVD002_MISSING_ARTIFACT", str(relative))
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != artifact["sha256"]:
            fail("CBEVD003_ARTIFACT_DIGEST_MISMATCH", str(relative))
