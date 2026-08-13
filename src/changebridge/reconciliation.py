"""Proof objects for source/candidate equality at a declared frontier."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from changebridge.canonical import table_digest


@dataclass(frozen=True)
class TableProof:
    table: str
    expected_count: int
    actual_count: int
    expected_digest: str
    actual_digest: str

    @property
    def matched(self) -> bool:
        return (
            self.expected_count == self.actual_count
            and self.expected_digest == self.actual_digest
        )


@dataclass(frozen=True)
class ReconciliationReport:
    generation_id: str
    frontier_lsn: int
    tables: tuple[TableProof, ...]

    @property
    def matched(self) -> bool:
        return bool(self.tables) and all(table.matched for table in self.tables)

    def as_dict(self) -> dict[str, Any]:
        return {
            "frontier_lsn": self.frontier_lsn,
            "generation_id": self.generation_id,
            "matched": self.matched,
            "tables": [
                {
                    "actual_count": item.actual_count,
                    "actual_digest": item.actual_digest,
                    "expected_count": item.expected_count,
                    "expected_digest": item.expected_digest,
                    "matched": item.matched,
                    "table": item.table,
                }
                for item in self.tables
            ],
        }


def reconcile(
    generation_id: str,
    frontier_lsn: int,
    expected: dict[str, dict[str, dict[str, Any]]],
    actual: dict[str, dict[str, dict[str, Any]]],
) -> ReconciliationReport:
    table_names = sorted(set(expected) | set(actual))
    proofs = tuple(
        TableProof(
            table=table,
            expected_count=len(expected.get(table, {})),
            actual_count=len(actual.get(table, {})),
            expected_digest=table_digest(expected.get(table, {})),
            actual_digest=table_digest(actual.get(table, {})),
        )
        for table in table_names
    )
    return ReconciliationReport(generation_id, frontier_lsn, proofs)
