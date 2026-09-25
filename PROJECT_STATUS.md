# ChangeBridge project status

## Current authorized boundary

- Part: 2 — Executable local migration path
- Stage: 2 — CDC capture and governed-envelope normalization
- Verified entry commit: `006a74119ebc4edc050e31ae171ca8d9fbe8b669`
- Verified entry tree: `745f25fc394fd06c339ee22b432e3f8f26d5035d`
- Predecessor checkpoint: `PART2_STAGE1_SOURCE_BOUNDARY_VERIFIED`
- Stage branch: `part2-stage2-dms-normalizer`
- Stage evidence: `evidence/part2/stage2/`

## Candidate result

`PART2_STAGE2_CDC_NORMALIZATION_PENDING_EXTERNAL_CLOSURE`

The local adapter validates immutable manifests, explicit profile capabilities, source/schema
identity, generation/run lineage, typed PostgreSQL LSN boundaries, full before/after images,
transaction/event order, deterministic replay identity, quarantine partitioning, and atomic output.
JSON, JSONL, and Parquet fixtures are transparently synthetic and reproduce deterministically.

The result is limited to `LOCAL_VERIFIED`. No AWS DMS, S3, target apply, Spark, Iceberg,
checkpoint, reconciliation, Terraform, performance, availability, exactly-once, zero-downtime, or
production-readiness claim is made.

The in-repository receipt holds `ST22-AC-01` through `ST22-AC-40` as candidate-pass and leaves exact
PR-head, merge, post-merge, and external checkpoint criteria `ST22-AC-41` through `ST22-AC-44`
pending external closure.

## Next permitted action

Publish the exact candidate, validate every required GitHub check on that head, merge with an
expected-head guard, verify fresh merged `main`, and issue
`PART2_STAGE2_CDC_NORMALIZATION_VERIFIED`. Stage 3 execution remains unauthorized.
