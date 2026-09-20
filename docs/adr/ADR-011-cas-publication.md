# ADR-011: Publish with expected-revision compare-and-swap

- Status: Accepted
- Authority: ChangeBridge Part 1 Stage 3
- Evidence class: `DESIGN_ONLY`
- Supersession: a later ADR must name and replace this decision explicitly

## Context

Concurrent or stale publishers can otherwise overwrite a newer active-generation decision.

## Decision

Every publish attempt names the expected pointer revision, proven generation, proof manifest digest, complete table map, and immutable attempt ID. Conditional conflict is a safe non-mutation outcome.

## Alternatives considered

- **Last writer wins:** Reject: stale automation can erase a newer decision.
- **Process-local lock:** Reject: it does not protect distributed publishers or retries.
- **Unconditional pointer write followed by verification:** Reject: verification detects but does not prevent lost updates.

## Consequences

- Conflicts are ordinary control flow.
- Publication attempts are immutable evidence.
- Retry requires rereading active revision and re-authorizing intent.

## Failure and recovery behavior

- Unproven generation is ineligible.
- CAS conflict leaves generation and pointer unchanged.
- Ambiguous write response requires pointer reconciliation before retry.

## Traceability

- Requirements: `CB-PUBLISH-001`, `CB-PUBLISH-002`, `CB-PUBLISH-003`
- Components: `publication_controller`, `active_generation_pointer`
- Proof obligation: Stage 4 must prove competing writers, ambiguous response, and retry-after-reread behavior.

## Limitation

The local SQLite primitive is not DynamoDB managed proof.
