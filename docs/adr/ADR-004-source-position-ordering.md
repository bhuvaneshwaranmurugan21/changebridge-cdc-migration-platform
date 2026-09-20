# ADR-004: Order by source position and transaction sequence

- Status: Accepted
- Authority: ChangeBridge Part 1 Stage 3
- Evidence class: `DESIGN_ONLY`
- Supersession: a later ADR must name and replace this decision explicitly

## Context

Commit timestamps can collide, skew, or arrive out of order and cannot preserve deterministic intra-transaction order.

## Decision

The total order key is source position plus transaction sequence and event sequence under a versioned comparator. Commit time is observability metadata only.

## Alternatives considered

- **Commit timestamp only:** Reject: it cannot prove total or causal order.
- **Arrival order:** Reject: retries and parallel transport make it nondeterministic.

## Consequences

- Comparator version is persisted.
- Unsupported position types are rejected.
- Parallel apply may not violate transaction order.

## Failure and recovery behavior

- Duplicate order keys with different payloads are conflicts.
- Comparator disagreement blocks progress.
- Partial transactions are never checkpointed.

## Traceability

- Requirements: `CB-ORDER-002`, `CB-ORDER-003`, `CB-ORDER-004`
- Components: `manifest_normalizer`, `migration_apply_engine`, `checkpoint_ledger`
- Proof obligation: Ordering contracts must permute arrival order and preserve identical canonical results.

## Limitation

Managed transport ordering is not locally proven.
