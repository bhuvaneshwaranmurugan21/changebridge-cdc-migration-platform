# ADR-009: Reconcile canonical rows hierarchically at one frontier

- Status: Accepted
- Authority: ChangeBridge Part 1 Stage 3
- Evidence class: `DESIGN_ONLY`
- Supersession: a later ADR must name and replace this decision explicitly

## Context

Equal row counts can hide changed values, key swaps, missing deletes, and compensating errors.

## Decision

Bind source and candidate observations to the same F, canonicalize typed rows, and compare count plus digest hierarchically by table and partition/bucket before localizing mismatches.

## Alternatives considered

- **Count-only comparison:** Reject: equal counts do not imply equal data.
- **Unfrozen source query:** Reject: concurrent writes make source and target incomparable.
- **Whole-dataset digest only:** Reject: mismatch localization and bounded retry become expensive.

## Consequences

- Canonicalization version and null/type rules are explicit.
- Source snapshot acquisition is part of proof lineage.
- Proof can localize without weakening equality.

## Failure and recovery behavior

- Different frontiers invalidate comparison.
- Unfreezable source observation remains unverified and blocks managed proof.
- Any mismatch blocks publication.

## Traceability

- Requirements: `CB-RECON-001`, `CB-RECON-002`, `CB-RECON-003`
- Components: `postgres_source`, `iceberg_generation_store`, `reconciliation_coordinator`
- Proof obligation: Stage 4 must include count-equal/digest-different and frontier-mismatch oracles.

## Limitation

The exact PostgreSQL/DMS mechanism for acquiring source-at-F remains a managed-proof obligation.
