# Stage 6 reconciliation proof

The accepted generation `generation-34edddda5aee96dc7236aaf3` is frozen at
`F = 0/194FE20`. The source observation is replayed independently from accepted PostgreSQL history;
the target is read from generation-owned Iceberg snapshots after the accepted snapshot and CDC
transaction. Values stay typed through canonicalization.

The proof hierarchy is keyed row → SHA-256 bucket → table → generation. Every bucket is present,
including empty buckets. Mismatches identify table, key, and class. Physical Iceberg snapshot
identities may differ between independent builds; logical reconciliation must not.

The proof manifest binds the seal, frontier, schema set, input revision, and all eight gate digests.
The durable ledger prevents writes after sealing and makes identical proof replay recoverable.
`PROVEN` means eligible for Stage 7 consideration, not published.

Failure paths cover value corruption, missed deletes, missing gates, stale frontiers, corrupt gate
digests, seal conflicts, and first-publication rollback-readiness misrepresentation.
