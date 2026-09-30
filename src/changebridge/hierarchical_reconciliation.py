"""Deterministic typed reconciliation from keyed rows to one generation root."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from changebridge.contracts import semantic_digest

PRIMARY_KEYS = {"orders": "order_id", "order_items": "item_id"}


def _key(table: str, row: Mapping[str, Any]) -> str:
    field = PRIMARY_KEYS.get(table)
    if field is None or field not in row:
        raise ValueError(f"CB26R001_KEY_AUTHORITY:{table}")
    return str(row[field])


def _index(table: str, rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = _key(table, row)
        if key in result:
            raise ValueError(f"CB26R002_DUPLICATE_KEY:{table}:{key}")
        result[key] = dict(row)
    return result


def _bucket(key: str, count: int) -> int:
    return int(semantic_digest(key, domain="stage26-bucket-key")[:16], 16) % count


def reconcile(
    source: Mapping[str, Sequence[Mapping[str, Any]]],
    candidate: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    generation_id: str,
    frontier: str,
    schema_identities: Mapping[str, str],
    bucket_count: int = 8,
) -> dict[str, Any]:
    """Compare exact typed rows at one frontier and localize every mismatch."""
    if bucket_count < 1:
        raise ValueError("CB26R003_BUCKET_COUNT")
    table_reports: dict[str, Any] = {}
    mismatch_count = 0
    for table in sorted(set(source) | set(candidate)):
        expected, actual = (
            _index(table, source.get(table, [])),
            _index(table, candidate.get(table, [])),
        )
        mismatches: list[dict[str, str]] = []
        bucket_rows: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for key in sorted(set(expected) | set(actual)):
            left, right = expected.get(key), actual.get(key)
            if left is None:
                mismatches.append({"kind": "UNEXPECTED_CANDIDATE_ROW", "key": key})
            elif right is None:
                mismatches.append({"kind": "MISSING_CANDIDATE_ROW", "key": key})
            elif semantic_digest(left, domain=f"stage26-row:{table}") != semantic_digest(
                right, domain=f"stage26-row:{table}"
            ):
                mismatches.append({"kind": "VALUE_MISMATCH", "key": key})
            bucket_rows[_bucket(key, bucket_count)].append(
                {
                    "key": key,
                    "source_digest": None
                    if left is None
                    else semantic_digest(left, domain=f"stage26-row:{table}"),
                    "candidate_digest": None
                    if right is None
                    else semantic_digest(right, domain=f"stage26-row:{table}"),
                }
            )
        buckets = [
            {
                "bucket": bucket,
                "row_count": len(bucket_rows.get(bucket, [])),
                "digest": semantic_digest(
                    bucket_rows.get(bucket, []), domain=f"stage26-bucket:{table}:{bucket}"
                ),
            }
            for bucket in range(bucket_count)
        ]
        report = {
            "schema_identity": schema_identities[table],
            "source_count": len(expected),
            "candidate_count": len(actual),
            "source_digest": semantic_digest(
                [expected[key] for key in sorted(expected)], domain=f"stage26-table:{table}"
            ),
            "candidate_digest": semantic_digest(
                [actual[key] for key in sorted(actual)], domain=f"stage26-table:{table}"
            ),
            "buckets": buckets,
            "mismatches": mismatches,
        }
        report["table_digest"] = semantic_digest(report, domain=f"stage26-table-proof:{table}")
        mismatch_count += len(mismatches)
        table_reports[table] = report
    body = {
        "record_type": "reconciliation_report",
        "contract_version": "1.0.0",
        "generation_id": generation_id,
        "frontier": {"kind": "postgres_lsn", "value": frontier},
        "partitioning": {"algorithm": "sha256-mod", "bucket_count": bucket_count},
        "tables": table_reports,
        "mismatch_count": mismatch_count,
        "verdict": "PASS" if mismatch_count == 0 else "FAIL",
    }
    return {
        **body,
        "reconciliation_digest": semantic_digest(body, domain="stage26-reconciliation"),
    }
