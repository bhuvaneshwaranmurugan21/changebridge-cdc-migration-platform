# ADR-021: Bind publication to an execution-present physical proof

## Status

Accepted for Part 2 Stage 7; supersedes any interpretation that an accepted logical proof alone
authorizes publication after its physical warehouse has vanished.

## Context

The accepted Stage 6 evidence remains valid proof of the logical generation at frontier
`0/194FE20`, but its disposable Iceberg warehouse no longer exists. Publishing replacement
snapshots under the old snapshot identities would be false; publishing unproven replacement
snapshots would break the proof-before-publication invariant.

## Decision

Stage 7 reconstructs `generation-34edddda5aee96dc7236aaf3` solely from accepted immutable
inputs, reruns the unchanged eight-gate proof against that exact physical materialization, and
creates a publication-binding manifest. The binding chains the accepted Stage 6 proof digest,
the fresh execution proof digest, the unchanged reconciliation digest, and the complete physical
table map. New Iceberg snapshot IDs and manifest-list digests are first-class identities.

The publication controller registers only that binding. One durable monotonic revision exists
even while the active pointer is absent. Publication, ordinary rollback, and first-publication
fallback are explicit expected-revision transitions with immutable attempt IDs. Ambiguous
acknowledgements are reconciled by attempt ID; they are never retried as new decisions.

Consumers pin one revision, one generation, and its complete table map before reading. A failed
post-publication consumer verification enters an incident state and cannot silently auto-fallback.

## Consequences

- Existing Stage 6 evidence remains byte-identical and retains its logical authority.
- Fresh physical identities are disclosed rather than confused with vanished snapshots.
- Pointer absence cannot reset the revision, preventing ABA publication.
- First-publication fallback restores source routing, not a nonexistent prior target generation.
- The proof is bounded to local Spark, Iceberg, filesystem storage, and SQLite.
