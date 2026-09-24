#!/usr/bin/env python3
"""Fail-closed PostgreSQL 17 replication snapshot compatibility probe.

The probe intentionally uses the raw logical-replication command because
psycopg2's convenience slot API does not expose the exported snapshot name.
No connection details or exported snapshot identifiers are printed.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Sequence
from typing import Any

import psycopg2
from psycopg2.extras import LogicalReplicationConnection

_LSN = re.compile(r"^[0-9A-F]{1,8}/[0-9A-F]{1,8}$")
_EXPECTED_COLUMNS = ("slot_name", "consistent_point", "snapshot_name", "output_plugin")
_SLOT_NAME = "cb_stage21_compatibility_probe"


class ProbeFailure(RuntimeError):
    """Stable, non-secret compatibility-probe failure."""


def _connection_arguments() -> dict[str, Any]:
    required = ("PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD")
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise ProbeFailure("CBPG001_MISSING_CONNECTION_ENV:" + ",".join(missing))
    return {
        "host": os.environ["PGHOST"],
        "port": int(os.environ["PGPORT"]),
        "dbname": os.environ["PGDATABASE"],
        "user": os.environ["PGUSER"],
        "password": os.environ["PGPASSWORD"],
        "connect_timeout": 10,
        "application_name": "changebridge-stage21-probe",
    }


def _validate_result(columns: Sequence[str], row: Sequence[Any]) -> tuple[str, str]:
    if tuple(columns) != _EXPECTED_COLUMNS:
        raise ProbeFailure("CBPG002_REPLICATION_FIELDS_MISMATCH:" + ",".join(columns))
    if len(row) != 4:
        raise ProbeFailure(f"CBPG003_REPLICATION_ARITY_MISMATCH:{len(row)}")
    slot_name, consistent_point, snapshot_name, output_plugin = row
    if slot_name != _SLOT_NAME or output_plugin != "test_decoding":
        raise ProbeFailure("CBPG004_REPLICATION_IDENTITY_MISMATCH")
    if not isinstance(consistent_point, str) or _LSN.fullmatch(consistent_point) is None:
        raise ProbeFailure("CBPG005_INVALID_CONSISTENT_POINT")
    if not isinstance(snapshot_name, str) or not snapshot_name:
        raise ProbeFailure("CBPG006_MISSING_EXPORTED_SNAPSHOT")
    return consistent_point, snapshot_name


def run_probe() -> dict[str, Any]:
    kwargs = _connection_arguments()
    exporter = psycopg2.connect(
        **kwargs,
        connection_factory=LogicalReplicationConnection,
    )
    exporter.autocommit = True
    snapshot_connection = None
    try:
        replication_cursor = exporter.cursor()
        replication_cursor.execute(
            "CREATE_REPLICATION_SLOT "
            f"{_SLOT_NAME} TEMPORARY LOGICAL test_decoding (SNAPSHOT 'export')"
        )
        row = replication_cursor.fetchone()
        if row is None:
            raise ProbeFailure("CBPG003_REPLICATION_ARITY_MISMATCH:0")
        columns = tuple(item.name for item in replication_cursor.description)
        consistent_point, snapshot_name = _validate_result(columns, row)

        snapshot_connection = psycopg2.connect(**kwargs)
        snapshot_connection.set_session(
            isolation_level="REPEATABLE READ",
            readonly=True,
            autocommit=False,
        )
        with snapshot_connection.cursor() as cursor:
            escaped_snapshot = snapshot_name.replace("'", "''")
            cursor.execute(f"SET TRANSACTION SNAPSHOT '{escaped_snapshot}'")
            cursor.execute(
                "SELECT current_setting('server_version_num'), "
                "current_setting('wal_level'), "
                "current_setting('transaction_isolation'), "
                "current_setting('transaction_read_only')"
            )
            server_version_num, wal_level, isolation, read_only = cursor.fetchone()
        snapshot_connection.rollback()

        if int(server_version_num) // 10000 != 17:
            raise ProbeFailure("CBPG007_UNEXPECTED_SERVER_MAJOR")
        if wal_level != "logical":
            raise ProbeFailure("CBPG008_LOGICAL_REPLICATION_DISABLED")
        if isolation != "repeatable read" or read_only != "on":
            raise ProbeFailure("CBPG009_SNAPSHOT_TRANSACTION_MODE_MISMATCH")

        return {
            "probe_version": "1.0.0",
            "result": "PASS",
            "driver": "psycopg2-binary",
            "driver_version": psycopg2.__version__.split()[0],
            "libpq_version": psycopg2.__libpq_version__,
            "server_major": 17,
            "wal_level": "logical",
            "output_plugin": "test_decoding",
            "replication_result_fields": list(_EXPECTED_COLUMNS),
            "consistent_point_kind": "postgres_lsn",
            "consistent_point_format_valid": True,
            "exported_snapshot_imported": True,
            "snapshot_identity_sha256": hashlib.sha256(snapshot_name.encode()).hexdigest(),
            "consistent_point_sha256": hashlib.sha256(consistent_point.encode()).hexdigest(),
            "snapshot_transaction": {
                "isolation": "repeatable read",
                "read_only": True,
            },
            "connection_details_recorded": False,
        }
    finally:
        if snapshot_connection is not None and not snapshot_connection.closed:
            snapshot_connection.close()
        exporter.close()


def main() -> int:
    try:
        result = run_probe()
    except (ProbeFailure, psycopg2.Error) as error:
        diagnostic = error.args[0] if isinstance(error, ProbeFailure) else error.pgcode
        print(json.dumps({"result": "FAIL", "diagnostic": diagnostic}, sort_keys=True))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
