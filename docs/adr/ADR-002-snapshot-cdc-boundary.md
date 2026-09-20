# ADR-002: Snapshot frontier S and CDC interval (S,F]

- Status: Accepted
- Authority: ChangeBridge Part 1 Stage 3
- Evidence class: `DESIGN_ONLY`
- Supersession: a later ADR must name and replace this decision explicitly

## Context

A snapshot and CDC stream can each succeed while leaving a gap or overlap at their boundary.

## Decision

Persist one typed snapshot frontier S and accept committed CDC events strictly greater than S through an inclusive proof frontier F. Frontier comparison uses source-position semantics, never wall-clock time.

## Alternatives considered

- **Inclusive [S,F]:** Reject: the transaction represented at S may be applied twice.
- **Timestamp boundary:** Reject: clocks do not provide transaction order or a gap-free handoff.

## Consequences

- Source position type/version is mandatory.
- Every batch declares start-exclusive and end-inclusive positions.
- Proof artifacts bind the same F.

## Failure and recovery behavior

- Unknown or incomparable positions quarantine input.
- A gap or overlap blocks apply.
- Unresolved source/DMS mapping remains explicitly unverified.

## Traceability

- Requirements: `CB-BOUNDARY-001`, `CB-BOUNDARY-002`, `CB-BOUNDARY-003`
- Components: `postgres_source`, `dms_transport`, `checkpoint_ledger`
- Proof obligation: Contracts must exercise exact-boundary inclusion, exclusion, gaps, overlaps, and position-type mismatch.

## Limitation

The transport-specific PostgreSQL/DMS checkpoint mapping requires later managed verification.
