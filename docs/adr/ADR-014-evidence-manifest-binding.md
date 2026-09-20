# ADR-014: Bind decisions through immutable evidence manifests

- Status: Accepted
- Authority: ChangeBridge Part 1 Stage 3
- Evidence class: `DESIGN_ONLY`
- Supersession: a later ADR must name and replace this decision explicitly

## Context

A green command without exact inputs, commit, run, frontier, and limitations cannot defend a migration claim.

## Decision

Every material decision emits a canonical record. A sealed evidence manifest binds repository commit/tree, run/generation, source and target identities, frontier, input/output digests, producer version, results, labels, and limitations.

## Alternatives considered

- **Rely on logs:** Reject: logs are incomplete, mutable, and difficult to bind.
- **Store screenshots only:** Reject: screenshots are not machine-verifiable lineage.
- **Regenerate evidence after the fact:** Reject: retrospective reconstruction can hide the actual executed state.

## Consequences

- Canonical serialization excludes volatile fields.
- Claim registry points to immutable proof.
- Orchestrator cannot manufacture passing results.

## Failure and recovery behavior

- Missing or mismatched digest blocks proof sealing.
- Stale commit/run binding invalidates claims.
- Unsupported evidence-label promotion fails validation.

## Traceability

- Requirements: `CB-EVIDENCE-001`, `CB-EVIDENCE-002`, `CB-EVIDENCE-003`, `CB-EVIDENCE-004`
- Components: `proof_coordinator`, `future_orchestrator`, `evidence_manifest_store`
- Proof obligation: Validators must reject volatile canonical fields, missing bindings, stale claims, and digest drift.

## Limitation

Local architecture validation proves specification consistency, not managed execution.
