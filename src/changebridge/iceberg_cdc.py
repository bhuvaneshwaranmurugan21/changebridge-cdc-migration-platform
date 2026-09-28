"""Real Spark/Iceberg Stage 4 CDC mutations with recoverable commit metadata."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, NoReturn

from changebridge.contracts import semantic_digest
from changebridge.iceberg_snapshot import BUSINESS_COLUMNS, IcebergSnapshotAdapter


class IcebergCDCError(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


def _fail(code: str, detail: str) -> NoReturn:
    raise IcebergCDCError(code, detail)


class _JavaCallable:
    def __init__(self, action: Callable[[], None]) -> None:
        self.action = action

    def call(self) -> None:
        self.action()

    class Java:
        implements = ["java.util.concurrent.Callable"]


class IcebergCDCAdapter(IcebergSnapshotAdapter):
    """Generation-scoped row mutation and snapshot-token recovery adapter."""

    def __init__(
        self,
        *,
        warehouse: Path,
        namespace: str,
        iceberg_jar: Path,
        app_name: str = "changebridge-stage24-cdc",
    ) -> None:
        super().__init__(
            warehouse=warehouse,
            namespace=namespace,
            iceberg_jar=iceberg_jar,
            app_name=app_name,
        )

    def __enter__(self) -> IcebergCDCAdapter:
        return self

    @staticmethod
    def table_input_digest(events: list[dict[str, Any]]) -> str:
        return semantic_digest(events, domain="stage24-table-input")

    @staticmethod
    def commit_token(
        generation_id: str,
        transaction_id: str,
        source_table: str,
        table_input_digest: str,
    ) -> str:
        return semantic_digest(
            {
                "generation_id": generation_id,
                "transaction_id": transaction_id,
                "source_table": source_table,
                "table_input_digest": table_input_digest,
                "protocol": "changebridge-stage24-cdc/1.0.0",
            },
            domain="stage24-iceberg-commit-token",
        )

    @staticmethod
    def _normalize_business(table: str, row: dict[str, Any]) -> dict[str, Any]:
        result = {column: row[column] for column in BUSINESS_COLUMNS[table]}
        if table == "order_items":
            result["unit_price"] = format(Decimal(str(result["unit_price"])), ".2f")
            value = result["created_at"]
            if isinstance(value, datetime):
                result["created_at"] = value.replace(tzinfo=UTC).isoformat(
                    timespec="microseconds"
                ).replace("+00:00", "Z")
        return result

    def current_row(self, table: str, key: str) -> dict[str, Any] | None:
        identifier = self.identifier(table)
        if not self.spark.catalog.tableExists(identifier):
            return None
        primary_key = BUSINESS_COLUMNS[table][0]
        escaped = key.replace("'", "''")
        rows = self.spark.sql(
            f"SELECT * FROM {identifier} WHERE {primary_key} = '{escaped}'"
        ).collect()
        if len(rows) > 1:
            _fail("CB24I001_MULTI_ROW_EFFECT", f"{table}:{key}")
        if not rows:
            return None
        return self._normalize_business(table, rows[0].asDict(recursive=True))

    def _target_row(
        self, event: dict[str, Any], *, commit_token: str, row_sequence: int
    ) -> dict[str, Any]:
        image = event["after"] if event["after"] is not None else event["before"]
        material = {**event, "after": image}
        row = self._to_target_row(
            material,
            shard_id=str(event["transaction_id"]),
            commit_token=commit_token,
            row_sequence=row_sequence,
        )
        row["_cb_snapshot_batch"] = str(event["transaction_id"])
        return {**row, "_cb_operation": event["operation"]}

    def _check_preconditions(self, table: str, events: list[dict[str, Any]]) -> None:
        for event in events:
            key = str(event["primary_key"][0]["value"])
            current = self.current_row(table, key)
            operation = event["operation"]
            if operation == "insert":
                if current is not None:
                    _fail("CB24I002_DUPLICATE_INSERT", f"{table}:{key}")
                continue
            if current is None:
                _fail("CB24I003_TARGET_ROW_MISSING", f"{table}:{key}")
            expected = self._normalize_business(table, dict(event["before"]))
            if current != expected:
                _fail("CB24I005_TARGET_BEFORE_IMAGE_MISMATCH", f"{table}:{key}")

    def _with_commit_properties(
        self, properties: dict[str, str], action: Callable[[], None]
    ) -> None:
        jvm = self.spark.sparkContext._jvm
        if jvm is None:
            _fail("CB24I006_COMMIT_METADATA_FAILURE", "missing-jvm")
        java_properties = jvm.java.util.HashMap()
        for key, value in sorted(properties.items()):
            java_properties.put(key, value)
        try:
            jvm.org.apache.iceberg.spark.CommitMetadata.withCommitProperties(
                java_properties,
                _JavaCallable(action),
                jvm.java.lang.Class.forName("java.lang.Exception"),
            )
        except Exception as exc:  # Spark/Py4J exposes runtime Java failures dynamically.
            _fail("CB24I006_COMMIT_METADATA_FAILURE", type(exc).__name__)

    def apply_table(
        self,
        *,
        generation_id: str,
        transaction_id: str,
        transaction_digest: str,
        source_table: str,
        events: list[dict[str, Any]],
        manifest_id: str,
        source_frontier: str,
    ) -> dict[str, Any]:
        if not events:
            _fail("CB24I007_EMPTY_TABLE_PLAN", source_table)
        table_digest = self.table_input_digest(events)
        token = self.commit_token(generation_id, transaction_id, source_table, table_digest)
        existing = self.snapshot_for_token(source_table, token)
        if existing is not None:
            summary = existing["summary"]
            expected = {
                "changebridge_transaction_digest": transaction_digest,
                "changebridge_table_input_digest": table_digest,
                "changebridge_generation_id": generation_id,
            }
            if any(summary.get(key) != value for key, value in expected.items()):
                _fail("CB24I008_COMMIT_TOKEN_CONFLICT", token)
            verified = self.verify_table(source_table)
            return {
                **existing,
                "commit_token": token,
                "table_input_digest": table_digest,
                "logical_digest": verified["state_digest"],
                "recovered": True,
            }
        self._check_preconditions(source_table, events)
        identifier = self.create_table(source_table)
        rows = [
            self._target_row(event, commit_token=token, row_sequence=index)
            for index, event in enumerate(events, 1)
        ]
        target_schema = self.spark.table(identifier).schema
        from pyspark.sql.types import StringType, StructField, StructType

        operation_field = StructField("_cb_operation", StringType())
        frame = self.spark.createDataFrame(
            rows, schema=StructType([*target_schema.fields, operation_field])
        )
        view = f"cb24_{token[:20]}"
        frame.createOrReplaceTempView(view)
        primary_key = BUSINESS_COLUMNS[source_table][0]
        columns = [field.name for field in target_schema.fields]
        update = ", ".join(f"t.{column}=s.{column}" for column in columns)
        insert_columns = ", ".join(columns)
        insert_values = ", ".join(f"s.{column}" for column in columns)
        statement = f"""
            MERGE INTO {identifier} t USING {view} s ON t.{primary_key}=s.{primary_key}
            WHEN MATCHED AND s._cb_operation='delete' THEN DELETE
            WHEN MATCHED AND s._cb_operation='update' THEN UPDATE SET {update}
            WHEN NOT MATCHED AND s._cb_operation='insert'
              THEN INSERT ({insert_columns}) VALUES ({insert_values})
        """
        properties = {
            "changebridge_commit_token": token,
            "changebridge_generation_id": generation_id,
            "changebridge_transaction_id": transaction_id,
            "changebridge_transaction_digest": transaction_digest,
            "changebridge_table_input_digest": table_digest,
            "changebridge_source_frontier": source_frontier,
            "changebridge_manifest_id": manifest_id,
            "changebridge_protocol_version": "1.0.0",
        }
        def commit_action() -> None:
            self.spark.sql(statement).collect()

        try:
            self._with_commit_properties(properties, commit_action)
        finally:
            self.spark.catalog.dropTempView(view)
        committed = self.snapshot_for_token(source_table, token)
        if committed is None:
            _fail("CB24I009_COMMIT_NOT_VISIBLE", token)
        verified = self.verify_table(source_table)
        return {
            **committed,
            "commit_token": token,
            "table_input_digest": table_digest,
            "logical_digest": verified["state_digest"],
            "recovered": False,
        }
