# Proof and publication

The authorities are `architecture/proof-state-machine.json` and `architecture/publication-state-machine.json`.

![Proof and publication](../../architecture/diagrams/proof-publication.svg)

Proof is not one mutable boolean. Eight independent gate records bind generation, frontier, input digests, producer/version, result, limitations, and invalidation conditions. Aggregation rejects missing, failed, stale, unbound, generation-mismatched, or frontier-mismatched gates. The sealed proof manifest is immutable.

Publication accepts only a `PROVEN` generation, a complete table map, sealed proof digest, and expected pointer revision. A stale writer is a safe conflict that changes nothing. After a successful pointer write, consumer resolution is verified. Failure at that point is an incident because the write occurred; it cannot be described as if publication never happened.
