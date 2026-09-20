# Consistency, rollback, and limitations

## Consumer-visible consistency

A publication pointer contains one generation ID, revision, complete table-map digest, proof-manifest digest, and publication-attempt ID. A reader resolves once and pins those values for the entire logical operation. Cache keys include pointer revision. Long-running readers keep their generation readable until their pin expires or is released.

This provides a generation-consistent consumer contract. It is **not** a claim of atomic transactions across independently committed Iceberg tables.

## Rollback and retirement

Rollback is a new authorized expected-revision publication of a prior generation. The target must remain proven, retained, readable, non-retired, table-map complete, evidence-valid, and consumer-compatible. Pointer rollback does not reverse external side effects.

Retirement requires the generation to be inactive, not reader-pinned, not rollback-required, past retention, and backed by preserved proof/evidence. `RETIRED` is terminal.

## Evidence boundary

- Architecture and ADRs: `DESIGN_ONLY`.
- Deterministic model validation: `LOCAL_VERIFIED` for specification consistency only.
- PostgreSQL/DMS frontier mapping: unverified external assumption.
- Iceberg apply/checkpoint coupling: unimplemented target design.
- Consumer resolver, orchestration, explicit managed rollback, retention, and retirement: unimplemented.
- AWS throughput, availability, recovery time, scale, cost, and zero-downtime: unclaimed.
- Transport may deliver at least once; logical apply is designed to be idempotent. No end-to-end exactly-once claim is made.
