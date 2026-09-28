# ChangeBridge project status

## Current authorized boundary

- Part: 2 — Executable local migration path
- Stage: 5 — Recoverable schema and primary-key policy
- Verified entry commit: `cbf575315e3b9bea3c0ee79f78e3288c8746effb`
- Verified entry tree: `30e26dd3d7cd89601de92bc6ec99ec0e1a2737f0`
- Predecessor checkpoint: `PART2_STAGE4_CDC_APPLY_VERIFIED`
- Stage branch: `part2-stage5-schema-policy`
- Stage evidence: `evidence/part2/stage5/`

## Candidate result

`PART2_STAGE5_SCHEMA_POLICY_PENDING_EXTERNAL_CLOSURE`

The governed `orders_source_contract/1.0.0` to `1.1.0` transition adds nullable non-key field
`source_note` using one real Iceberg metadata transaction. Existing rows read null. Process loss
after the Iceberg commit recovers the exact schema receipt from its deterministic token without a
second metadata commit. Unknown changes quarantine before mutation; incompatible schema or key
changes quarantine and reject the candidate generation.

The result is limited to `LOCAL_VERIFIED`. The compatible generation remains unpublished,
unsealed, and in `CDC_APPLYING`; the checkpoint stays `0/194FE20`. No AWS or Glue durability,
arbitrary schema evolution, implicit coercion/defaulting, publication, reconciliation,
performance, availability, zero-downtime, or production-readiness claim is made.

The in-repository receipt holds `ST25-AC-01` through `ST25-AC-44` as candidate-pass and leaves
guarded merge, merged-main identity, post-merge validation, and external checkpoint criteria
`ST25-AC-45` through `ST25-AC-48` pending external closure.

## Next permitted action

Publish the exact candidate, validate every required GitHub check on that head, merge with an
expected-head guard, verify fresh merged `main`, and issue
`PART2_STAGE5_SCHEMA_POLICY_VERIFIED`.
Stage 6 remains outside this stage's authority.
