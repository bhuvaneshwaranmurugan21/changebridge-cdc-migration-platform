# ADR-016: Stage 2 normalization authority

## Status

Accepted for the local Part 2 Stage 2 adapter only.

## Decisions

1. A snapshot row uses a producer-assigned `snapshot-batch:<generation>:<table>` identity. It is a
   snapshot batch identity, not a source transaction ID. The producer also assigns explicit stable
   snapshot row sequence; the normalizer never derives it from arrival order.
2. `event_id` retains the accepted transport-neutral v1 identity. Replay uniqueness is the tuple
   `(generation_id, event_id)`. The payload digest remains generation-bound, so a cross-generation
   reuse cannot be mistaken for an identical replay.
3. Envelope v1 update and delete support requires authentic full before images. A profile without
   them is unsupported and its records are quarantined; the adapter never reconstructs images.
4. Rejected input is represented only by the separate immutable quarantine contract. Accepted
   envelopes always carry `quarantine_reason: null`.
5. `ingested_at` comes from immutable manifest/fixture provenance. It is excluded from event and
   payload identity and cannot influence ordering.
6. PostgreSQL transaction COMMIT LSN is the governed CDC position. Snapshot rows are fixed at `S`;
   CDC rows must be within `(S, object_end_frontier]`. The object end is not reconciliation `F`.

## Compatibility and claim boundary

No accepted Part 1 identity is changed. These decisions specialize the existing envelope for one
versioned, synthetic, local profile. They establish no AWS DMS or S3 behavior claim.
