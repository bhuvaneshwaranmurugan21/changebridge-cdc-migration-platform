"""Strict local DMS/S3-shaped fixture normalization boundary.

The adapter is deliberately profile-driven and local.  It does not claim that
AWS DMS emitted, delivered, ordered, or recovered the synthetic fixture data.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from collections.abc import Iterable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn

import pyarrow.parquet as pq  # type: ignore[import-untyped]

from changebridge.contracts import (
    ContractError,
    canonical_bytes,
    classify_replay,
    compare_source_positions,
    event_id,
    event_order_key,
    event_payload_digest,
    semantic_digest,
    validate_cdc_event,
    validate_json_schema,
)

PROFILE_ID = "changebridge.synthetic-dms-s3.full-images"
PROFILE_VERSION = "1.0.0"
MANIFEST_VERSION = "raw-landing-manifest/1.0.0"
QUARANTINE_VERSION = "normalization-quarantine/1.0.0"
NORMALIZER_VERSION = "changebridge-manifest-normalizer/1.0.0"
SNAPSHOT_IDENTITY_VERSION = "snapshot-batch-identity/1.0.0"

REASON_CODES = frozenset(
    {
        "CBN001_UNKNOWN_PROFILE",
        "CBN002_UNKNOWN_FIELD",
        "CBN003_MANIFEST_PATH",
        "CBN004_OBJECT_MISSING",
        "CBN005_OBJECT_CHECKSUM",
        "CBN006_OBJECT_SIZE",
        "CBN007_ROW_COUNT",
        "CBN008_OBJECT_SEQUENCE",
        "CBN009_OBJECT_ID_CONFLICT",
        "CBN010_GENERATION_MISMATCH",
        "CBN011_RUN_MISMATCH",
        "CBN012_CONTRACT_MISMATCH",
        "CBN013_SCHEMA_MISMATCH",
        "CBN014_POSITION_MALFORMED",
        "CBN015_POSITION_BOUNDARY",
        "CBN016_TRANSACTION_METADATA",
        "CBN017_UNSUPPORTED_OPERATION",
        "CBN018_PRIMARY_KEY",
        "CBN019_IMAGE_COMBINATION",
        "CBN020_ORDER_KEY_CONFLICT",
        "CBN021_EVENT_PAYLOAD_CONFLICT",
        "CBN022_INTERVAL_GAP_OR_OVERLAP",
        "CBN023_SCALAR_LOSS",
        "CBN024_DUPLICATE_JSON_KEY",
        "CBN025_FORMAT_UNSUPPORTED",
        "CBN026_RECORD_DIGEST",
        "CBN027_UNEXPECTED_COLUMN",
        "CBN028_RECORD_TOO_LARGE",
        "CBN029_INVALID_TIMESTAMP",
    }
)

_RAW_FIELDS = frozenset(
    {
        "profile_id",
        "profile_version",
        "record_kind",
        "operation",
        "source_system",
        "source_database",
        "source_schema",
        "source_table",
        "source_contract_id",
        "source_contract_version",
        "source_contract_digest",
        "source_schema_version",
        "source_schema_digest",
        "primary_key",
        "before",
        "after",
        "transaction_id",
        "transaction_sequence",
        "event_sequence",
        "commit_lsn",
        "committed_at",
        "ingested_at",
        "run_id",
        "generation_id",
    }
)


class NormalizationError(ValueError):
    """Stable diagnostic for manifest and record failures."""

    def __init__(self, code: str, detail: str) -> None:
        if code not in REASON_CODES:
            raise ValueError(f"unregistered normalization code: {code}")
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


def fail(code: str, detail: str) -> NoReturn:
    raise NormalizationError(code, detail)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def strict_json_loads(data: str) -> Any:
    """Decode JSON without float coercion and reject duplicate object keys."""

    def object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                fail("CBN024_DUPLICATE_JSON_KEY", key)
            result[key] = value
        return result

    try:
        return json.loads(data, parse_float=Decimal, object_pairs_hook=object_pairs)
    except NormalizationError:
        raise
    except (json.JSONDecodeError, ValueError) as exc:
        fail("CBN023_SCALAR_LOSS", type(exc).__name__)


def _safe_object_path(root: Path, relative: str) -> Path:
    pure = PurePosixPath(relative)
    if pure.is_absolute() or not pure.parts or ".." in pure.parts or "\\" in relative:
        fail("CBN003_MANIFEST_PATH", relative)
    path = root.joinpath(*pure.parts)
    if path.is_symlink():
        fail("CBN003_MANIFEST_PATH", relative)
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        fail("CBN003_MANIFEST_PATH", relative)
    return path


def _validate_utc_timestamp(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.endswith("Z") or "T" not in value:
        fail("CBN029_INVALID_TIMESTAMP", field)
    return value


def _read_records(path: Path, fmt: str, max_record_bytes: int) -> list[dict[str, Any]]:
    if fmt == "jsonl":
        records: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if len(line.encode("utf-8")) > max_record_bytes:
                fail("CBN028_RECORD_TOO_LARGE", path.name)
            value = strict_json_loads(line)
            if not isinstance(value, dict):
                fail("CBN023_SCALAR_LOSS", "record is not an object")
            records.append(value)
        return records
    if fmt == "json":
        value = strict_json_loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
            fail("CBN023_SCALAR_LOSS", "JSON object set")
        return list(value)
    if fmt == "parquet":
        table = pq.read_table(path)
        if table.column_names != ["record_json", "record_sha256"]:
            fail("CBN027_UNEXPECTED_COLUMN", repr(table.column_names))
        rows: list[dict[str, Any]] = []
        for row in table.to_pylist():
            raw = row["record_json"]
            expected = row["record_sha256"]
            if not isinstance(raw, str) or not isinstance(expected, str):
                fail("CBN023_SCALAR_LOSS", "Parquet record columns")
            encoded = raw.encode("utf-8")
            if len(encoded) > max_record_bytes:
                fail("CBN028_RECORD_TOO_LARGE", path.name)
            if _sha256(encoded) != expected:
                fail("CBN026_RECORD_DIGEST", path.name)
            value = strict_json_loads(raw)
            if not isinstance(value, dict):
                fail("CBN023_SCALAR_LOSS", "Parquet record object")
            rows.append(value)
        return rows
    fail("CBN025_FORMAT_UNSUPPORTED", fmt)


def validate_manifest(
    root: Path,
    manifest: Mapping[str, Any],
    schema: Mapping[str, Any],
) -> list[tuple[Mapping[str, Any], Path]]:
    """Validate the whole immutable object set before reading record semantics."""

    try:
        validate_json_schema(manifest, schema, owner="raw-landing-manifest-v1")
    except ContractError as exc:
        fail("CBN023_SCALAR_LOSS", exc.detail)
    if manifest["manifest_version"] != MANIFEST_VERSION:
        fail("CBN023_SCALAR_LOSS", "manifest_version")
    if manifest["profile_id"] != PROFILE_ID or manifest["profile_version"] != PROFILE_VERSION:
        fail("CBN001_UNKNOWN_PROFILE", f"{manifest['profile_id']}:{manifest['profile_version']}")
    if manifest["start_exclusive_frontier"] != manifest["stage1_snapshot_frontier"]:
        fail("CBN022_INTERVAL_GAP_OR_OVERLAP", "manifest start does not equal S")
    if (
        compare_source_positions(
            manifest["start_exclusive_frontier"], manifest["object_end_frontier"]
        )
        >= 0
    ):
        fail("CBN022_INTERVAL_GAP_OR_OVERLAP", "nonadvancing interval")
    objects = manifest["objects"]
    sequences = [item["object_sequence"] for item in objects]
    if sequences != list(range(1, len(objects) + 1)):
        fail("CBN008_OBJECT_SEQUENCE", repr(sequences))
    seen: dict[str, str] = {}
    verified: list[tuple[Mapping[str, Any], Path]] = []
    prior_end = manifest["start_exclusive_frontier"]
    for item in objects:
        object_id = item["object_id"]
        prior = seen.get(object_id)
        if prior is not None and prior != item["sha256"]:
            fail("CBN009_OBJECT_ID_CONFLICT", object_id)
        if prior is not None:
            fail("CBN008_OBJECT_SEQUENCE", f"duplicate object {object_id}")
        seen[object_id] = item["sha256"]
        if item["start_exclusive_frontier"] != prior_end:
            fail("CBN022_INTERVAL_GAP_OR_OVERLAP", object_id)
        try:
            if (
                compare_source_positions(
                    item["start_exclusive_frontier"], item["end_inclusive_frontier"]
                )
                >= 0
            ):
                fail("CBN022_INTERVAL_GAP_OR_OVERLAP", object_id)
        except ContractError as exc:
            fail("CBN014_POSITION_MALFORMED", exc.detail)
        prior_end = item["end_inclusive_frontier"]
        path = _safe_object_path(root, item["path"])
        if not path.is_file():
            fail("CBN004_OBJECT_MISSING", item["path"])
        raw = path.read_bytes()
        if len(raw) != item["byte_length"]:
            fail("CBN006_OBJECT_SIZE", object_id)
        if _sha256(raw) != item["sha256"]:
            fail("CBN005_OBJECT_CHECKSUM", object_id)
        verified.append((item, path))
    if prior_end != manifest["object_end_frontier"]:
        fail("CBN022_INTERVAL_GAP_OR_OVERLAP", "terminal object frontier")
    expected_set = sorted(item["path"] for item in objects)
    if expected_set != sorted(manifest["declared_object_paths"]):
        fail("CBN008_OBJECT_SEQUENCE", "unmanifested or missing declared object")
    return verified


def _quarantine(
    manifest: Mapping[str, Any],
    object_entry: Mapping[str, Any],
    locator: str,
    raw_digest: str,
    error: NormalizationError,
) -> dict[str, Any]:
    material = {
        "contract_version": QUARANTINE_VERSION,
        "profile_id": manifest["profile_id"],
        "profile_version": manifest["profile_version"],
        "manifest_id": manifest["manifest_id"],
        "object_id": object_entry["object_id"],
        "record_locator": locator,
        "raw_record_digest": raw_digest,
        "run_id": manifest["run_id"],
        "generation_id": manifest["generation_id"],
        "reason_code": error.code,
        "diagnostic_context": error.detail[:160],
        "normalizer_version": NORMALIZER_VERSION,
        "first_observed_at": manifest["observed_at"],
    }
    identity = {key: value for key, value in material.items() if key != "diagnostic_context"}
    return {
        **material,
        "quarantine_id": semantic_digest(identity, domain="normalization-quarantine-identity"),
        "quarantine_digest": semantic_digest(material, domain="normalization-quarantine-record"),
    }


def normalize_record(
    raw: Mapping[str, Any],
    manifest: Mapping[str, Any],
    source_contracts: Mapping[tuple[str, str], tuple[str, Mapping[str, Any]]],
    envelope_schema: Mapping[str, Any],
) -> dict[str, Any]:
    unknown = set(raw) - _RAW_FIELDS
    missing = _RAW_FIELDS - set(raw)
    if unknown:
        fail("CBN002_UNKNOWN_FIELD", sorted(unknown)[0])
    if missing:
        fail("CBN016_TRANSACTION_METADATA", sorted(missing)[0])
    if raw["profile_id"] != PROFILE_ID or raw["profile_version"] != PROFILE_VERSION:
        fail("CBN001_UNKNOWN_PROFILE", str(raw.get("profile_version")))
    if raw["generation_id"] != manifest["generation_id"]:
        fail("CBN010_GENERATION_MISMATCH", str(raw["generation_id"]))
    if raw["run_id"] != manifest["run_id"]:
        fail("CBN011_RUN_MISMATCH", str(raw["run_id"]))
    contract_key = (str(raw["source_contract_id"]), str(raw["source_contract_version"]))
    authority = source_contracts.get(contract_key)
    if authority is None or raw["source_contract_digest"] != authority[0]:
        fail("CBN012_CONTRACT_MISMATCH", repr(contract_key))
    if raw["source_schema_digest"] != authority[0]:
        fail("CBN013_SCHEMA_MISMATCH", str(raw["source_schema_digest"]))
    operation = raw["operation"]
    if operation not in {"snapshot", "insert", "update", "delete"}:
        fail("CBN017_UNSUPPORTED_OPERATION", str(operation))
    if not isinstance(raw["primary_key"], list) or not raw["primary_key"]:
        fail("CBN018_PRIMARY_KEY", "missing")
    before, after = raw["before"], raw["after"]
    if operation in {"snapshot", "insert"} and (before is not None or after is None):
        fail("CBN019_IMAGE_COMBINATION", str(operation))
    if operation == "update" and (before is None or after is None):
        fail("CBN019_IMAGE_COMBINATION", str(operation))
    if operation == "delete" and (before is None or after is not None):
        fail("CBN019_IMAGE_COMBINATION", str(operation))
    if operation != "delete":
        try:
            validate_json_schema(after, authority[1], owner=str(raw["source_contract_id"]))
        except ContractError as exc:
            fail("CBN013_SCHEMA_MISMATCH", exc.detail)
    if before is not None:
        try:
            validate_json_schema(before, authority[1], owner=str(raw["source_contract_id"]))
        except ContractError as exc:
            fail("CBN013_SCHEMA_MISMATCH", exc.detail)
    record_kind = raw["record_kind"]
    if record_kind not in {"snapshot", "cdc"} or (record_kind == "snapshot") != (
        operation == "snapshot"
    ):
        fail("CBN017_UNSUPPORTED_OPERATION", f"{record_kind}:{operation}")
    transaction_id = raw["transaction_id"]
    if not isinstance(transaction_id, str) or not transaction_id:
        fail("CBN016_TRANSACTION_METADATA", "transaction_id")
    if operation == "snapshot" and not transaction_id.startswith("snapshot-batch:"):
        fail("CBN016_TRANSACTION_METADATA", "snapshot batch identity")
    if operation != "snapshot" and transaction_id.startswith("snapshot-batch:"):
        fail("CBN016_TRANSACTION_METADATA", "CDC source transaction identity")
    if not isinstance(raw["transaction_sequence"], int) or not isinstance(
        raw["event_sequence"], int
    ):
        fail("CBN016_TRANSACTION_METADATA", "sequence")
    position = {"kind": "postgres_lsn", "value": raw["commit_lsn"]}
    try:
        lower = compare_source_positions(position, manifest["stage1_snapshot_frontier"])
        upper = compare_source_positions(position, manifest["object_end_frontier"])
    except ContractError as exc:
        fail("CBN014_POSITION_MALFORMED", exc.detail)
    if operation == "snapshot":
        if lower != 0:
            fail("CBN015_POSITION_BOUNDARY", "snapshot position must equal S")
    elif lower <= 0 or upper > 0:
        fail("CBN015_POSITION_BOUNDARY", str(raw["commit_lsn"]))
    committed_at = _validate_utc_timestamp(raw["committed_at"], "committed_at")
    ingested_at = _validate_utc_timestamp(raw["ingested_at"], "ingested_at")
    event: dict[str, Any] = {
        "contract_version": "1.0.0",
        "source_system": raw["source_system"],
        "source_database": raw["source_database"],
        "source_schema": raw["source_schema"],
        "source_table": raw["source_table"],
        "source_contract_id": raw["source_contract_id"],
        "source_contract_version": raw["source_contract_version"],
        "source_contract_digest": raw["source_contract_digest"],
        "operation": operation,
        "primary_key": deepcopy(raw["primary_key"]),
        "before": deepcopy(before),
        "after": deepcopy(after),
        "transaction_id": transaction_id,
        "source_position": position,
        "transaction_sequence": raw["transaction_sequence"],
        "event_sequence": raw["event_sequence"],
        "committed_at": committed_at,
        "ingested_at": ingested_at,
        "source_schema_version": raw["source_schema_version"],
        "source_schema_digest": raw["source_schema_digest"],
        "event_id": "0" * 64,
        "payload_digest": "0" * 64,
        "run_id": raw["run_id"],
        "generation_id": raw["generation_id"],
        "transport_capabilities": {
            "before_images": "full",
            "transaction_boundaries": True,
            "source_order": True,
        },
        "quarantine_reason": None,
    }
    event["event_id"] = event_id(event)
    event["payload_digest"] = event_payload_digest(event)
    try:
        validate_cdc_event(event, envelope_schema)
    except ContractError as exc:
        fail("CBN023_SCALAR_LOSS", exc.detail)
    return event


@dataclass(frozen=True)
class NormalizationBundle:
    canonical: tuple[dict[str, Any], ...]
    quarantine: tuple[dict[str, Any], ...]
    report: dict[str, Any]


def normalize_manifest(
    root: Path,
    manifest: Mapping[str, Any],
    *,
    manifest_schema: Mapping[str, Any],
    envelope_schema: Mapping[str, Any],
    source_contracts: Mapping[tuple[str, str], tuple[str, Mapping[str, Any]]],
) -> NormalizationBundle:
    verified = validate_manifest(root, manifest, manifest_schema)
    accepted_by_id: dict[str, dict[str, Any]] = {}
    order_payload: dict[tuple[Any, ...], str] = {}
    quarantined: list[dict[str, Any]] = []
    duplicate_count = 0
    raw_count = 0
    for object_entry, path in verified:
        records = _read_records(path, object_entry["format"], manifest["max_record_bytes"])
        if len(records) != object_entry["row_count"]:
            fail("CBN007_ROW_COUNT", str(object_entry["object_id"]))
        for index, raw in enumerate(records, 1):
            raw_count += 1
            raw_digest = semantic_digest(raw, domain="raw-transport-record")
            locator = f"row:{index}"
            try:
                event = normalize_record(raw, manifest, source_contracts, envelope_schema)
                prior = accepted_by_id.get(event["event_id"])
                if prior is not None:
                    classification = classify_replay(prior, event)
                    if classification == "duplicate":
                        duplicate_count += 1
                        continue
                    fail("CBN021_EVENT_PAYLOAD_CONFLICT", event["event_id"])
                key = event_order_key(event)
                prior_payload = order_payload.get(key)
                if prior_payload is not None and prior_payload != event["payload_digest"]:
                    fail("CBN020_ORDER_KEY_CONFLICT", repr(key))
                order_payload[key] = event["payload_digest"]
                accepted_by_id[event["event_id"]] = event
            except NormalizationError as exc:
                quarantined.append(_quarantine(manifest, object_entry, locator, raw_digest, exc))
    canonical = sorted(accepted_by_id.values(), key=event_order_key)
    quarantined.sort(key=lambda row: (row["object_id"], row["record_locator"], row["reason_code"]))
    canonical_digest = semantic_digest(canonical, domain="normalized-canonical-set")
    quarantine_digest = semantic_digest(quarantined, domain="normalized-quarantine-set")
    report_material = {
        "contract_version": "normalization-report/1.0.0",
        "normalizer_version": NORMALIZER_VERSION,
        "manifest_id": manifest["manifest_id"],
        "run_id": manifest["run_id"],
        "generation_id": manifest["generation_id"],
        "profile_id": manifest["profile_id"],
        "profile_version": manifest["profile_version"],
        "raw_record_count": raw_count,
        "accepted_count": len(canonical),
        "quarantined_count": len(quarantined),
        "duplicate_count": duplicate_count,
        "canonical_digest": canonical_digest,
        "quarantine_digest": quarantine_digest,
        "result": "PASS" if not quarantined else "QUARANTINED",
        "limitations": [
            "Synthetic local contract fixtures; no AWS DMS or S3 execution is claimed.",
            (
                "No target apply, checkpoint, reconciliation, performance, or production "
                "claim is established."
            ),
        ],
    }
    report = {
        **report_material,
        "report_digest": semantic_digest(report_material, domain="normalization-report"),
    }
    return NormalizationBundle(tuple(canonical), tuple(quarantined), report)


def _render_json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def write_bundle_atomic(output: Path, bundle: NormalizationBundle) -> None:
    """Publish a complete bundle by one directory rename; never leave partial success."""

    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    try:
        (temporary / "canonical.json").write_bytes(_render_json(list(bundle.canonical)))
        (temporary / "quarantine.json").write_bytes(_render_json(list(bundle.quarantine)))
        (temporary / "report.json").write_bytes(_render_json(bundle.report))
        os.replace(temporary, output)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def generation_replay_key(event: Mapping[str, Any]) -> tuple[str, str]:
    """Event identity is transport-neutral; replay partitioning is generation-scoped."""

    return str(event["generation_id"]), str(event["event_id"])


def canonical_event_bytes(event: Mapping[str, Any]) -> bytes:
    return canonical_bytes(event, domain="canonical-cdc-envelope")


def records_semantically_equal(
    left: Iterable[Mapping[str, Any]], right: Iterable[Mapping[str, Any]]
) -> bool:
    return [canonical_event_bytes(item) for item in left] == [
        canonical_event_bytes(item) for item in right
    ]
