# ADR-010: Provide consumer consistency through generation resolution

- Status: Accepted
- Authority: ChangeBridge Part 1 Stage 3
- Evidence class: `DESIGN_ONLY`
- Supersession: a later ADR must name and replace this decision explicitly

## Context

Iceberg does not provide an automatic atomic transaction spanning all independently committed tables.

## Decision

Publish one versioned active-generation pointer containing a complete table map. A reader resolves once and pins generation ID, pointer revision, and table-map digest for the logical operation.

## Alternatives considered

- **Update table aliases independently:** Reject: readers can mix generations.
- **Resolve pointer before every table read:** Reject: a long operation can cross publication revisions.
- **Claim cross-table Iceberg atomicity:** Reject: that guarantee is neither implemented nor proven.

## Consequences

- Reader libraries need explicit pinning.
- Cache entries are revision-keyed and invalidated by revision.
- Old generations remain readable while pins exist.

## Failure and recovery behavior

- Incomplete table map blocks publication.
- Missing generation data fails resolution.
- Post-publication verification failure becomes an incident, not a fictional rollback of the write.

## Traceability

- Requirements: `CB-ISOLATION-001`, `CB-PUBLISH-002`, `CB-PUBLISH-004`
- Components: `active_generation_pointer`, `consumer_resolver`, `iceberg_generation_store`
- Proof obligation: Contracts must model long readers, cache revisioning, incomplete maps, and post-write verification failure.

## Limitation

Consumer-visible consistency is a design contract; no managed consumer resolver exists.
