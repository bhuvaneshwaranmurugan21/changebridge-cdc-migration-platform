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
| 3 | Transaction-preserving landing and ordering | `PART2_STAGE3_TRANSACTION_LANDING_VERIFIED` |
| 4 | Idempotent target apply and checkpoint coupling | `PART2_STAGE4_TARGET_APPLY_VERIFIED` |
| 5 | Schema evolution, quarantine, and deterministic restart | `PART2_STAGE5_RECOVERY_VERIFIED` |
| 6 | Reconciliation and proof-manifest construction | `PART2_STAGE6_RECONCILIATION_VERIFIED` |
| 7 | Local cutover, rollback, and Part 2 closure | `PART2_COMPLETION_VERIFIED` |

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

## Failure and correction policy

- Failures preserve their original diagnostics and are corrected through reviewable commits.
- A failed snapshot attempt cannot be relabeled successful or reused for another generation.
- Part 1 evidence remains immutable and is validated both historically and by current-tree digest.
- Authority changes require a named transition record with old/new behavior and affected claims.
- After merge, a correctness defect requires a corrective or revert pull request; history is not
  rewritten.
