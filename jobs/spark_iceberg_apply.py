"""Production-shaped Spark adapter; the correctness policy lives in changebridge.engine.

This file is intentionally not called by local evidence. In AWS, orchestration supplies a
validated contiguous manifest and commits its transaction-preserving changes to an Iceberg
candidate generation. Managed-service verification remains an explicit outstanding claim.
"""

from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest-uri", required=True)
    parser.add_argument("--catalog", default="glue_catalog")
    parser.add_argument("--database", required=True)
    parser.add_argument("--generation-id", required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        from pyspark.sql import SparkSession
    except ImportError as error:
        raise SystemExit("install the spark extra to run this adapter") from error
    spark = SparkSession.builder.appName(f"changebridge-{args.generation_id}").getOrCreate()
    changes = spark.read.json(args.manifest_uri)
    required = {"table", "record_key", "operation", "commit_lsn", "transaction_id"}
    missing = required - set(changes.columns)
    if missing:
        raise ValueError(f"manifest records missing columns: {sorted(missing)}")
    # One transaction-preserving input manifest maps to one candidate-table commit.
    # MERGE SQL is table-specific and generated only after contract validation.
    changes.createOrReplaceTempView("validated_cdc_changes")
    spark.sql("SELECT count(*) AS validated_change_count FROM validated_cdc_changes").show()
    spark.stop()


if __name__ == "__main__":
    main()
