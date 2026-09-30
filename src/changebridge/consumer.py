"""Generation-pinned consumer resolution for Stage 7."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from changebridge.contracts import semantic_digest
from changebridge.publication import PublicationError, PublicationStore

TableReader = Callable[[str, Mapping[str, Any]], Mapping[str, Any]]


class ConsumerResolver:
    def __init__(self, store: PublicationStore) -> None:
        self.store = store

    def resolve_and_verify(
        self,
        product_id: str,
        *,
        pin_id: str,
        read_table: TableReader,
    ) -> dict[str, Any]:
        pin = self.store.pin(product_id, pin_id)
        if pin["route"] == "SOURCE_FALLBACK":
            return {**pin, "verification": "SOURCE_FALLBACK_VERIFIED", "tables": {}}
        table_map = pin["table_map"]
        if not isinstance(table_map, Mapping) or set(table_map) != {"order_items", "orders"}:
            raise PublicationError("CB27C004_TABLE_MAP_INCOMPLETE", pin_id)
        observations: dict[str, Any] = {}
        for table in sorted(table_map):
            binding = table_map[table]
            observed = dict(read_table(table, binding))
            if str(observed.get("snapshot_id")) != str(binding["snapshot_id"]):
                raise PublicationError("CB27C005_SNAPSHOT_MISMATCH", table)
            if int(observed.get("row_count", -1)) != int(binding["row_count"]):
                raise PublicationError("CB27C006_ROW_COUNT_MISMATCH", table)
            observations[table] = observed
        result = {
            **pin,
            "verification": "GENERATION_CONSISTENT_READ_VERIFIED",
            "tables": observations,
        }
        result["consumer_verification_digest"] = semantic_digest(
            result, domain="stage27-consumer-verification"
        )
        return result
