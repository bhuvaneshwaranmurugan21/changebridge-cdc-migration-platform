"""Transport-neutral CDC domain objects."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class Operation(StrEnum):
    INSERT = "insert"
    UPDATE = "update"
    DELETE = "delete"


@dataclass(frozen=True)
class ChangeEvent:
    table: str
    key: str
    operation: Operation
    before: dict[str, Any] | None
    after: dict[str, Any] | None

    def __post_init__(self) -> None:
        if self.operation is Operation.DELETE and self.after is not None:
            raise ValueError("delete events cannot contain an after image")
        if self.operation is not Operation.DELETE and self.after is None:
            raise ValueError("insert/update events require an after image")

    def as_dict(self) -> dict[str, Any]:
        return {
            "after": self.after,
            "before": self.before,
            "key": self.key,
            "operation": self.operation.value,
            "table": self.table,
        }


@dataclass(frozen=True)
class CdcTransaction:
    transaction_id: str
    commit_lsn: int
    committed_at: str
    events: tuple[ChangeEvent, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "commit_lsn": self.commit_lsn,
            "committed_at": self.committed_at,
            "events": [event.as_dict() for event in self.events],
            "transaction_id": self.transaction_id,
        }


@dataclass(frozen=True)
class CdcBatch:
    batch_id: str
    start_lsn_exclusive: int
    end_lsn_inclusive: int
    transactions: tuple[CdcTransaction, ...]

    def __post_init__(self) -> None:
        if self.end_lsn_inclusive <= self.start_lsn_exclusive:
            raise ValueError("batch frontier must advance")

    def as_dict(self) -> dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "end_lsn_inclusive": self.end_lsn_inclusive,
            "start_lsn_exclusive": self.start_lsn_exclusive,
            "transactions": [transaction.as_dict() for transaction in self.transactions],
        }


@dataclass(frozen=True)
class Generation:
    generation_id: str
    snapshot_lsn: int
    current_lsn: int
    schema_version: str
    status: str
