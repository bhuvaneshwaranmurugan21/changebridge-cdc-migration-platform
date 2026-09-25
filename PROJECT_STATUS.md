# ChangeBridge project status

## Current authorized boundary

- Part: 2 — Executable local migration path
- Stage: 3 — Snapshot loader and isolated Iceberg generation
- Verified entry commit: `9382f8150c5af1de1bcdc8494fda6212c1d0b18b`
- Verified entry tree: `5e98c6a8fe03e0dd5e6e01ca5508943743782435`
- Predecessor checkpoint: `PART2_STAGE2_CDC_NORMALIZATION_VERIFIED`
- Stage branch: `part2-stage3-snapshot-generation`
- Stage evidence: `evidence/part2/stage3/`

## Candidate result

`PART2_STAGE3_SNAPSHOT_GENERATION_PENDING_EXTERNAL_CLOSURE`

The complete accepted six-row `orders` and 66-row `order_items` snapshot passes through the
unchanged Stage 2 normalizer and is written by real local Spark into generation-owned Iceberg
format-version-2 tables. Same-input replay is a no-op, altered input fails closed, and a process
terminated after Iceberg commit recovers from durable commit metadata without rewriting.

The result is limited to `LOCAL_VERIFIED`. No AWS, S3/Glue durability, post-`S` CDC application,
schema evolution, publication, Terraform, performance, availability, exactly-once, zero-downtime,
or production-readiness claim is made.

The in-repository receipt holds `ST23-AC-01` through `ST23-AC-38` as candidate-pass and leaves
exact PR-head, merge, post-merge, and external checkpoint criteria `ST23-AC-39` through
`ST23-AC-42` pending external closure.

## Next permitted action

Generate commit-bound evidence from the real-target lab, publish the exact candidate, validate
every required GitHub check on that head, merge with an expected-head guard, verify fresh merged
`main`, and issue `PART2_STAGE3_SNAPSHOT_GENERATION_VERIFIED`. Stage 4 remains unauthorized.
