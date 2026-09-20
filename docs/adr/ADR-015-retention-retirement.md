# ADR-015: Retain evidence and retire generations with explicit guards

- Status: Accepted
- Authority: ChangeBridge Part 1 Stage 3
- Evidence class: `DESIGN_ONLY`
- Supersession: a later ADR must name and replace this decision explicitly

## Context

Deleting or reactivating historical generations without reader, rollback, and evidence checks can break live queries and remove the only recovery target.

## Decision

Retirement requires the generation to be inactive, non-pinned, outside the rollback set, past approved retention, evidence-preserved, and explicitly authorized. RETIRED is terminal; re-use requires a new generation and proof.

## Alternatives considered

- **Time-only deletion:** Reject: active reader pins and rollback obligations can outlive age.
- **Retired-to-active transition:** Reject: readability, compatibility, and proof may no longer hold.
- **Retain everything forever:** Reject: uncontrolled storage and privacy obligations remain unresolved.

## Consequences

- Reader pins and rollback policy constrain cleanup.
- Evidence retention may exceed data retention.
- Retirement emits a durable decision record.

## Failure and recovery behavior

- Active or pinned generation cannot retire.
- Required rollback target cannot retire.
- Evidence deletion before policy expiry is blocked.

## Traceability

- Requirements: `CB-PUBLISH-004`, `CB-SEC-002`, `CB-EVIDENCE-001`
- Components: `rollback_retirement_controller`, `consumer_resolver`, `evidence_manifest_store`
- Proof obligation: Contracts must cover active, pinned, rollback-required, evidence-missing, and authorized retirement cases.

## Limitation

No managed retention or teardown proof exists.
