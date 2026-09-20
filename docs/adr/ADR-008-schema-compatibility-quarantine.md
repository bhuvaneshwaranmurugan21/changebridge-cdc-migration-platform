# ADR-008: Version schema identity and quarantine incompatible drift

- Status: Accepted
- Authority: ChangeBridge Part 1 Stage 3
- Evidence class: `DESIGN_ONLY`
- Supersession: a later ADR must name and replace this decision explicitly

## Context

A transport can continue delivering records after a source change that the target cannot safely interpret.

## Decision

Every envelope and generation binds a schema digest and compatibility-policy version. Additive nullable changes may pass explicit policy; incompatible or unknown changes quarantine before target mutation.

## Alternatives considered

- **Infer schema per batch:** Reject: results vary with arrival order and partial observations.
- **Automatically coerce all changes:** Reject: lossy or ambiguous transformations become silent corruption.

## Consequences

- Schema decisions are evidence records.
- Compatibility is directional and versioned.
- Recovery creates an auditable successor or resumes only before sealing under the same generation policy.

## Failure and recovery behavior

- Unknown schema identity blocks normalization.
- Incompatible drift rejects the generation.
- Policy version mismatch requires re-adjudication.

## Traceability

- Requirements: `CB-SCHEMA-001`, `CB-SCHEMA-002`, `CB-SCHEMA-003`
- Components: `schema_coordinator`, `manifest_normalizer`, `generation_registry`
- Proof obligation: Stage 4 owns compatibility fixtures and fail-closed unknown-schema tests.

## Limitation

The local schema oracle covers a narrow contract and is not managed Glue/Iceberg proof.
