# ADR-007: Represent deletes with auditable tombstones

- Status: Accepted
- Authority: ChangeBridge Part 1 Stage 3
- Evidence class: `DESIGN_ONLY`
- Supersession: a later ADR must name and replace this decision explicitly

## Context

Dropping delete evidence prevents deterministic replay, reconciliation, and forensic explanation.

## Decision

Canonical deletes carry key, source position, transaction identity, schema identity, and deletion evidence. Current-state tables may omit deleted rows, but tombstones remain through the generation/evidence retention boundary.

## Alternatives considered

- **Hard delete without evidence:** Reject: replay and reconciliation cannot explain absence.
- **Keep deleted rows as ordinary active rows:** Reject: consumer semantics become ambiguous.

## Consequences

- Current state and audit evidence are distinct.
- Retention policy covers tombstones.
- Delete proof is an independent gate.

## Failure and recovery behavior

- Delete without a resolvable key is quarantined.
- Missing tombstone evidence blocks proof.
- Premature tombstone retirement blocks generation retirement.

## Traceability

- Requirements: `CB-APPLY-003`, `CB-RECON-002`
- Components: `manifest_normalizer`, `migration_apply_engine`, `evidence_manifest_store`
- Proof obligation: Contracts must verify delete apply, replay, reconciliation, and retention.

## Limitation

Physical Iceberg tombstone representation remains an implementation choice constrained by this decision.
