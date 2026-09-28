"""Atomic local Iceberg schema application and recovery identity."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, NoReturn

from changebridge.contracts import semantic_digest
from changebridge.schema_policy import FieldDefinition, SchemaDecision


class IcebergSchemaError(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


def _fail(code: str, detail: str) -> NoReturn:
    raise IcebergSchemaError(code, detail)


class IcebergSchemaAdapter:
    def __init__(self, *, warehouse: Path, iceberg_jar: Path) -> None:
        if not iceberg_jar.is_file():
            _fail("CB25I001_JAR_MISSING", str(iceberg_jar))
        warehouse.mkdir(parents=True, exist_ok=True)
        from pyspark.sql import SparkSession

        self.spark = (
            SparkSession.builder.master("local[2]")
            .appName("changebridge-stage25-schema")
            .config("spark.ui.enabled", "false")
            .config("spark.jars", str(iceberg_jar))
            .config(
                "spark.sql.extensions",
                "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions",
            )
            .config("spark.sql.catalog.stage25", "org.apache.iceberg.spark.SparkCatalog")
            .config("spark.sql.catalog.stage25.type", "hadoop")
            .config("spark.sql.catalog.stage25.warehouse", warehouse.as_uri())
            .config("spark.sql.session.timeZone", "UTC")
            .config("spark.sql.shuffle.partitions", "2")
            .getOrCreate()
        )
        self.spark.sparkContext.setLogLevel("WARN")
        self.spark.sql("CREATE NAMESPACE IF NOT EXISTS stage25.rehearsal")
        self.identifier = "stage25.rehearsal.orders"

    def __enter__(self) -> IcebergSchemaAdapter:
        return self

    def __exit__(self, *_: object) -> None:
        self.spark.stop()

    def create_predecessor(self, rows: list[dict[str, Any]]) -> None:
        self.spark.sql(
            f"""CREATE TABLE IF NOT EXISTS {self.identifier} (
                order_id STRING NOT NULL,
                customer_id STRING NOT NULL,
                amount BIGINT NOT NULL,
                campaign_id STRING
            ) USING iceberg TBLPROPERTIES ('format-version'='2')"""
        )
        if self.spark.table(self.identifier).count() == 0:
            from pyspark.sql.types import LongType, StringType, StructField, StructType

            frame = self.spark.createDataFrame(
                rows,
                schema=StructType(
                    [
                        StructField("order_id", StringType(), False),
                        StructField("customer_id", StringType(), False),
                        StructField("amount", LongType(), False),
                        StructField("campaign_id", StringType(), True),
                    ]
                ),
            )
            frame.select("order_id", "customer_id", "amount", "campaign_id").writeTo(
                self.identifier
            ).append()

    def _table(self) -> Any:
        jvm = self.spark.sparkContext._jvm
        if jvm is None:
            _fail("CB25I002_JVM_MISSING", self.identifier)
        return jvm.org.apache.iceberg.spark.Spark3Util.loadIcebergTable(
            self.spark._jsparkSession, self.identifier
        )

    def metadata(self) -> dict[str, Any]:
        table = self._table()
        table.refresh()
        properties = {
            str(row.getKey()): str(row.getValue()) for row in table.properties().entrySet()
        }
        return {
            "schema_id": int(table.schema().schemaId()),
            "metadata_location": str(table.operations().current().metadataFileLocation()),
            "properties": properties,
            "snapshot_count": int(
                self.spark.sql(f"SELECT * FROM {self.identifier}.snapshots").count()
            ),
        }

    @staticmethod
    def apply_token(decision: SchemaDecision) -> str:
        return semantic_digest(
            {
                "generation_id": decision.generation_id,
                "source_table": decision.source_table,
                "previous_digest": decision.previous.digest,
                "candidate_digest": decision.candidate.digest,
                "policy_digest": decision.policy_digest,
                "decision_digest": decision.decision_digest,
            },
            domain="stage25-schema-apply-token",
        )

    def apply(self, decision: SchemaDecision) -> dict[str, Any]:
        if decision.verdict != "COMPATIBLE":
            _fail("CB25I003_DECISION_NOT_COMPATIBLE", decision.decision_id)
        token = self.apply_token(decision)
        before = self.metadata()
        existing_token = before["properties"].get("changebridge.schema-apply-token")
        if existing_token is not None:
            if (
                existing_token != token
                or before["properties"].get("changebridge.schema-candidate-digest")
                != decision.candidate.digest
            ):
                _fail("CB25I004_APPLY_TOKEN_CONFLICT", token)
            return {**before, "apply_token": token, "recovered": True}
        if len(decision.added_fields) != 1:
            _fail("CB25I005_UNSUPPORTED_CHANGE_SET", repr(decision.added_fields))
        field = decision.added_fields[0]
        if not field.nullable or field.name in {row.name for row in decision.candidate_primary_key}:
            _fail("CB25I006_UNSUPPORTED_FIELD", field.name)
        self._commit(decision, field, token)
        after = self.metadata()
        if after["properties"].get("changebridge.schema-apply-token") != token:
            _fail("CB25I007_COMMIT_NOT_VISIBLE", token)
        if after["snapshot_count"] != before["snapshot_count"]:
            _fail("CB25I008_SCHEMA_CREATED_DATA_SNAPSHOT", token)
        return {**after, "apply_token": token, "recovered": False}

    def _commit(self, decision: SchemaDecision, field: FieldDefinition, token: str) -> None:
        table = self._table()
        jvm = self.spark.sparkContext._jvm
        assert jvm is not None
        types: Mapping[str, Any] = {
            "string": jvm.org.apache.iceberg.types.Types.StringType.get(),
            "integer": jvm.org.apache.iceberg.types.Types.LongType.get(),
            "boolean": jvm.org.apache.iceberg.types.Types.BooleanType.get(),
        }
        iceberg_type = types.get(field.data_type)
        if iceberg_type is None:
            _fail("CB25I009_TYPE_MAPPING", field.data_type)
        try:
            transaction = table.newTransaction()
            transaction.updateSchema().addColumn(field.name, iceberg_type).commit()
            (
                transaction.updateProperties()
                .set("changebridge.schema-apply-token", token)
                .set("changebridge.schema-decision-id", decision.decision_id)
                .set("changebridge.schema-policy-digest", decision.policy_digest)
                .set("changebridge.schema-candidate-digest", decision.candidate.digest)
                .commit()
            )
            transaction.commitTransaction()
        except Exception as exc:
            _fail("CB25I010_SCHEMA_COMMIT_FAILED", type(exc).__name__)

    def logical_rows(self) -> list[dict[str, Any]]:
        return [
            row.asDict(recursive=True)
            for row in self.spark.sql(
                f"SELECT order_id,customer_id,amount,campaign_id,source_note "
                f"FROM {self.identifier} ORDER BY order_id"
            ).collect()
        ]
