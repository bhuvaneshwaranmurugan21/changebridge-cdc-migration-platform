# ADR-012: Rollback republishes an eligible prior generation

- Status: Accepted
- Authority: ChangeBridge Part 1 Stage 3
- Evidence class: `DESIGN_ONLY`
- Supersession: a later ADR must name and replace this decision explicitly

## Context

Reverse mutation is difficult to prove and a historical generation can become unreadable, retired, or invalidated.

## Decision

Rollback is an authorized CAS publication of a previously proven generation that remains retained, readable, non-retired, table-map complete, evidence-valid, and compatible with the current consumer contract.

## Alternatives considered

- **Reverse-mutate current tables:** Reject: it reconstructs history through new writes and can compound failure.
- **Allow any historical generation:** Reject: retired, unreadable, or stale-proof targets are unsafe.
- **Reuse the original publish command:** Reject: expected revision and authorization context are stale.

## Consequences

- Rollback readiness is a continuously invalidatable gate.
- External side effects are outside pointer rollback.
- Rolled-back and active status are separate concepts.

## Failure and recovery behavior

- Retired, unreadable, unproven, or reader-incompatible target is rejected.
- CAS conflict is safe.
- Consumer verification failure invokes incident response.

## Traceability

- Requirements: `CB-PUBLISH-004`, `CB-OPS-002`
- Components: `rollback_retirement_controller`, `publication_controller`, `consumer_resolver`
- Proof obligation: Contracts must cover every eligibility guard, stale authorization, and concurrent rollback conflict.

## Limitation

No explicit managed rollback API or scenario exists yet.
