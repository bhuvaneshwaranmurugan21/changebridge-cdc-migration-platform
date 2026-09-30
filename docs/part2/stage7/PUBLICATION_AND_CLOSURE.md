# Stage 7 publication and Part 2 closure

## Authority chain

The accepted Stage 6 proof digest is
`df47eda3dff2f2d4491afab71574a9abefe02e1ba1af3a788f3c190ab650a5ad`.
Stage 7 reconstructs the same generation from accepted inputs and reruns all eight gates. The
publication-binding manifest requires the accepted and execution proofs to agree on generation,
frontier, schema authority, and logical reconciliation digest while recording fresh physical
Iceberg identities.

## Publication protocol

1. Register the execution-bound generation and complete table map.
2. Begin from revision `0`, source routing, and no active pointer.
3. Publish with one immutable attempt ID and expected revision `0`.
4. Reconcile an ambiguous acknowledgement by the same attempt ID.
5. Pin revision `1`; read both tables only through that pin; verify snapshot IDs and row counts.
6. Run the explicitly authorized first-publication fallback at expected revision `1`.
7. Reconcile its ambiguous acknowledgement and verify revision `2`, source routing, and pointer
   absence. A stale attempt at revision `0` must still fail, proving the revision did not reset.

## Failure behavior

- Failed, missing, stale, or corrupt proof data blocks registration or publication.
- Stale and competing writers do not mutate the pointer.
- Reusing an attempt ID with different input is rejected.
- A consumer mismatch after pointer mutation enters `INCIDENT`; orchestration never invents an
  automatic fallback decision.
- Ordinary rollback requires an explicit authorization and a retained, readable, evidence-valid,
  previously published generation. It republishes a generation pointer and never reverse-mutates
  Iceberg tables.

## Evidence boundary

The real-runtime lab uses Spark 3.5.9, Iceberg 1.11.0, a filesystem Hadoop catalog, and
file-backed SQLite. The run ends in verified source fallback with no active pointer. No AWS,
managed durability, live traffic, production rollback, performance, availability, zero downtime,
or production-readiness property is asserted.
