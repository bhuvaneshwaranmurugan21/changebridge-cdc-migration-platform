# Stage 3 failure modes

- Wrong generation, table, schema, contract, frontier, operation, or duplicate key: reject before
  target mutation.
- Identical replay: return the reconciled commit and create no new Iceberg snapshot.
- Same shard identity with changed content: terminal conflict; never overwrite.
- Failure before Iceberg commit: no target commit may be acknowledged.
- Iceberg commit without ledger acknowledgement: discover the immutable commit token in Iceberg,
  verify its input digest and logical result, then reconstruct the ledger without rewriting.
- Ledger entry without a matching Iceberg commit: fail closed and block admission.
- Partial table set: remain `SNAPSHOT_LOADING`.
- Path or namespace alias: reject before Spark writes.

Recovery never converts an unknown outcome into success and never mutates an active or foreign
generation.
