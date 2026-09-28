# ADR-018: Recoverable Iceberg CDC apply

- Status: Accepted for bounded local Stage 4 proof
- Decision: Commit each affected Iceberg table with a deterministic token and transaction-bound
  snapshot properties. Persist per-table receipts and advance the source checkpoint last with a
  compare-and-swap guard.
- Reason: Iceberg does not supply one atomic transaction spanning independent tables and SQLite
  cannot atomically commit with Iceberg. Durable target commit identity makes ambiguity
  discoverable and replay-safe without claiming cross-system atomicity.
- Failure behavior: Before-image drift, token conflicts, incomplete receipts, stale checkpoints,
  undeclared schema/key evolution, and changed replay identity fail closed.
- Limit: The accepted Stage 4 fixture touches one table. Multi-table recovery behavior is covered
  by the protocol and unit tests, not falsely presented as an atomic storage transaction.
