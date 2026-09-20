# ADR-013: Backfill and replay use successor generations

- Status: Accepted
- Authority: ChangeBridge Part 1 Stage 3
- Evidence class: `DESIGN_ONLY`
- Supersession: a later ADR must name and replace this decision explicitly

## Context

Repairing an active or rejected generation in place destroys auditability and can leak partial correction to consumers.

## Decision

Backfill, repair, and semantic replay create a new successor generation with lineage to its source generation and independent proof/publication. Exact transport retry before sealing may remain within the same generation only under the replay identity contract.

## Alternatives considered

- **Patch the active generation:** Reject: consumers observe partial repair.
- **Reopen rejected generation:** Reject: the original rejection evidence no longer describes the mutable object.
- **Clone without lineage:** Reject: audit and claim invalidation become untraceable.

## Consequences

- Storage and proof costs increase.
- Lineage is explicit.
- Historical evidence remains stable.

## Failure and recovery behavior

- Missing parent lineage blocks successor creation.
- Cross-generation write is rejected.
- Successor cannot inherit proof without recomputation.

## Traceability

- Requirements: `CB-ISOLATION-002`, `CB-APPLY-004`, `CB-EVIDENCE-001`
- Components: `generation_registry`, `migration_apply_engine`, `iceberg_generation_store`
- Proof obligation: Stage 4 must reject active-generation repair and inherited proof.

## Limitation

Successor-generation automation is unimplemented.
