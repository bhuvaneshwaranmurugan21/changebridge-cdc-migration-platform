# Stage 3 local runbook

Prerequisites are Java 17, Python 3.11 or 3.12, the repository development and Spark extras, and
the Iceberg JAR whose SHA-256 is locked in `contracts/stage3-runtime-lock.json`.

1. Verify the JAR digest before starting Spark.
2. Build the full handoff and run the unchanged normalizer.
3. Register the deterministic generation and transition it from `CREATED` to `SNAPSHOT_LOADING`.
4. Run `jobs/spark_iceberg_snapshot.py` once for `orders` and once for `order_items`.
5. Replay both commands and confirm no new Iceberg snapshot appears.
6. Compare table counts and logical digests with the independent source oracle.
7. Record the admission proof and transition to `CDC_APPLYING`.

Never delete or rewrite a warehouse to resolve a conflict. A ledger/Iceberg disagreement blocks
admission until durable metadata proves the outcome.
