"""Pure source-boundary contracts and PostgreSQL LSN guards."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from changebridge.contracts import ContractError, compare_source_positions

BOUNDARY_RECEIPT_VERSION = "source-boundary-receipt/1.0.0"
LSN_COMPARATOR_VERSION = "postgres-lsn-u32-pair/1.0.0"
POSTGRES_IMAGE = "postgres@sha256:639ab7ceb90e13123085b741fb31ef493fba25463002f6da665352e7b534b652"
_NAMESPACE = re.compile(r"^cb_[a-z0-9_]{1,48}$")


def _fail(code: str, detail: str) -> ContractError:
    return ContractError(code, detail)


@dataclass(frozen=True)
class PostgresSettings:
    host: str
    port: int
    database: str
    user: str
    password: str
    schema: str

    @classmethod
    def from_environment(cls) -> PostgresSettings:
        required = (
            "PGHOST",
            "PGPORT",
            "PGDATABASE",
            "PGUSER",
            "PGPASSWORD",
            "CB_SOURCE_SCHEMA",
        )
        missing = [name for name in required if not os.environ.get(name)]
        if missing:
            raise _fail("CBPG001_MISSING_CONNECTION_ENV", ",".join(missing))
        schema = os.environ["CB_SOURCE_SCHEMA"]
        if _NAMESPACE.fullmatch(schema) is None:
            raise _fail("CBSRC023_INVALID_NAMESPACE", schema)
        return cls(
            host=os.environ["PGHOST"],
            port=int(os.environ["PGPORT"]),
            database=os.environ["PGDATABASE"],
            user=os.environ["PGUSER"],
            password=os.environ["PGPASSWORD"],
            schema=schema,
        )

    def connect_arguments(self) -> dict[str, Any]:
        return {
            "application_name": "changebridge-stage21",
            "connect_timeout": 10,
            "dbname": self.database,
            "host": self.host,
            "password": self.password,
            "port": self.port,
            "user": self.user,
            "options": f"-csearch_path={self.schema}",
        }


class FrontierRegistry:
    """In-memory reference guard for one immutable frontier per generation."""

    def __init__(self) -> None:
        self._frontiers: dict[str, dict[str, str]] = {}

    def bind(self, generation_id: str, frontier: Mapping[str, str]) -> dict[str, str]:
        candidate = dict(frontier)
        compare_source_positions(candidate, candidate)
        if candidate["kind"] != "postgres_lsn":
            raise _fail("CBSNP001_NON_POSTGRES_FRONTIER", candidate["kind"])
        prior = self._frontiers.get(generation_id)
        if prior is not None and prior != candidate:
            raise _fail("CBSNP002_SECOND_FRONTIER", generation_id)
        self._frontiers[generation_id] = candidate
        return deepcopy(candidate)


def select_first_committed_transaction(
    records: Sequence[Mapping[str, Any]], frontier: Mapping[str, Any]
) -> dict[str, Any]:
    """Select the first decoded transaction by its commit LSN.

    PostgreSQL may label the first row-level output with the slot's consistent
    point.  A migration transaction frontier is therefore the corresponding
    COMMIT record, which must be strictly after the exported-snapshot boundary.
    """

    first_change_index = next(
        (
            index
            for index, record in enumerate(records)
            if str(record.get("data", "")).startswith("table ")
        ),
        None,
    )
    if first_change_index is None:
        raise _fail("CBSNP015_NO_POST_BOUNDARY_CHANGE", "logical decoding output")
    first_change = records[first_change_index]
    xid = str(first_change.get("xid", ""))
    change_position = {"kind": "postgres_lsn", "value": first_change.get("lsn")}
    if not xid or not isinstance(change_position["value"], str):
        raise _fail("CBSNP016_MALFORMED_DECODED_CHANGE", repr(first_change))
    if compare_source_positions(change_position, frontier) < 0:
        raise _fail("CBSNP017_CHANGE_PRECEDES_FRONTIER", repr(change_position))

    commit = next(
        (
            record
            for record in records[first_change_index + 1 :]
            if str(record.get("xid", "")) == xid
            and str(record.get("data", "")).startswith("COMMIT ")
        ),
        None,
    )
    if commit is None or not isinstance(commit.get("lsn"), str):
        raise _fail("CBSNP018_COMMIT_RECORD_MISSING", xid)
    commit_position = {"kind": "postgres_lsn", "value": commit["lsn"]}
    if compare_source_positions(commit_position, frontier) <= 0:
        raise _fail("CBSNP009_NONADVANCING_FIRST_POSITION", repr(commit_position))
    return {
        "first_change_position": change_position,
        "first_commit_position": commit_position,
        "first_transaction_xid": xid,
        "logical_change_count": sum(
            str(record.get("data", "")).startswith("table ") for record in records
        ),
    }


def validate_boundary_receipt(
    receipt: Mapping[str, Any],
    *,
    expected_generation_id: str,
    expected_workload_id: str,
    expected_schema_set_digest: str,
    expected_source_identity_digest: str,
) -> None:
    if receipt.get("receipt_version") != BOUNDARY_RECEIPT_VERSION:
        raise _fail("CBSNP003_UNKNOWN_RECEIPT_VERSION", str(receipt.get("receipt_version")))
    checks = (
        ("generation_id", expected_generation_id, "CBSNP004_GENERATION_MISMATCH"),
        ("workload_id", expected_workload_id, "CBSNP005_WORKLOAD_MISMATCH"),
        ("schema_set_digest", expected_schema_set_digest, "CBSNP006_SCHEMA_MISMATCH"),
        (
            "source_identity_digest",
            expected_source_identity_digest,
            "CBSNP007_SOURCE_IDENTITY_MISMATCH",
        ),
    )
    for field, expected, diagnostic in checks:
        if receipt.get(field) != expected:
            raise _fail(diagnostic, field)
    frontier = receipt.get("snapshot_frontier")
    first = receipt.get("first_post_boundary_position")
    if not isinstance(frontier, Mapping) or not isinstance(first, Mapping):
        raise _fail("CBSNP008_MISSING_BOUNDARY_POSITION", "snapshot or first position")
    if frontier.get("kind") != "postgres_lsn" or first.get("kind") != "postgres_lsn":
        raise _fail("CBSNP001_NON_POSTGRES_FRONTIER", repr((frontier, first)))
    if compare_source_positions(first, frontier) <= 0:
        raise _fail("CBSNP009_NONADVANCING_FIRST_POSITION", repr(first))
    if receipt.get("comparator_version") != LSN_COMPARATOR_VERSION:
        raise _fail("CBSNP010_COMPARATOR_VERSION_MISMATCH", str(receipt.get("comparator_version")))
    if receipt.get("snapshot_imported") is not True:
        raise _fail("CBSNP011_SNAPSHOT_NOT_IMPORTED", "snapshot_imported")
    if receipt.get("cleanup", {}).get("slot_dropped") is not True:
        raise _fail("CBSNP012_CLEANUP_NOT_PROVEN", "slot")
