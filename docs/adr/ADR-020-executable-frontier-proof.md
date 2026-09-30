# ADR-020: Executable frozen-frontier proof

## Status

Accepted for Part 2 Stage 6.

## Decision

One candidate generation is sealed at PostgreSQL frontier `F = 0/194FE20`. Source and target
observations bind the same frontier, schema authority, and generation. Typed keyed-row hashes roll
up into deterministic buckets, tables, and one generation reconciliation digest. A separate
durable ledger permits only `CDC_APPLYING → SEALED → PROVING → PROVEN`.

Exactly eight independently bound gates are mandatory: continuity, schema, deletes,
reconciliation, lag, pre-migration, rollback readiness, and evidence integrity. Missing, failed,
stale, corrupted, or differently bound gates fail closed. Proof recovery reuses the immutable seal
and cannot mutate target data.

Because no incumbent generation exists, first publication keeps the active pointer absent until
Stage 7 compare-and-set succeeds. Failure restores pointer absence and source-system fallback. This
is not represented as rollback to a previously published generation.

## Boundary

Stage 6 proves bounded local correctness with PostgreSQL-history fixtures, Spark 3.5.9, Iceberg
1.11.0, a filesystem catalog, and SQLite. It performs no publication, active-pointer mutation,
cutover, rollback execution, AWS operation, performance experiment, or production claim.
