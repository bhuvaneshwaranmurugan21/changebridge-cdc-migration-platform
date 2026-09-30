# ChangeBridge project status

## Current authorized boundary

- Part: 2 — Executable local migration path
- Stage: 6 — Frozen-frontier reconciliation proof
- Verified entry commit: `7b5e71c68c52766affd68d0a2c6087656b447c31`
- Verified entry tree: `62ed362e52a7d5fb3ccc8aa30085211980c1ca7d`
- Predecessor checkpoint: `PART2_STAGE5_SCHEMA_POLICY_VERIFIED`
- Stage branch: `part2-stage6-reconciliation-proof`
- Stage evidence: `evidence/part2/stage6/`

## Candidate result

`PART2_STAGE6_RECONCILIATION_PENDING_EXTERNAL_CLOSURE`

The candidate is reconciled at `F = 0/194FE20`. Typed keyed-row proofs roll up through deterministic
buckets and tables. Exact Iceberg snapshots, schema authority, deletes, lag, pre-migration,
first-publication rollback readiness, and evidence integrity form eight mandatory gates. The
durable sequence is `CDC_APPLYING → SEALED → PROVING → PROVEN`.

The result is `LOCAL_VERIFIED`. The generation remains unpublished and inactive. First-publication
rollback restores an absent pointer and source fallback; it is not rollback to a previously
published generation. No AWS, managed durability, publication, cutover, rollback execution,
performance, availability, zero-downtime, or production-readiness claim is made.

The receipt holds `ST26-AC-01` through `ST26-AC-48` as candidate-pass and leaves
guarded merge, merged-main identity, post-merge validation, and external checkpoint criteria
`ST26-AC-49` through `ST26-AC-52` pending external closure.

## Next permitted action

Publish the exact candidate, validate every required GitHub check on that head, merge with an
expected-head guard, verify fresh merged `main`, and issue
`PART2_STAGE6_RECONCILIATION_VERIFIED`.
Stage 7 remains outside this stage's authority.
