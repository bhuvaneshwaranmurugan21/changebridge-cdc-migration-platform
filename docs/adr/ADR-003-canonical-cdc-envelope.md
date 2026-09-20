# ADR-003: Transport-neutral canonical CDC envelope

- Status: Accepted
- Authority: ChangeBridge Part 1 Stage 3
- Evidence class: `DESIGN_ONLY`
- Supersession: a later ADR must name and replace this decision explicitly

## Context

DMS, Debezium, and future transports encode ordering, transactions, and deletes differently.

## Decision

Normalize raw transport records into a versioned envelope containing source identity, generation, transaction ID, source position, transaction/event sequence, operation, key, before/after images, schema digest, and payload digest.

## Alternatives considered

- **Apply transport records directly:** Reject: correctness becomes coupled to undocumented transport shapes.
- **Minimal key/value envelope:** Reject: transaction ordering, deletes, schema identity, and replay conflict detection are lost.

## Consequences

- Normalizer version becomes evidence lineage.
- Unknown fields/operations fail closed.
- Raw records remain immutable for re-normalization.

## Failure and recovery behavior

- Malformed or unknown records are quarantined.
- Envelope digest mismatch blocks replay.
- Transport assumptions remain evidence-bounded.

## Traceability

- Requirements: `CB-ORDER-001`, `CB-ORDER-004`, `CB-SCHEMA-001`
- Components: `dms_transport`, `s3_landing`, `manifest_normalizer`
- Proof obligation: Stage 4 owns versioned schemas and cross-transport conformance fixtures.

## Limitation

Stage 3 specifies the envelope but does not implement a DMS normalizer.
