# AWS execution and cutover runbook

## Preconditions

- Approved maintenance and rollback window.
- Source WAL retention sized for the full migration plus recovery buffer.
- Capacity and quota checks completed.
- Source contract digest pinned.
- Previous proven generation retained and readable.
- Dashboards and alarms linked to the run record.

## Execute

1. Create a globally unique run ID and generation ID.
2. Record Terraform commit, plan digest, region, account alias, and operator.
3. Start the DMS full-load-and-CDC task; capture task ARN and snapshot checkpoint `S`.
4. Verify raw object immutability, encryption, checksums, and transaction order.
5. Apply only contiguous manifests beginning after `S`. For each transaction, establish a durable
   target receipt before conditionally advancing the external checkpoint.
6. If either target-commit or checkpoint acknowledgement is ambiguous, stop and reconcile the
   deterministic target receipt and checkpoint ledger. Never blindly replay or advance.
7. Freeze proof frontier `F`; acquire source and candidate observations at the same typed frontier
   and capture hierarchical counts and canonical digests.
8. Inject a bounded worker failure, prove checkpoint/target recovery, then replay safely.
9. Inject a known target mismatch, prove the gate blocks, create or rebuild an auditable successor
   when data changes are required, and reconcile again.
10. Check every independent continuity, schema, delete, reconciliation, lag, pre-migration,
    rollback-readiness, and evidence-integrity gate at `F`; seal the proof manifest.
11. Swap the complete generation pointer with the expected revision and record the conditional
    write response. Treat a stale writer as a safe conflict.
12. Resolve the pointer through the consumer path, pin its generation/revision/table-map digest,
    verify representative reads, and then begin the observation hold period.

## Roll back

1. Stop new candidate publication.
2. Resolve the current pointer revision and a prior generation that is still proven, retained,
   readable, non-retired, evidence-valid, table-map complete, and consumer-compatible.
3. Record rollback authorization and conditionally publish that eligible generation with the
   expected current pointer revision.
4. Pin and verify consumer resolution and business totals on the resulting revision.
5. Preserve the withdrawn generation, proof, publication attempt, logs, and incident evidence.
6. Do not retire either generation while it is active, reader-pinned, rollback-required, or while
   its required evidence retention is incomplete.

## Required evidence before any production claim

- run and generation IDs;
- Terraform plan/apply output and deployed resource ARNs;
- DMS checkpoint plus source/target engine versions;
- Iceberg snapshot IDs and manifest digests;
- failure timestamps, CloudWatch log links, alarm state, and recovery timestamps;
- reconciliation JSON before failure, during mismatch, and after repair;
- measured p50/p95 runtime, maximum lag, bytes processed, and AWS cost;
- teardown plan/output and residual-resource check.
