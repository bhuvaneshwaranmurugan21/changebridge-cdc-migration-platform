# Control Record Semantics

`contracts/control/control-records-v1.schema.json` contains the single v1 authority for twelve logical
records. `contracts/catalog.json` assigns their owners, producers, consumers, identities, lifecycle,
requirements, ADRs, components, invariants, and future proof owners.

Generation ID, snapshot frontier, and schema-set digest are immutable. Checkpoints advance monotonically
and bind a matching durable target-commit receipt. An applied transaction identity cannot bind two
digests. Reconciliation compares source and candidate at one frozen frontier and canonicalization
version.

A sealed proof manifest contains exactly continuity, schema, deletes, reconciliation, lag,
pre-migration, rollback-readiness, and evidence-integrity gates. All eight must pass at the same
generation, frontier, schema set, and input revision. Publication additionally requires a proven
generation, complete table map, and the expected active-pointer revision. Stale writers fail without
pointer mutation.

Rollback targets a retained, readable, proven generation and records reason, authority, prior revision,
and new revision. Evidence bundles bind exact artifacts, commit, run, resources, labels, limitations,
and producer versions. The local validator proves schema and bounded semantic consistency only; it does
not prove runtime durability or managed compare-and-swap behavior.
