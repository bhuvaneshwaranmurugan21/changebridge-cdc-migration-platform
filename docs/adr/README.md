# Architecture decisions

All decisions are `Accepted` and `DESIGN_ONLY`.
The machine-readable index is `architecture/adr-index.json`.

- [ADR-001: Generation is the isolation and publication unit](ADR-001-generation-isolation-unit.md)
- [ADR-002: Snapshot frontier S and CDC interval (S,F]](ADR-002-snapshot-cdc-boundary.md)
- [ADR-003: Transport-neutral canonical CDC envelope](ADR-003-canonical-cdc-envelope.md)
- [ADR-004: Order by source position and transaction sequence](ADR-004-source-position-ordering.md)
- [ADR-005: Deterministic replay identity and conflicting duplicates](ADR-005-replay-identity-conflicts.md)
- [ADR-006: Recover target commit and checkpoint without distributed ACID](ADR-006-target-checkpoint-recovery.md)
- [ADR-007: Represent deletes with auditable tombstones](ADR-007-delete-tombstone-retention.md)
- [ADR-008: Version schema identity and quarantine incompatible drift](ADR-008-schema-compatibility-quarantine.md)
- [ADR-009: Reconcile canonical rows hierarchically at one frontier](ADR-009-hierarchical-reconciliation.md)
- [ADR-010: Provide consumer consistency through generation resolution](ADR-010-consumer-generation-consistency.md)
- [ADR-011: Publish with expected-revision compare-and-swap](ADR-011-cas-publication.md)
- [ADR-012: Rollback republishes an eligible prior generation](ADR-012-rollback-eligibility.md)
- [ADR-013: Backfill and replay use successor generations](ADR-013-backfill-replay-isolation.md)
- [ADR-014: Bind decisions through immutable evidence manifests](ADR-014-evidence-manifest-binding.md)
- [ADR-015: Retain evidence and retire generations with explicit guards](ADR-015-retention-retirement.md)

A later ADR must explicitly name any superseded record and trigger
requirement, claim, model, diagram, and validation review.
