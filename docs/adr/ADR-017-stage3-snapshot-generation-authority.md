# ADR-017: Stage 3 owns isolated snapshot generation

- Status: Accepted
- Scope: ChangeBridge Part 2 Stage 3
- Supersedes: the Stage 3 row in the earlier Part 2 completion table only

## Context

The accepted master plan assigns Stage 3 to loading the snapshot at source frontier `S` into an
isolated Iceberg generation. The earlier completion table instead named transaction-preserving
landing, work already governed at the normalization boundary and whose target application belongs
after the snapshot exists.

## Decision

Stage 3 owns the complete 72-row snapshot bridge, generation isolation, real local Iceberg load,
idempotent shard commits, ambiguous-acknowledgement recovery, reconciliation at `S`, and guarded
admission to `CDC_APPLYING`. Stage 4 owns post-`S` transaction-aware CDC apply and checkpoint
recovery. Stages 5–7 retain schema policy, final proof, and publication responsibilities.

Completed Part 1 and Part 2 Stage 1–2 semantics, receipts, and evidence are immutable. The
correction moves no previously completed requirement and deletes no future obligation.

## Consequences

The Stage 2 normalizer remains unchanged. Stage 3 rejects CDC input, performs no publication, and
makes only a bounded `LOCAL_VERIFIED` claim for the locked local Spark/Iceberg runtime.
