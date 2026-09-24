"""Real PostgreSQL source execution and exported-snapshot boundary adapter."""

from __future__ import annotations

import hashlib
import re
import threading
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import psycopg2  # type: ignore[import-untyped]
from psycopg2 import sql
from psycopg2.extras import LogicalReplicationConnection  # type: ignore[import-untyped]

from changebridge.contracts import ContractError, semantic_digest
from changebridge.source_boundary import (
    BOUNDARY_RECEIPT_VERSION,
    CAPTURE_METHOD,
    LSN_COMPARATOR_VERSION,
    POSTGRES_IMAGE,
    FrontierRegistry,
    PostgresSettings,
    select_first_committed_transaction,
    validate_boundary_receipt,
)
from changebridge.source_workload import replay_workload, validate_workload

_SLOT = re.compile(r"^[a-z0-9_]{1,63}$")
_TABLE_KEYS = {"order_items": "item_id", "orders": "order_id"}
_TABLE_COLUMNS = {
    "order_items": {"created_at", "item_id", "note", "order_id", "quantity", "unit_price"},
    "orders": {"amount", "campaign_id", "customer_id", "order_id", "source_note"},
}


def _fail(code: str, detail: str) -> ContractError:
    return ContractError(code, detail)


def _connect(settings: PostgresSettings) -> Any:
    return psycopg2.connect(**settings.connect_arguments())


def initialize_source_namespace(settings: PostgresSettings) -> None:
    connection = _connect(settings)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = %s)", (settings.schema,)
            )
            if cursor.fetchone()[0]:
                raise _fail("CBSRC024_DIRTY_REUSED_NAMESPACE", settings.schema)
            cursor.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(settings.schema)))
        connection.commit()
    finally:
        connection.close()


def drop_source_namespace(settings: PostgresSettings) -> None:
    connection = _connect(settings)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(settings.schema))
            )
        connection.commit()
    finally:
        connection.close()


def apply_migration(connection: Any, migration: Path) -> str:
    if not migration.is_file():
        raise _fail("CBSRC014_MIGRATION_MISSING", migration.name)
    content = migration.read_text(encoding="utf-8")
    checksum = hashlib.sha256(content.encode()).hexdigest()
    with connection.cursor() as cursor:
        cursor.execute(content)
    connection.commit()
    return checksum


def _execute_event(cursor: Any, event: Mapping[str, Any]) -> None:
    operation = event["operation"]
    table = event["table"]
    if operation == "schema_change":
        cursor.execute("ALTER TABLE orders ADD COLUMN source_note TEXT")
        return
    if table not in _TABLE_KEYS:
        raise _fail("CBSRC015_UNKNOWN_SOURCE_TABLE", str(table))
    key_column = _TABLE_KEYS[table]
    before = event["before"]
    after = event["after"]
    if operation == "insert":
        if not isinstance(after, Mapping):
            raise _fail("CBSRC016_INVALID_EVENT_IMAGE", str(event["transaction_id"]))
        columns = sorted(after)
        if not set(columns) <= _TABLE_COLUMNS[table]:
            raise _fail("CBSRC017_UNKNOWN_SOURCE_COLUMN", repr(columns))
        query = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
            sql.Identifier(table),
            sql.SQL(", ").join(map(sql.Identifier, columns)),
            sql.SQL(", ").join(sql.Placeholder() for _ in columns),
        )
        cursor.execute(query, [after[column] for column in columns])
    elif operation == "update":
        if not isinstance(before, Mapping) or not isinstance(after, Mapping):
            raise _fail("CBSRC016_INVALID_EVENT_IMAGE", str(event["transaction_id"]))
        columns = sorted(set(after) - {key_column})
        if not set(columns) <= _TABLE_COLUMNS[table]:
            raise _fail("CBSRC017_UNKNOWN_SOURCE_COLUMN", repr(columns))
        assignments = sql.SQL(", ").join(
            sql.SQL("{} = {}").format(sql.Identifier(column), sql.Placeholder())
            for column in columns
        )
        query = sql.SQL("UPDATE {} SET {} WHERE {} = {}").format(
            sql.Identifier(table),
            assignments,
            sql.Identifier(key_column),
            sql.Placeholder(),
        )
        cursor.execute(query, [after[column] for column in columns] + [event["key"]])
        if cursor.rowcount != 1:
            raise _fail("CBSRC018_UPDATE_TARGET_MISMATCH", f"{table}:{event['key']}")
    elif operation == "delete":
        query = sql.SQL("DELETE FROM {} WHERE {} = {}").format(
            sql.Identifier(table), sql.Identifier(key_column), sql.Placeholder()
        )
        cursor.execute(query, [event["key"]])
        if cursor.rowcount != 1:
            raise _fail("CBSRC019_DELETE_TARGET_MISMATCH", f"{table}:{event['key']}")
    else:
        raise _fail("CBSRC013_UNKNOWN_OPERATION", str(operation))


def _execute_transaction(
    settings: PostgresSettings,
    transaction: Mapping[str, Any],
    *,
    ready: threading.Event | None = None,
    commit_permission: threading.Event | None = None,
) -> dict[str, Any]:
    connection = _connect(settings)
    try:
        with connection.cursor() as cursor:
            for raw_event in transaction["events"]:
                event = {**raw_event, "transaction_id": transaction["transaction_id"]}
                _execute_event(cursor, event)
            cursor.execute("SELECT txid_current()::text")
            observed_transaction_id = cursor.fetchone()[0]
        if ready is not None:
            ready.set()
        if commit_permission is not None and not commit_permission.wait(timeout=15):
            raise _fail("CBSRC020_COMMIT_PERMISSION_TIMEOUT", transaction["transaction_id"])
        if transaction["outcome"] == "COMMIT":
            connection.commit()
        else:
            connection.rollback()
        return {
            "logical_transaction_id": transaction["transaction_id"],
            "observed_transaction_id_sha256": hashlib.sha256(
                observed_transaction_id.encode()
            ).hexdigest(),
            "outcome": transaction["outcome"],
        }
    finally:
        connection.close()


def _execute_concurrent_pair(
    settings: PostgresSettings, transactions: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    by_id = {transaction["transaction_id"]: transaction for transaction in transactions}
    commit_order = ("tx-007-writer-b", "tx-006-writer-a")
    ready = {tx_id: threading.Event() for tx_id in by_id}
    permit = {tx_id: threading.Event() for tx_id in by_id}
    done = {tx_id: threading.Event() for tx_id in by_id}
    results: dict[str, dict[str, Any]] = {}
    errors: list[BaseException] = []

    def worker(tx_id: str) -> None:
        try:
            results[tx_id] = _execute_transaction(
                settings,
                by_id[tx_id],
                ready=ready[tx_id],
                commit_permission=permit[tx_id],
            )
        except BaseException as error:
            errors.append(error)
            ready[tx_id].set()
        finally:
            done[tx_id].set()

    threads = [threading.Thread(target=worker, args=(tx_id,), daemon=True) for tx_id in by_id]
    for thread in threads:
        thread.start()
    if not all(event.wait(timeout=15) for event in ready.values()):
        raise _fail("CBSRC021_CONCURRENT_READY_TIMEOUT", "writers-ready")
    for tx_id in commit_order:
        permit[tx_id].set()
        if not done[tx_id].wait(timeout=15):
            raise _fail("CBSRC022_CONCURRENT_COMMIT_TIMEOUT", tx_id)
    for thread in threads:
        thread.join(timeout=1)
    if errors:
        raise errors[0]
    return [results[tx_id] for tx_id in commit_order]


def execute_workload_phase(
    settings: PostgresSettings, spec: Mapping[str, Any], phase: str
) -> list[dict[str, Any]]:
    validate_workload(spec)
    transactions = [tx for tx in spec["transactions"] if tx["phase"] == phase]
    observations: list[dict[str, Any]] = []
    concurrent_ids = {"tx-006-writer-a", "tx-007-writer-b"}
    concurrent = [tx for tx in transactions if tx["transaction_id"] in concurrent_ids]
    for transaction in sorted(transactions, key=lambda tx: tx["commit_ordinal"] or 2**31):
        if transaction["transaction_id"] in concurrent_ids:
            if not any(item.get("concurrency_group") == "writers-ready" for item in observations):
                for item in _execute_concurrent_pair(settings, concurrent):
                    item["concurrency_group"] = "writers-ready"
                    observations.append(item)
            continue
        observations.append(_execute_transaction(settings, transaction))
    return observations


def query_source_state(connection: Any, *, workload_id: str, phase: str) -> dict[str, Any]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT item_id, order_id, quantity, unit_price::text, note, "
            "to_char(created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"') "
            "FROM order_items ORDER BY item_id"
        )
        items = [
            {
                "created_at": row[5],
                "item_id": row[0],
                "note": row[4],
                "order_id": row[1],
                "quantity": row[2],
                "unit_price": row[3],
            }
            for row in cursor.fetchall()
        ]
        cursor.execute(
            "SELECT order_id, customer_id, amount, campaign_id, source_note "
            "FROM orders ORDER BY order_id"
        )
        orders = [
            {
                "amount": row[2],
                "campaign_id": row[3],
                "customer_id": row[1],
                "order_id": row[0],
                "source_note": row[4],
            }
            for row in cursor.fetchall()
        ]
    tables: dict[str, Any] = {}
    for name, rows in (("order_items", items), ("orders", orders)):
        tables[name] = {
            "row_count": len(rows),
            "rows": rows,
            "state_digest": semantic_digest(rows, domain=f"source-table-state:{name}"),
        }
    whole = {name: value["state_digest"] for name, value in sorted(tables.items())}
    return {
        "phase": phase,
        "tables": tables,
        "whole_state_digest": semantic_digest(whole, domain="source-whole-state"),
        "workload_id": workload_id,
    }


def capture_boundary(
    settings: PostgresSettings,
    spec: Mapping[str, Any],
    *,
    repository_commit: str,
    repository_tree: str,
) -> dict[str, Any]:
    """Capture one real imported snapshot and prove the first post-S change."""

    validate_workload(spec)
    generation_id = "generation-" + spec["workload_id"][:24]
    slot_name = "cb_stage21_" + spec["workload_id"][:20]
    if _SLOT.fullmatch(slot_name) is None:
        raise _fail("CBSNP013_INVALID_SLOT_NAME", slot_name)

    exporter = psycopg2.connect(
        **settings.connect_arguments(),
        connection_factory=LogicalReplicationConnection,
    )
    snapshot_connection = None
    admin_connection = None
    slot_created = False
    slot_dropped = False
    try:
        replication_cursor = exporter.cursor()
        replication_cursor.execute(
            f"CREATE_REPLICATION_SLOT {slot_name} LOGICAL test_decoding (SNAPSHOT 'export')"
        )
        row = replication_cursor.fetchone()
        columns = tuple(item.name for item in replication_cursor.description)
        if columns != ("slot_name", "consistent_point", "snapshot_name", "output_plugin"):
            raise _fail("CBPG002_REPLICATION_FIELDS_MISMATCH", repr(columns))
        returned_slot, consistent_point, snapshot_name, output_plugin = row
        if returned_slot != slot_name or output_plugin != "test_decoding" or not snapshot_name:
            raise _fail("CBPG004_REPLICATION_IDENTITY_MISMATCH", "slot/plugin/snapshot")
        slot_created = True
        frontier = {"kind": "postgres_lsn", "value": consistent_point}
        FrontierRegistry().bind(generation_id, frontier)

        snapshot_connection = _connect(settings)
        snapshot_connection.set_session(
            isolation_level="REPEATABLE READ", readonly=True, autocommit=False
        )
        with snapshot_connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("SET TRANSACTION SNAPSHOT {}").format(sql.Literal(snapshot_name))
            )
            cursor.execute(
                "SELECT system_identifier::text, current_database(), "
                "current_setting('transaction_isolation'), "
                "current_setting('transaction_read_only'), version() "
                "FROM pg_control_system()"
            )
            system_identifier, database, isolation, read_only, server_version = cursor.fetchone()
        source_identity_digest = semantic_digest(
            {
                "database": database,
                "schema": settings.schema,
                "system_identifier": system_identifier,
            },
            domain="postgres-source-identity",
        )
        snapshot_state = query_source_state(
            snapshot_connection, workload_id=spec["workload_id"], phase="PRE_BOUNDARY"
        )
        expected_state = replay_workload(spec, through_phase="PRE_BOUNDARY")
        if snapshot_state["whole_state_digest"] != expected_state["whole_state_digest"]:
            raise _fail("CBSNP014_SNAPSHOT_STATE_MISMATCH", "whole_state_digest")
        snapshot_connection.commit()
        snapshot_connection.close()
        snapshot_connection = None
        exporter.close()

        post_observations = execute_workload_phase(settings, spec, "POST_BOUNDARY")
        admin_connection = _connect(settings)
        with admin_connection.cursor() as cursor:
            cursor.execute(
                "SELECT lsn::text, xid::text, data "
                "FROM pg_logical_slot_get_changes(%s, NULL, NULL)",
                (slot_name,),
            )
            changes = cursor.fetchall()
        admin_connection.commit()
        decoded = [{"data": data, "lsn": lsn, "xid": xid} for lsn, xid, data in changes]
        first_transaction = select_first_committed_transaction(decoded, frontier)
        first_position = first_transaction["first_commit_position"]

        with admin_connection.cursor() as cursor:
            cursor.execute("SELECT pg_drop_replication_slot(%s)", (slot_name,))
        admin_connection.commit()
        slot_dropped = True

        generation_states = ["CREATED", "SNAPSHOT_LOADING", "CDC_APPLYING"]
        generation_record = {
            "contract_version": "1.0.0",
            "evidence_refs": ["evidence/part2/stage1/boundary-capture-report.json"],
            "generation_id": generation_id,
            "record_id": "migration-generation-" + generation_id,
            "record_type": "migration_generation",
            "retention_state": "RETAINED",
            "revision": 0,
            "schema_set_digest": spec["schema_set_digest"],
            "snapshot_frontier": frontier,
            "state": generation_states[-1],
        }
        receipt: dict[str, Any] = {
            "capture_method": CAPTURE_METHOD,
            "cleanup": {"slot_dropped": slot_dropped},
            "comparator_version": LSN_COMPARATOR_VERSION,
            "first_post_boundary_position": first_position,
            "first_post_boundary_change_position": first_transaction[
                "first_change_position"
            ],
            "first_post_boundary_transaction_sha256": hashlib.sha256(
                first_transaction["first_transaction_xid"].encode()
            ).hexdigest(),
            "generation_id": generation_id,
            "generation_record": generation_record,
            "generation_transitions": generation_states,
            "image": POSTGRES_IMAGE,
            "logical_change_count": first_transaction["logical_change_count"],
            "output_plugin": "test_decoding",
            "post_boundary_observations": post_observations,
            "receipt_version": BOUNDARY_RECEIPT_VERSION,
            "repository_commit": repository_commit,
            "repository_tree": repository_tree,
            "schema_set_digest": spec["schema_set_digest"],
            "server_major": 17,
            "server_version_digest": hashlib.sha256(server_version.encode()).hexdigest(),
            "slot_identity_sha256": hashlib.sha256(slot_name.encode()).hexdigest(),
            "snapshot_frontier": frontier,
            "snapshot_identity_sha256": hashlib.sha256(snapshot_name.encode()).hexdigest(),
            "snapshot_imported": True,
            "snapshot_state": snapshot_state,
            "snapshot_transaction": {"isolation": isolation, "read_only": read_only == "on"},
            "source_identity_digest": source_identity_digest,
            "workload_id": spec["workload_id"],
        }
        validate_boundary_receipt(
            receipt,
            expected_generation_id=generation_id,
            expected_workload_id=spec["workload_id"],
            expected_schema_set_digest=spec["schema_set_digest"],
            expected_source_identity_digest=source_identity_digest,
        )
        return receipt
    finally:
        if snapshot_connection is not None and not snapshot_connection.closed:
            snapshot_connection.rollback()
            snapshot_connection.close()
        if not exporter.closed:
            exporter.close()
        if slot_created and not slot_dropped:
            cleanup = admin_connection if admin_connection is not None else _connect(settings)
            try:
                with cleanup.cursor() as cursor:
                    cursor.execute(
                        "SELECT pg_drop_replication_slot(%s) WHERE EXISTS ("
                        "SELECT 1 FROM pg_replication_slots "
                        "WHERE slot_name = %s AND NOT active)",
                        (slot_name, slot_name),
                    )
                cleanup.commit()
            finally:
                cleanup.close()
        elif admin_connection is not None:
            admin_connection.close()
