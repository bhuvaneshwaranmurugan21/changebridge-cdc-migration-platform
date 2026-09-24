# Stage 1 Source-Boundary Authority

## Problem

A snapshot plus a CDC stream is not complete merely because both ran. The snapshot must be tied to
the exact position from which decoding continues. Stage 1 makes that handoff executable against
real PostgreSQL.

## Qualified boundary procedure

1. Materialize and validate the complete deterministic workload before execution.
2. Execute the pre-boundary transactions in an isolated schema.
3. Open a PostgreSQL logical-replication connection and create a generation-scoped slot with
   `SNAPSHOT 'export'` and the `test_decoding` output plugin.
4. Treat the returned consistent point as the single immutable typed frontier `S`.
5. While the exporter remains open, start a separate read-only, repeatable-read transaction and
   import the exact returned snapshot name.
6. Query every governed table in stable primary-key order and calculate canonical table and
   whole-state digests inside that transaction.
7. Close the imported transaction and exporter only after the governed read completes.
8. Execute the declared post-boundary transaction and consume the logical slot without a start
   filter that could hide changes.
9. Bind the first decoded transaction's **COMMIT LSN** as its governed source position and require
   it to compare strictly greater than `S`.
10. Drop the slot and prove cleanup in the receipt.

The first row-change record may carry an LSN equal to the slot's consistent point. That record is
not used as the transaction frontier. Transaction ordering is governed by the corresponding COMMIT
LSN, which is strictly after `S` in the qualified procedure.

## Workload contract lifecycle

`contracts/source-workload-spec-v1.json` is the pre-execution specification. It contains seed,
schema-set digest, logical clock, driver version, explicit transactions, and concurrency schedule.
It excludes physical LSN, PostgreSQL transaction ID, host/container identity, wall-clock time, and
temporary paths.

The pre-existing `contracts/source-workload-v1.schema.json` remains a completed-run receipt
authority. Stage 1 does not reinterpret it. The specification/receipt distinction is additive.

## Determinism

Equal seeds must reproduce equal workload IDs, transaction/event digests, histories, and canonical
states. They are not expected to reproduce equal WAL addresses. Every physical LSN is bound to its
own execution receipt and source identity.

## Governed source cases

The workload covers single and multi-row inserts, update, delete, multi-table commit, deterministic
concurrent writers, a bounded large transaction, null/value distinction, Unicode, exact decimal,
UTC timestamp edges, controlled schema change, and an aborted transaction. The independent replay
oracle and queried PostgreSQL state must match exactly.

## Evidence boundary

This stage proves the source side locally against the pinned PostgreSQL 17.11 image. It does not
prove DMS checkpoint mapping, delivery, target application, Iceberg behavior, or any managed,
performance, availability, cost, or production property.
