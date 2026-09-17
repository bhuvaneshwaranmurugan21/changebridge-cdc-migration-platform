# ADR-005: Deterministic replay identity and conflicting duplicates

- Status: Accepted
- Authority: ChangeBridge Part 1 Stage 3
- Evidence class: `DESIGN_ONLY`
- Supersession: a later ADR must name and replace this decision explicitly

## Context

At-least-once delivery makes duplicates normal, but transaction-ID reuse with different content indicates corruption or an unstable canonicalization.

## Decision

Replay identity is source identity, generation, transaction ID, terminal source position, and canonical payload digest. Exact matches are no-ops; same identity with another digest is a terminal conflict for that apply attempt.

## Alternatives considered

- **Deduplicate by transaction ID only:** Reject: conflicting payloads can be silently discarded.
- **Always reapply:** Reject: non-idempotent updates and deletes can corrupt state.

## Consequences

- Canonical serialization is versioned.
- Transaction receipts are retained.
- Conflict is distinguished from ordinary replay.

## Failure and recovery behavior

- Digest conflict quarantines the generation.
- Missing identity blocks apply.
- Receipt lookup ambiguity fails safe.

## Traceability

- Requirements: `CB-APPLY-004`, `CB-APPLY-005`, `CB-ORDER-003`
- Components: `manifest_normalizer`, `migration_apply_engine`, `checkpoint_ledger`
- Proof obligation: Property and differential tests must prove identical replay and conflicting replay behavior.

## Limitation

The target managed transaction ledger is not implemented.
