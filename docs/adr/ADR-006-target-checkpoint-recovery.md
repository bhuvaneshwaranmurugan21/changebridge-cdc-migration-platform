# ADR-006: Recover target commit and checkpoint without distributed ACID

- Status: Accepted
- Authority: ChangeBridge Part 1 Stage 3
- Evidence class: `DESIGN_ONLY`
- Supersession: a later ADR must name and replace this decision explicitly

## Context

Iceberg target commits and an external checkpoint ledger cannot truthfully be represented as one ACID transaction.

## Decision

Use a deterministic target commit identity, persist durable target receipt evidence, then conditionally advance the monotonic checkpoint. On ambiguous acknowledgement, reconcile the target receipt and ledger before deciding replay or completion.

## Alternatives considered

- **Claim one cross-system transaction:** Reject: no coordinator or atomic commit protocol exists.
- **Advance checkpoint before target commit:** Reject: data loss follows target failure.
- **Blindly retry after timeout:** Reject: a successful but unacknowledged commit may be duplicated.

## Consequences

- Commit receipts are correctness inputs.
- Recovery is an explicit state machine.
- Checkpoint is subordinate to durable target evidence.

## Failure and recovery behavior

- Crash before target durability leaves checkpoint unchanged.
- Commit-success/checkpoint-failure enters reconciliation.
- Unresolvable target outcome fails safe.

## Traceability

- Requirements: `CB-CHECKPOINT-001`, `CB-CHECKPOINT-002`, `CB-CHECKPOINT-003`
- Components: `migration_apply_engine`, `iceberg_generation_store`, `checkpoint_ledger`
- Proof obligation: Stage 4 must cover every crash boundary and ambiguous acknowledgement outcome.

## Limitation

This is a recoverable protocol design, not an implemented Iceberg/DynamoDB transaction.
