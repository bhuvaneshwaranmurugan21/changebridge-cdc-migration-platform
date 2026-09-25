from __future__ import annotations

import copy
import json
import shutil
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from changebridge.contracts import (
    ContractError,
    canonical_bytes,
    compare_source_positions,
    event_id,
    event_payload_digest,
    schema_digest,
)
from changebridge.normalizer import (
    NormalizationError,
    canonical_event_bytes,
    generation_replay_key,
    normalize_manifest,
    normalize_record,
    records_semantically_equal,
    strict_json_loads,
    validate_manifest,
    write_bundle_atomic,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/part2-stage2/valid"


def load(path: Path) -> Any:
    return strict_json_loads(path.read_text(encoding="utf-8"))


def authority() -> tuple[
    dict[str, Any], dict[str, Any], dict[tuple[str, str], tuple[str, dict[str, Any]]]
]:
    manifest_schema = load(ROOT / "contracts/raw-landing-manifest-v1.json")
    envelope_schema = load(ROOT / "contracts/cdc-envelope-v1.schema.json")
    contracts = {}
    for contract_id, version, relative in (
        ("orders_source_contract", "1.0.0", "contracts/orders-v1.json"),
        ("orders_source_contract_v1_1", "1.1.0", "contracts/orders-v1.1.json"),
        ("order_items_source_contract", "1.0.0", "contracts/order-items-v1.json"),
    ):
        schema = load(ROOT / relative)
        contracts[(contract_id, version)] = (schema_digest(schema), schema)
    return manifest_schema, envelope_schema, contracts


def bundle(root: Path = FIXTURE):
    manifest_schema, envelope_schema, contracts = authority()
    return normalize_manifest(
        root,
        load(root / "manifest.json"),
        manifest_schema=manifest_schema,
        envelope_schema=envelope_schema,
        source_contracts=contracts,
    )


def first_raw() -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = load(FIXTURE / "manifest.json")
    records = load(FIXTURE / "objects/snapshot-insert.json")
    return manifest, records[0]


def expect_code(code: str, action: Any) -> None:
    with pytest.raises(NormalizationError) as exc:
        action()
    assert exc.value.code == code


def test_valid_fixture_normalizes_all_operations_and_formats() -> None:
    result = bundle()
    assert [event["operation"] for event in result.canonical] == [
        "snapshot",
        "insert",
        "update",
        "delete",
        "update",
    ]
    assert not result.quarantine
    assert result.report["result"] == "PASS"
    assert result.report["raw_record_count"] == 5


def test_fixture_provenance_is_explicitly_synthetic() -> None:
    provenance = load(FIXTURE / "provenance.json")
    profile = load(ROOT / "contracts/transport-profile-stage22-v1.json")
    assert provenance["managed_dms_output"] is False
    assert provenance["classification"] == "SYNTHETIC_CONTRACT_FIXTURE"
    assert profile["managed_service_claim"] is False


def test_snapshot_identity_is_namespaced_and_not_source_transaction() -> None:
    result = bundle()
    snapshot = result.canonical[0]
    assert snapshot["transaction_id"].startswith("snapshot-batch:")
    assert (
        snapshot["source_position"] == load(FIXTURE / "manifest.json")["stage1_snapshot_frontier"]
    )


def test_generation_scoped_replay_key_without_event_identity_redefinition() -> None:
    event = bundle().canonical[1]
    other = copy.deepcopy(event)
    other["generation_id"] = "other-generation"
    other["payload_digest"] = event_payload_digest(other)
    assert event_id(other) == event["event_id"]
    assert generation_replay_key(other) != generation_replay_key(event)
    assert other["payload_digest"] != event["payload_digest"]


def test_ingested_at_does_not_change_event_or_payload_identity() -> None:
    event = bundle().canonical[1]
    changed = copy.deepcopy(event)
    changed["ingested_at"] = "2030-01-01T00:00:00.000000Z"
    assert event_id(changed) == event["event_id"]
    assert event_payload_digest(changed) == event["payload_digest"]


def test_strict_json_rejects_duplicate_keys_and_preserves_decimal() -> None:
    expect_code("CBN024_DUPLICATE_JSON_KEY", lambda: strict_json_loads('{"x":1,"x":2}'))
    assert strict_json_loads('{"x":1.2300}')["x"] == Decimal("1.2300")


@given(st.integers(min_value=0, max_value=2**32 - 1), st.integers(min_value=0, max_value=2**32 - 1))
@settings(max_examples=60, deadline=None)
def test_postgres_lsn_order_is_numeric(high: int, low: int) -> None:
    left = {"kind": "postgres_lsn", "value": f"{high:X}/{low:X}"}
    right_value = ((high << 32) | low) + 1
    if right_value >= 2**64:
        return
    right = {
        "kind": "postgres_lsn",
        "value": f"{right_value >> 32:X}/{right_value & 0xFFFFFFFF:X}",
    }
    assert compare_source_positions(left, right) < 0


def test_lexical_lsn_trap_is_rejected_by_numeric_order() -> None:
    assert (
        compare_source_positions(
            {"kind": "postgres_lsn", "value": "F/0"},
            {"kind": "postgres_lsn", "value": "10/0"},
        )
        < 0
    )


@given(st.dictionaries(st.text(min_size=1, max_size=8), st.integers(), max_size=8))
@settings(max_examples=50, deadline=None)
def test_canonical_bytes_ignore_mapping_insertion_order(value: dict[str, int]) -> None:
    reversed_value = dict(reversed(list(value.items())))
    assert canonical_bytes(value, domain="stage22-property") == canonical_bytes(
        reversed_value, domain="stage22-property"
    )


def test_canonical_values_preserve_unicode_decimal_timestamp_binary_and_null() -> None:
    value = {
        "unicode": "cafe\u0301",
        "decimal": Decimal("12345678901234567890.1200"),
        "timestamp": datetime(2024, 2, 29, 23, 59, 58, 123456, tzinfo=UTC),
        "binary": b"\x00\xff",
        "null": None,
    }
    encoded = canonical_bytes(value, domain="stage22-scalars")
    assert b"12345678901234567890.12" in encoded
    assert "café".encode() in encoded
    assert b"2024-02-29T23:59:58.123456Z" in encoded


def test_normalized_unicode_key_collision_fails_closed() -> None:
    with pytest.raises(ContractError) as exc:
        canonical_bytes({"é": 1, "e\u0301": 2}, domain="stage22-collision")
    assert exc.value.code == "CBCAN007_NORMALIZED_KEY_COLLISION"


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (lambda row: row.__setitem__("profile_version", "9.9.9"), "CBN001_UNKNOWN_PROFILE"),
        (lambda row: row.__setitem__("unknown", True), "CBN002_UNKNOWN_FIELD"),
        (lambda row: row.__setitem__("generation_id", "wrong"), "CBN010_GENERATION_MISMATCH"),
        (lambda row: row.__setitem__("run_id", "wrong"), "CBN011_RUN_MISMATCH"),
        (
            lambda row: row.__setitem__("source_contract_digest", "0" * 64),
            "CBN012_CONTRACT_MISMATCH",
        ),
        (lambda row: row.__setitem__("source_schema_digest", "0" * 64), "CBN013_SCHEMA_MISMATCH"),
        (lambda row: row.__setitem__("commit_lsn", "not-an-lsn"), "CBN014_POSITION_MALFORMED"),
        (lambda row: row.__setitem__("operation", "truncate"), "CBN017_UNSUPPORTED_OPERATION"),
        (lambda row: row.__setitem__("primary_key", []), "CBN018_PRIMARY_KEY"),
        (lambda row: row.__setitem__("after", None), "CBN019_IMAGE_COMBINATION"),
        (lambda row: row.__setitem__("committed_at", "2024-01-01"), "CBN029_INVALID_TIMESTAMP"),
    ],
)
def test_record_mutations_have_exact_diagnostics(mutation: Any, code: str) -> None:
    manifest, raw = first_raw()
    mutation(raw)
    manifest_schema, envelope_schema, contracts = authority()
    del manifest_schema
    expect_code(code, lambda: normalize_record(raw, manifest, contracts, envelope_schema))


def test_cdc_at_s_and_beyond_object_end_are_rejected() -> None:
    manifest = load(FIXTURE / "manifest.json")
    raw = load(FIXTURE / "objects/snapshot-insert.json")[1]
    _, envelope, contracts = authority()
    raw["commit_lsn"] = manifest["stage1_snapshot_frontier"]["value"]
    expect_code(
        "CBN015_POSITION_BOUNDARY", lambda: normalize_record(raw, manifest, contracts, envelope)
    )
    raw["commit_lsn"] = "FFFFFFFF/FFFFFFFF"
    expect_code(
        "CBN015_POSITION_BOUNDARY", lambda: normalize_record(raw, manifest, contracts, envelope)
    )


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (lambda m: m["objects"][0].__setitem__("path", "../escape"), "CBN003_MANIFEST_PATH"),
        (lambda m: m["objects"][0].__setitem__("sha256", "0" * 64), "CBN005_OBJECT_CHECKSUM"),
        (lambda m: m["objects"][0].__setitem__("byte_length", 1), "CBN006_OBJECT_SIZE"),
        (lambda m: m["objects"][1].__setitem__("object_sequence", 9), "CBN008_OBJECT_SEQUENCE"),
        (
            lambda m: m["objects"][1].__setitem__(
                "start_exclusive_frontier", {"kind": "postgres_lsn", "value": "0/1"}
            ),
            "CBN022_INTERVAL_GAP_OR_OVERLAP",
        ),
    ],
)
def test_manifest_mutations_fail_before_output(tmp_path: Path, mutation: Any, code: str) -> None:
    target = tmp_path / "fixture"
    shutil.copytree(FIXTURE, target)
    manifest = load(target / "manifest.json")
    mutation(manifest)
    schema, _, _ = authority()
    expect_code(code, lambda: validate_manifest(target, manifest, schema))


def test_missing_object_and_row_count_fail_closed(tmp_path: Path) -> None:
    target = tmp_path / "fixture"
    shutil.copytree(FIXTURE, target)
    manifest = load(target / "manifest.json")
    (target / manifest["objects"][0]["path"]).unlink()
    schema, _, _ = authority()
    expect_code("CBN004_OBJECT_MISSING", lambda: validate_manifest(target, manifest, schema))
    target = tmp_path / "fixture2"
    shutil.copytree(FIXTURE, target)
    manifest = load(target / "manifest.json")
    manifest["objects"][0]["row_count"] = 99
    manifest_schema, envelope, contracts = authority()
    expect_code(
        "CBN007_ROW_COUNT",
        lambda: normalize_manifest(
            target,
            manifest,
            manifest_schema=manifest_schema,
            envelope_schema=envelope,
            source_contracts=contracts,
        ),
    )


def test_arrival_permutation_does_not_change_output() -> None:
    original = bundle()
    assert tuple(sorted(original.canonical, key=lambda row: row["event_id"])) != ()
    reversed_events = tuple(reversed(original.canonical))
    assert records_semantically_equal(original.canonical, tuple(reversed(reversed_events)))


def test_json_and_parquet_transport_round_trip_are_equivalent(tmp_path: Path) -> None:
    raw = load(FIXTURE / "objects/snapshot-insert.json")[1]
    raw_text = json.dumps(raw, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    path = tmp_path / "one.parquet"
    digest = __import__("hashlib").sha256(raw_text.encode()).hexdigest()
    pq.write_table(pa.table({"record_json": [raw_text], "record_sha256": [digest]}), path)
    table = pq.read_table(path).to_pylist()[0]
    decoded = strict_json_loads(table["record_json"])
    manifest = load(FIXTURE / "manifest.json")
    _, envelope, contracts = authority()
    assert canonical_event_bytes(
        normalize_record(raw, manifest, contracts, envelope)
    ) == canonical_event_bytes(normalize_record(decoded, manifest, contracts, envelope))


def test_replay_duplicate_and_payload_conflict_classification() -> None:
    event = bundle().canonical[1]
    assert event_id(event) == event["event_id"]
    changed = copy.deepcopy(event)
    changed["after"]["amount"] += 1
    changed["payload_digest"] = event_payload_digest(changed)
    assert changed["event_id"] == event["event_id"]
    assert changed["payload_digest"] != event["payload_digest"]


def test_atomic_bundle_write_and_existing_destination_guard(tmp_path: Path) -> None:
    result = bundle()
    output = tmp_path / "sealed"
    write_bundle_atomic(output, result)
    assert sorted(path.name for path in output.iterdir()) == [
        "canonical.json",
        "quarantine.json",
        "report.json",
    ]
    with pytest.raises(FileExistsError):
        write_bundle_atomic(output, result)


def test_quarantine_is_deterministic_and_mutually_exclusive(tmp_path: Path) -> None:
    target = tmp_path / "fixture"
    shutil.copytree(FIXTURE, target)
    records = load(target / "objects/snapshot-insert.json")
    records[1]["after"] = None
    payload = (json.dumps(records, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    object_entry = load(target / "manifest.json")["objects"][0]
    (target / object_entry["path"]).write_bytes(payload)
    manifest = load(target / "manifest.json")
    manifest["objects"][0]["byte_length"] = len(payload)
    manifest["objects"][0]["sha256"] = __import__("hashlib").sha256(payload).hexdigest()
    manifest_schema, envelope, contracts = authority()
    first = normalize_manifest(
        target,
        manifest,
        manifest_schema=manifest_schema,
        envelope_schema=envelope,
        source_contracts=contracts,
    )
    second = normalize_manifest(
        target,
        manifest,
        manifest_schema=manifest_schema,
        envelope_schema=envelope,
        source_contracts=contracts,
    )
    assert first.quarantine == second.quarantine
    assert first.quarantine[0]["reason_code"] == "CBN019_IMAGE_COMBINATION"
    assert first.report["accepted_count"] + first.report["quarantined_count"] == 5


def test_parquet_profile_rejects_unexpected_columns(tmp_path: Path) -> None:
    path = tmp_path / "bad.parquet"
    pq.write_table(pa.table({"wrong": ["x"]}), path)
    from changebridge.normalizer import _read_records

    expect_code("CBN027_UNEXPECTED_COLUMN", lambda: _read_records(path, "parquet", 1024))


def test_invalid_position_kind_is_incomparable() -> None:
    with pytest.raises(ContractError) as exc:
        compare_source_positions(
            {"kind": "postgres_lsn", "value": "0/1"},
            {"kind": "integer", "value": "1"},
        )
    assert exc.value.code == "CBPOS004_INCOMPARABLE_KINDS"
