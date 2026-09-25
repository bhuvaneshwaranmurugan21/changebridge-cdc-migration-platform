# Stage 3 skeptical review

## What is proven

A real local Spark 3.5.9 process writes complete bounded snapshot data to real Iceberg 1.11.0
format-version-2 tables. Replays are no-ops, a killed process after target commit recovers from
Iceberg metadata, and admission requires count and canonical-digest agreement at `S`.

## What is not proven

The filesystem Hadoop catalog is not S3 or Glue. SQLite is not a distributed control plane. The
test is correctness-focused, not a performance or availability measurement. Stage 3 does not apply
CDC, publish a generation, support schema evolution, or claim exactly-once delivery.

## Strongest challenge

Iceberg and SQLite cannot commit atomically. The design therefore uses a deterministic commit token
persisted in Iceberg snapshot metadata as the recovery authority for the ambiguous gap. If Iceberg
cannot prove that token and digest, the loader blocks rather than guessing.
