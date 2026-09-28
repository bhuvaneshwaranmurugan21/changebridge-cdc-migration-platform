# ChangeBridge project status

## Current authorized boundary

- Part: 2 — Executable local migration path
- Stage: 4 — Recoverable transactional CDC apply
- Verified entry commit: `e9b4a6dc6d62c1c90a89ea4ba3c02ad6a0d6a601`
- Verified entry tree: `775b6790edd7b671091e32b0e2787374e4bcb429`
- Predecessor checkpoint: `PART2_STAGE3_SNAPSHOT_GENERATION_VERIFIED`
- Stage branch: `part2-stage4-transactional-apply`
- Stage evidence: `evidence/part2/stage4/`

## Candidate result

`PART2_STAGE4_CDC_APPLY_PENDING_EXTERNAL_CLOSURE`

The accepted transaction `tx-012-post-boundary` advances the candidate from `0/194FB20` to
`0/194FE20`. Real Spark/Iceberg and an independent SQLite reference finish with identical six-row
orders and 66-row order-items digests. A process terminated after Iceberg commit leaves the
checkpoint at `S` and recovers by commit token without a second target write.

The result is limited to `LOCAL_VERIFIED`. The generation remains unpublished in `CDC_APPLYING`.
No AWS or S3/Glue durability, atomic cross-table storage transaction, production exactly-once,
schema/key evolution, publication, performance, availability, zero-downtime, or
production-readiness claim is made.

The in-repository receipt holds `ST24-AC-01` through `ST24-AC-44` as candidate-pass and leaves
guarded merge, merged-main identity, post-merge validation, and external checkpoint criteria
`ST24-AC-45` through `ST24-AC-48` pending external closure.

## Next permitted action

Publish the exact candidate, validate every required GitHub check on that head, merge with an
expected-head guard, verify fresh merged `main`, and issue `PART2_STAGE4_CDC_APPLY_VERIFIED`.
Stage 5 remains outside this stage's authority.
