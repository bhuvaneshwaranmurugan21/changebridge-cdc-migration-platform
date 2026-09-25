# Stage 3 authority transition

The former completion-table label `Transaction-preserving landing and ordering` and checkpoint
`PART2_STAGE3_TRANSACTION_LANDING_VERIFIED` are corrected to `Snapshot loader and isolated
Iceberg generation` and `PART2_STAGE3_SNAPSHOT_GENERATION_VERIFIED`.

No accepted Stage 1 or Stage 2 file is rewritten. Transaction/event identity and ordering stay with
Stage 2 normalization; their target application moves to Stage 4. The correction preserves every
future schema, reconciliation, publication, and rollback obligation.
