# Authority Transition CB-AUTH-TRANSITION-002

## Prior authority

Part 1 defined the typed frontier, `(S,F]` interval, generation immutability, canonicalization,
source ordering, and evidence rules as design and reference-oracle authority.

## Executable transition

Stage 1 adds a local PostgreSQL implementation without changing those meanings:

- PostgreSQL LSN text is accepted only when each hexadecimal half fits unsigned 32-bit syntax.
- `S` is the consistent point returned by logical-slot creation with an exported snapshot.
- The snapshot is imported while its exporter remains valid.
- A decoded transaction is ordered by its COMMIT LSN. A row-change record may legitimately carry
  the same LSN as `S`; it is retained as observation evidence but is not the transaction frontier.
- Semantic workload identity excludes all physical LSN values.

## Protected compatibility

The Part 1 source tree and historical validator run separately at exact commit
`6ae4e071782bddeb5a35f9635262e868f52df6f5`. Current-tree preservation recomputes every protected
Part 1 manifest and receipt digest. No historical evidence is edited.

## Claim effect

The transition supports only a new `LOCAL_VERIFIED` source-boundary claim. AWS DMS mapping,
managed delivery, target application, performance, availability, cost, exactly-once, zero
downtime, and production readiness remain unclaimed.
