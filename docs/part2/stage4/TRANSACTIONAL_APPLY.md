# Part 2 Stage 4 — Transactional CDC Apply

Stage 4 applies the bounded canonical interval `(0/194FB20, 0/194FE20]` to the unpublished
generation created in Stage 3. Its accepted input is the preserved transaction
`tx-012-post-boundary`. The transaction changes `order-004` from amount `4500` with no campaign
to amount `4750` with campaign `post-boundary`.

## Correctness protocol

1. Validate the manifest lineage, typed LSN interval, generation, schema digest, complete
   transaction event set, order, images, and unchanged primary key.
2. Claim the transaction by `(generation_id, transaction_id, transaction_digest)` in SQLite.
3. For each affected table, derive a deterministic input digest and commit token, verify target
   before-images, and execute a real Iceberg `MERGE`.
4. Bind the token, generation, transaction digest, table-input digest, manifest, and frontier into
   Iceberg snapshot summary metadata.
5. Durably record one verified table receipt. If the process disappears before this write, find
   and verify the Iceberg snapshot by token rather than replaying the mutation.
6. Advance the checkpoint with compare-and-swap only when every manifest-declared table receipt
   is durable. An identical completed replay returns the prior outcome.

The SQLite control transaction does not create an atomic transaction across Iceberg tables.
Instead, deterministic table commit tokens, durable per-table receipts, before-image guards, and
checkpoint-last finalization turn partial progress into recoverable state. The candidate stays in
`CDC_APPLYING`; Stage 4 performs no publication or cutover.

## Proof boundary

The evidence is `LOCAL_VERIFIED` for Spark 3.5.9, Iceberg 1.11.0, a filesystem Hadoop catalog,
and file-backed SQLite. The real-target laboratory runs twice, compares against an independent
SQLite reference, terminates a process after Iceberg commit but before receipt, recovers without
another write, and proves drift rejection.

It establishes neither AWS durability nor distributed exactly-once delivery, availability,
performance, atomic multi-table storage commits, schema/key evolution, reconciliation at a later
freeze point, publication, cutover, rollback, or production readiness.
