# ADR-019: Recoverable schema and primary-key policy

## Status

Accepted for Part 2 Stage 5. This ADR supersedes ADR-008 as the executable proof authority while
preserving ADR-008's fail-closed intent.

## Context

A CDC event can name a plausible schema version while carrying an unknown digest, a changed key,
or a contract that was never applied to the target. Allowing that event to reach mutation would
make replay and recovery ambiguous. Conversely, treating every additive change as safe would hide
the distinction between a nullable non-key addition and a required field, type, nullability, or
primary-key change.

## Decision

1. Contract identity is the tuple `(contract_id, version, digest)`; version alone is insufficient.
2. Primary keys are ordered, typed definitions and are independent authority, not inferred from
   event payloads.
3. Policy `changebridge.schema-policy/1.0.0` has an immutable canonical digest.
4. The only accepted change is one nullable non-key field addition. Coercion, default inference,
   removals, renames, type changes, nullability narrowing, and primary-key changes fail closed.
5. The decision is durable before target mutation. Unknown decisions open quarantine. Incompatible
   decisions open quarantine and durably mark the candidate generation `REJECTED` in the
   Stage 5 schema-control ledger.
6. One Iceberg transaction commits the schema field and recovery properties. The resulting
   receipt binds apply token, policy digest, candidate digest, decision, Iceberg schema ID, and
   metadata location.
7. CDC assembly requires that exact receipt and rejects key-value mutation.

## Recovery

The deterministic apply token is stored in Iceberg properties in the same metadata transaction as
the field addition. After process loss, the coordinator discovers the token and candidate digest,
records the missing control receipt, and performs no second schema commit. An inconsistent token
is a hard conflict.

## Consequences

The policy is intentionally narrow and explainable. The local proof does not claim arbitrary
Iceberg evolution, cross-table atomicity, managed catalog durability, or production safety. Stage
6 still owns reconciliation and sealing; Stage 7 owns publication and cutover.

## Traceability

- Requirements: `CB-SCHEMA-001`, `CB-SCHEMA-002`, `CB-SCHEMA-003`, `CB-CHECKPOINT-001`
- Evidence label: `LOCAL_VERIFIED`
- Runtime: Spark 3.5.9, Iceberg 1.11.0, filesystem Hadoop catalog, SQLite
