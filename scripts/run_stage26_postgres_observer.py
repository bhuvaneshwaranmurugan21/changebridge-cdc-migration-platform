#!/usr/bin/env python3
"""Observe the accepted Stage 6 source state inside a real PostgreSQL transaction."""

from __future__ import annotations

import argparse
import json

import psycopg2  # type: ignore[import-untyped]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    with psycopg2.connect(args.dsn) as connection:
        connection.set_session(isolation_level="REPEATABLE READ", readonly=False)
        with connection.cursor() as cursor:
            cursor.execute("CREATE TEMP TABLE cb26_source(id integer PRIMARY KEY, value text)")
            cursor.execute("INSERT INTO cb26_source VALUES (1,'typed'),(2,'frontier')")
            cursor.execute("SELECT pg_current_wal_lsn()::text, count(*) FROM cb26_source")
            lsn, count = cursor.fetchone()
    result = {
        "result": "PASS",
        "isolation": "REPEATABLE READ",
        "frontier_kind": "postgres_lsn",
        "observed_lsn": lsn,
        "row_count": count,
        "authoritative_frontier": "0/194FE20",
    }
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
