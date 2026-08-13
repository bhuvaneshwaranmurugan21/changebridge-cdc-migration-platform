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
5. Apply only contiguous manifests beginning at `S`.
6. Freeze proof frontier `F`; capture source and candidate counts/digests at `F`.
7. Inject a bounded worker failure, prove rollback, then replay the same manifest.
8. Inject a known target mismatch, prove the gate blocks, repair, and reconcile again.
9. Check lag, schema, pre-migration, rollback, and reconciliation gates.
10. Swap the pointer with expected version; record the conditional-write response.
11. Observe error rate, lag, and business totals during the hold period.

## Roll back

1. Stop new candidate publication.
2. Resolve the last proven generation and current pointer version.
3. Conditionally swap the pointer to the previous generation.
4. Verify consumer reads and business totals.
5. Preserve failed generation, logs, and evidence for analysis.

## Required evidence before any production claim

- run and generation IDs;
- Terraform plan/apply output and deployed resource ARNs;
- DMS checkpoint plus source/target engine versions;
- Iceberg snapshot IDs and manifest digests;
- failure timestamps, CloudWatch log links, alarm state, and recovery timestamps;
- reconciliation JSON before failure, during mismatch, and after repair;
- measured p50/p95 runtime, maximum lag, bytes processed, and AWS cost;
- teardown plan/output and residual-resource check.
