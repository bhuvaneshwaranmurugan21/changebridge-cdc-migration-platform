# ChangeBridge Part 2 Completion Contract

## Purpose

Part 2 converts the accepted Part 1 correctness authority into an executable, locally proven
migration path. Completion is evidence-driven: a service, script, or green command is not proof
unless its inputs, repository state, result, limitations, and owning requirement are bound in a
validated receipt.

## Evidence boundary

Part 2 may establish `LOCAL_VERIFIED` behavior against isolated PostgreSQL and local target
components. It cannot establish `AWS_VERIFIED`, production readiness, throughput, availability,
RTO/RPO, cost, zero downtime, or exactly-once delivery without separately authorized managed
proof. Every stage must retain those limitations.

## Ordered stages

| Stage | Completion unit | Required continuation status |
|---:|---|---|
| 1 | Deterministic source workload and exported-snapshot boundary | `PART2_STAGE1_SOURCE_BOUNDARY_VERIFIED` |
| 2 | CDC capture and governed envelope normalization | `PART2_STAGE2_CDC_NORMALIZATION_VERIFIED` |
| 3 | Snapshot loader and isolated Iceberg generation | `PART2_STAGE3_SNAPSHOT_GENERATION_VERIFIED` |
| 4 | Transaction-aware CDC apply and checkpoint recovery | `PART2_STAGE4_CDC_APPLY_VERIFIED` |
| 5 | Schema and primary-key change policy | `PART2_STAGE5_SCHEMA_POLICY_VERIFIED` |
| 6 | Frontier reconciliation and sealed proof | `PART2_STAGE6_RECONCILIATION_VERIFIED` |
| 7 | Orchestration, publication, rollback, and Part 2 closure | `PART2_COMPLETION_VERIFIED` |

Stages are sequential. A later stage consumes the exact merged checkpoint of its predecessor and
must not reinterpret source identity, canonicalization, generation identity, transaction order,
or the half-open boundary `(S,F]`.

## Stage 1 completion rule

Stage 1 is complete only when all of the following are true:

1. `ST21-AC-01` through `ST21-AC-37` pass on one exact pull-request head.
2. The real PostgreSQL lane runs, rather than skips, against the digest-pinned official image.
3. The reviewed head is merged under the repository's existing policy.
4. `ST21-AC-38` through `ST21-AC-40` pass against fresh merged `main`.
5. The external continuation checkpoint names the exact merge commit and tree.

A skipped, waived, stale, manually asserted, or partially evidenced criterion is a failure.

## Stage 1 authority

The machine-readable acceptance authority is
`requirements/part2-stage1-acceptance.json`. The source runtime proof is bound to a pre-evidence
source-freeze commit because a committed manifest cannot contain its own final commit identity.
Exact PR-head, merge, and post-merge identities are verified externally through GitHub and the
continuation checkpoint.

## Stage 1 exclusions

Stage 1 does not implement AWS DMS, Spark, Iceberg, Glue, Step Functions, DynamoDB, Terraform,
deployment, performance testing, release, or tagging. It does not change target-apply behavior.

## Stage 2 completion rule

Stage 2 is complete only when `ST22-AC-01` through `ST22-AC-40` pass on one source-freeze
commit/tree, `ST22-AC-41` passes on the exact reviewed pull-request head, the guarded policy merge
succeeds, fresh merged `main` satisfies `ST22-AC-42` and `ST22-AC-43`, and an external
`PART2_STAGE2_CDC_NORMALIZATION_VERIFIED` checkpoint satisfies `ST22-AC-44`.

The Stage 2 claim ceiling is one explicit local synthetic DMS/S3-shaped profile. JSON, JSONL, and
Parquet fixture normalization, quarantine, identity, ordering, and atomic output are locally
verified; AWS DMS emission, S3 delivery, managed recovery, target application, and production
properties remain unclaimed.

The machine-readable authority is `requirements/part2-stage2-acceptance.json`. Repository evidence
binds to a pre-evidence source-freeze commit to avoid recursive commit and manifest identities.

## Stage 3 authority correction

The prior table incorrectly assigned transaction-preserving landing to Stage 3 even though Stage 2
already owns normalized transaction/event identity and ordering. ADR-017 corrects the sequence
without changing any completed Stage 1 or Stage 2 contract, evidence, or checkpoint. No obligation
is removed: CDC application moves to Stage 4, schema policy to Stage 5, final reconciliation to
Stage 6, and publication/rollback to Stage 7.

## Stage 3 completion rule

Stage 3 is complete only when `ST23-AC-01` through `ST23-AC-38` pass on the bound source-freeze
commit/tree, `ST23-AC-39` passes on the exact reviewed pull-request head, the expected-head policy
merge satisfies `ST23-AC-40`, fresh merged `main` satisfies `ST23-AC-41`, and an external
`PART2_STAGE3_SNAPSHOT_GENERATION_VERIFIED` checkpoint satisfies `ST23-AC-42`.

Stage 3 may load only the complete accepted snapshot at `S` into an unpublished, generation-owned
local Iceberg namespace. It must preserve post-`S` canonical CDC for Stage 4 but cannot apply it or
advance a CDC checkpoint. Its claim ceiling is `LOCAL_VERIFIED` for the checksum-pinned local
Spark/Iceberg profile; it establishes no AWS, performance, availability, exactly-once,
zero-downtime, or production-readiness property.

The machine-readable authority is `requirements/part2-stage3-acceptance.json`. Repository evidence
binds to a pre-evidence source-freeze commit to avoid recursive commit and manifest identities.

## Failure and correction policy

- Failures preserve their original diagnostics and are corrected through reviewable commits.
- A failed snapshot attempt cannot be relabeled successful or reused for another generation.
- Part 1 evidence remains immutable and is validated both historically and by current-tree digest.
- Authority changes require a named transition record with old/new behavior and affected claims.
- After merge, a correctness defect requires a corrective or revert pull request; history is not
  rewritten.
