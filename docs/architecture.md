# ChangeBridge architecture authority

ChangeBridge uses **frontier-bound migration generations**. A generation is the unit of source-boundary capture, isolated build, proof, publication, rollback eligibility, retention, and retirement.

```text
Generation G = snapshot at typed frontier S
             + ordered committed CDC interval (S,F]
             + sealed candidate table map at F
             + complete proof manifest at F
             + expected-revision publication decision
```

This is the authoritative Stage 3 design. It is intentionally explicit about what remains unimplemented or unverified.

## Authority map

- [Responsibility model](architecture/RESPONSIBILITY_MODEL.md)
- [Generation lifecycle](architecture/GENERATION_LIFECYCLE.md)
- [Checkpoint recovery](architecture/CHECKPOINT_RECOVERY.md)
- [Proof and publication](architecture/PROOF_AND_PUBLICATION.md)
- [Consistency and limitations](architecture/CONSISTENCY_AND_LIMITATIONS.md)
- [Architecture decision records](adr/README.md)
- Machine-readable authorities in [`../architecture/`](../architecture/)

## Trust boundaries

- The **data plane** transports and stores generation-scoped data; it does not decide completeness.
- The **control plane** owns lifecycle, checkpoint, proof aggregation, publication, reader resolution, rollback, and retirement decisions.
- The **evidence plane** binds inputs, decisions, repository/run identity, results, and limitations; it does not manufacture passing capability.

![Responsibility planes](../architecture/diagrams/responsibility-planes.svg)

## Non-negotiable semantics

1. Source positions, not timestamps, define snapshot/CDC coverage and ordering.
2. The checkpoint never advances ahead of durable target-commit evidence.
3. Ambiguous acknowledgements are reconciled before replay or advancement.
4. Only a sealed generation may be proven; only a proven generation may be published.
5. Publication is a compare-and-swap of one complete generation pointer.
6. Consumers pin generation and pointer revision for a logical operation.
7. Rejected and retired generations never silently re-enter service.
8. Rollback republishes an eligible prior generation; it does not reverse-mutate data.
9. Reconciliation compares canonical data at one frozen frontier, not counts alone.
10. Architecture validation is local specification proof, never managed-runtime proof.

## Current implementation boundary

The SQLite engine remains a local correctness oracle with a smaller state vocabulary and local transaction coupling. Terraform is partial. The Spark file is an input-shape adapter. DMS-to-source frontier mapping, Iceberg apply/checkpoint recovery, consumer resolution, orchestration, explicit rollback, and retirement remain implementation or managed-proof obligations.
