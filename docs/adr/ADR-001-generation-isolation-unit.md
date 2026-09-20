# ADR-001: Generation is the isolation and publication unit

- Status: Accepted
- Authority: ChangeBridge Part 1 Stage 3
- Evidence class: `DESIGN_ONLY`
- Supersession: a later ADR must name and replace this decision explicitly

## Context

Snapshot, replay, backfill, proof, and publication must not expose partial tables or mutate the currently active dataset.

## Decision

Build every migration in a unique generation namespace. Mutations are allowed only while building; sealing freezes its data/evidence identity. Consumers see a generation only through one versioned pointer.

## Alternatives considered

- **In-place active mutation:** Reject: partial tables and failed replays become consumer-visible.
- **Per-table generations:** Reject: independent publication can mix business frontiers.

## Consequences

- Storage is duplicated during migration.
- Rollback is pointer publication, not reverse mutation.
- Generation lifecycle and retention become explicit control-plane concerns.

## Failure and recovery behavior

- Namespace collision blocks creation.
- Any write after sealing is rejected.
- A failed generation remains isolated and auditable.

## Traceability

- Requirements: `CB-ISOLATION-001`, `CB-ISOLATION-002`, `CB-PUBLISH-004`
- Components: `generation_registry`, `iceberg_generation_store`, `active_generation_pointer`
- Proof obligation: Stage 4 must reject cross-generation writes and publication of an unsealed or unproven generation.

## Limitation

The repository does not yet implement generation-scoped Iceberg tables or managed reader resolution.
