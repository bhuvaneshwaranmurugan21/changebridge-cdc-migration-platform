"""Real local Spark/Iceberg adapter for Stage 3 snapshot generation."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from changebridge.contracts import semantic_digest

BUSINESS_COLUMNS = {
    "orders": ("order_id", "customer_id", "amount", "campaign_id", "source_note"),
    "order_items": (
        "item_id",
        "order_id",
        "quantity",
        "unit_price",
        "note",
        "created_at",
    ),
}


class IcebergSnapshotError(RuntimeError):
    pass


class IcebergSnapshotAdapter:
    """One generation-scoped filesystem catalog with real Iceberg commits."""

    def __init__(
        self,
        *,
        warehouse: Path,
        namespace: str,
        iceberg_jar: Path,
        app_name: str = "changebridge-stage23-snapshot",
    ) -> None:
        if not iceberg_jar.is_file():
            raise IcebergSnapshotError(f"CBI001_JAR_MISSING:{iceberg_jar}")
        warehouse.mkdir(parents=True, exist_ok=True)
        from pyspark.sql import SparkSession

        self.warehouse = warehouse
        self.namespace = namespace
        self.spark = (
            SparkSession.builder.master("local[2]")
            .appName(app_name)
            .config("spark.ui.enabled", "false")
            .config("spark.jars", str(iceberg_jar))
            .config(
                "spark.sql.extensions",
                "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions",
            )
            .config("spark.sql.catalog.stage23", "org.apache.iceberg.spark.SparkCatalog")
            .config("spark.sql.catalog.stage23.type", "hadoop")
            .config("spark.sql.catalog.stage23.warehouse", warehouse.as_uri())
            .config("spark.sql.session.timeZone", "UTC")
            .config("spark.sql.shuffle.partitions", "2")
            .getOrCreate()
        )
        self.spark.sparkContext.setLogLevel("WARN")
        self.spark.sql(f"CREATE NAMESPACE IF NOT EXISTS stage23.{namespace}")

    def close(self) -> None:
        self.spark.stop()

    def __enter__(self) -> IcebergSnapshotAdapter:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def identifier(self, table: str) -> str:
        if table not in BUSINESS_COLUMNS:
            raise IcebergSnapshotError(f"CBI002_UNKNOWN_TABLE:{table}")
        return f"stage23.{self.namespace}.{table}"

    def create_table(self, table: str) -> str:
        identifier = self.identifier(table)
        if table == "orders":
            business = """
              order_id STRING NOT NULL,
              customer_id STRING NOT NULL,
              amount BIGINT NOT NULL,
              campaign_id STRING,
              source_note STRING,
            """
        else:
            business = """
              item_id STRING NOT NULL,
              order_id STRING NOT NULL,
              quantity BIGINT NOT NULL,
              unit_price DECIMAL(38,2) NOT NULL,
              note STRING,
              created_at TIMESTAMP NOT NULL,
            """
        self.spark.sql(
            f"""
            CREATE TABLE IF NOT EXISTS {identifier} (
              {business}
              _cb_generation_id STRING NOT NULL,
              _cb_run_id STRING NOT NULL,
              _cb_source_system STRING NOT NULL,
              _cb_source_database STRING NOT NULL,
              _cb_source_schema STRING NOT NULL,
              _cb_source_table STRING NOT NULL,
              _cb_source_contract_id STRING NOT NULL,
              _cb_source_contract_version STRING NOT NULL,
              _cb_source_contract_digest STRING NOT NULL,
              _cb_source_schema_digest STRING NOT NULL,
              _cb_snapshot_frontier STRING NOT NULL,
              _cb_snapshot_batch STRING NOT NULL,
              _cb_row_sequence BIGINT NOT NULL,
              _cb_source_key STRING NOT NULL,
              _cb_row_digest STRING NOT NULL,
              _cb_shard_id STRING NOT NULL,
              _cb_commit_token STRING NOT NULL,
              _cb_event_id STRING NOT NULL
            ) USING iceberg
            TBLPROPERTIES ('format-version'='2')
            """
        )
        return identifier

    def _to_target_row(
        self,
        event: dict[str, Any],
        *,
        shard_id: str,
        commit_token: str,
        row_sequence: int,
    ) -> dict[str, Any]:
        table = str(event["source_table"])
        after = dict(event["after"])
        if table == "order_items":
            after["unit_price"] = Decimal(str(after["unit_price"]))
            after["created_at"] = (
                datetime.fromisoformat(str(after["created_at"]).replace("Z", "+00:00"))
                .astimezone(UTC)
                .replace(tzinfo=None)
            )
        primary_key = str(event["primary_key"][0]["value"])
        return {
            **after,
            "_cb_generation_id": event["generation_id"],
            "_cb_run_id": event["run_id"],
            "_cb_source_system": event["source_system"],
            "_cb_source_database": event["source_database"],
            "_cb_source_schema": event["source_schema"],
            "_cb_source_table": table,
            "_cb_source_contract_id": event["source_contract_id"],
            "_cb_source_contract_version": event["source_contract_version"],
            "_cb_source_contract_digest": event["source_contract_digest"],
            "_cb_source_schema_digest": event["source_schema_digest"],
            "_cb_snapshot_frontier": event["source_position"]["value"],
            "_cb_snapshot_batch": event["transaction_id"],
            "_cb_row_sequence": row_sequence,
            "_cb_source_key": primary_key,
            "_cb_row_digest": semantic_digest(event["after"], domain=f"stage23-source-row:{table}"),
            "_cb_shard_id": shard_id,
            "_cb_commit_token": commit_token,
            "_cb_event_id": event["event_id"],
        }

    def snapshot_for_token(self, table: str, commit_token: str) -> dict[str, Any] | None:
        identifier = self.identifier(table)
        if not self.spark.catalog.tableExists(identifier):
            return None
        rows = self.spark.sql(
            f"SELECT snapshot_id, operation, summary FROM {identifier}.snapshots "
            "ORDER BY committed_at"
        ).collect()
        for row in rows:
            summary = dict(row["summary"])
            if summary.get("changebridge_commit_token") == commit_token:
                return {
                    "snapshot_id": str(row["snapshot_id"]),
                    "operation": row["operation"],
                    "summary": summary,
                }
        return None

    def append_snapshot(
        self,
        *,
        table: str,
        events: list[dict[str, Any]],
        shard_id: str,
        commit_token: str,
        input_digest: str,
    ) -> dict[str, Any]:
        identifier = self.create_table(table)
        existing = self.snapshot_for_token(table, commit_token)
        if existing is not None:
            summary = existing["summary"]
            if summary.get("changebridge_input_digest") != input_digest:
                raise IcebergSnapshotError(f"CBI003_COMMIT_TOKEN_CONFLICT:{commit_token}")
            return {**existing, "recovered": True}
        target_rows = [
            self._to_target_row(
                event, shard_id=shard_id, commit_token=commit_token, row_sequence=index
            )
            for index, event in enumerate(events, 1)
        ]
        from pyspark.sql.types import (
            DecimalType,
            LongType,
            StringType,
            StructField,
            StructType,
            TimestampType,
        )

        if table == "orders":
            business_fields = [
                StructField("order_id", StringType(), False),
                StructField("customer_id", StringType(), False),
                StructField("amount", LongType(), False),
                StructField("campaign_id", StringType(), True),
                StructField("source_note", StringType(), True),
            ]
        else:
            business_fields = [
                StructField("item_id", StringType(), False),
                StructField("order_id", StringType(), False),
                StructField("quantity", LongType(), False),
                StructField("unit_price", DecimalType(38, 2), False),
                StructField("note", StringType(), True),
                StructField("created_at", TimestampType(), False),
            ]
        metadata_fields = [
            StructField(name, LongType() if name == "_cb_row_sequence" else StringType(), False)
            for name in (
                "_cb_generation_id",
                "_cb_run_id",
                "_cb_source_system",
                "_cb_source_database",
                "_cb_source_schema",
                "_cb_source_table",
                "_cb_source_contract_id",
                "_cb_source_contract_version",
                "_cb_source_contract_digest",
                "_cb_source_schema_digest",
                "_cb_snapshot_frontier",
                "_cb_snapshot_batch",
                "_cb_row_sequence",
                "_cb_source_key",
                "_cb_row_digest",
                "_cb_shard_id",
                "_cb_commit_token",
                "_cb_event_id",
            )
        ]
        frame = self.spark.createDataFrame(
            target_rows, schema=StructType([*business_fields, *metadata_fields])
        )
        (
            frame.writeTo(identifier)
            .option("snapshot-property.changebridge_commit_token", commit_token)
            .option("snapshot-property.changebridge_input_digest", input_digest)
            .option("snapshot-property.changebridge_shard_id", shard_id)
            .option("snapshot-property.changebridge_row_count", str(len(events)))
            .option(
                "snapshot-property.changebridge_generation_id",
                str(events[0]["generation_id"]),
            )
            .option(
                "snapshot-property.changebridge_source_frontier",
                str(events[0]["source_position"]["value"]),
            )
            .append()
        )
        committed = self.snapshot_for_token(table, commit_token)
        if committed is None:
            raise IcebergSnapshotError(f"CBI004_COMMIT_NOT_VISIBLE:{commit_token}")
        return {**committed, "recovered": False}

    def snapshot_count(self, table: str) -> int:
        identifier = self.identifier(table)
        if not self.spark.catalog.tableExists(identifier):
            return 0
        return int(self.spark.sql(f"SELECT * FROM {identifier}.snapshots").count())

    def logical_rows(self, table: str) -> list[dict[str, Any]]:
        identifier = self.identifier(table)
        columns = BUSINESS_COLUMNS[table]
        order_by = columns[0]
        rows = self.spark.sql(
            f"SELECT {', '.join(columns)} FROM {identifier} ORDER BY {order_by}"
        ).collect()
        result: list[dict[str, Any]] = []
        for row in rows:
            value = row.asDict(recursive=True)
            if table == "order_items":
                value["unit_price"] = format(value["unit_price"], ".2f")
                timestamp = value["created_at"].replace(tzinfo=UTC)
                value["created_at"] = timestamp.isoformat(timespec="microseconds").replace(
                    "+00:00", "Z"
                )
            result.append(value)
        return result

    def verify_table(self, table: str) -> dict[str, Any]:
        rows = self.logical_rows(table)
        return {
            "table": table,
            "row_count": len(rows),
            "state_digest": semantic_digest(rows, domain=f"source-table-state:{table}"),
            "snapshot_count": self.snapshot_count(table),
        }
