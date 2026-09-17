# ChangeBridge Claims

Generated deterministically from `claims/claims.json`. The registry is authoritative.
No claim on this page changes an evidence label by presentation alone.

## CB-CLAIM-001 — LOCAL_VERIFIED

<!-- claim:CB-CLAIM-001 -->
The SQLite reference engine locally verifies contiguous frontiers, identical replay, conflicting replay rejection, tombstones, failure rollback, schema gates, reconciliation, and compare-and-swap publication.

- Scope: single-process SQLite correctness oracle
- Limitations: This is local reference-model proof, not DMS, Spark, Iceberg, DynamoDB, Step Functions, or distributed-runtime proof.
- Requirements: `CB-ORDER-002`, `CB-APPLY-003`, `CB-APPLY-004`, `CB-APPLY-005`, `CB-CHECKPOINT-002`, `CB-RECON-003`, `CB-PUBLISH-002`, `CB-PUBLISH-003`
- Disposition: `CORRECTED`

## CB-CLAIM-002 — DESIGN_ONLY

<!-- claim:CB-CLAIM-002 -->
The repository contains a design-only, partial AWS reference topology; it does not contain a complete deployable migration platform or managed runtime proof.

- Scope: architecture and partial Terraform declarations
- Limitations: Source database, replication instance, Glue apply job, Step Functions state machine, budgets, lease controls, managed cutover, and teardown proof are absent.
- Requirements: `CB-OPS-002`, `CB-OPS-003`, `CB-SEC-001`
- Disposition: `DOWNGRADED`

## CB-CLAIM-003 — UNCLAIMED

<!-- claim:CB-CLAIM-003 -->
ChangeBridge makes no AWS throughput, availability, recovery-time, scale, or cost claim because no qualifying managed measurement exists.

- Scope: managed operational metrics
- Limitations: Future measurements require a bounded workload, raw observations, exact run lineage, and teardown evidence.
- Requirements: `CB-OPS-003`, `CB-OPS-004`
- Disposition: `FROZEN`

## CB-CLAIM-004 — LOCAL_VERIFIED

<!-- claim:CB-CLAIM-004 -->
The local reference engine prevents publication before its modeled gates pass and changes the active generation through a versioned compare-and-swap pointer.

- Scope: single-process SQLite publication oracle
- Limitations: Managed multi-table consumer behavior is design-only; no atomic cross-Iceberg-table transaction is claimed.
- Requirements: `CB-PUBLISH-001`, `CB-PUBLISH-002`, `CB-PUBLISH-003`
- Disposition: `CORRECTED`

## CB-CLAIM-005 — LOCAL_VERIFIED

<!-- claim:CB-CLAIM-005 -->
The deterministic local failure laboratory executes 13 named checks and reproduced byte-for-byte at the Stage 1 merged commit.

- Scope: local simulator
- Limitations: The checks exercise local control-plane semantics only and do not invoke managed AWS services.
- Requirements: `CB-EVIDENCE-003`
- Disposition: `CORRECTED`

## CB-CLAIM-006 — DESIGN_ONLY

<!-- claim:CB-CLAIM-006 -->
The current Spark file is an interface and input-shape adapter: it validates five columns and counts rows, but performs no Iceberg write, MERGE, delete application, checkpoint coupling, or idempotent target transaction.

- Scope: jobs/spark_iceberg_apply.py
- Limitations: It is not an Iceberg apply engine and must not be described as production-ready.
- Requirements: `CB-APPLY-001`, `CB-APPLY-002`, `CB-APPLY-003`, `CB-CHECKPOINT-001`
- Disposition: `DOWNGRADED`

## CB-CLAIM-007 — UNCLAIMED

<!-- claim:CB-CLAIM-007 -->
Step Functions orchestration is an unimplemented target design: no state-machine definition, Terraform resource, test, or run evidence exists.

- Scope: orchestration
- Limitations: Architecture prose is not implementation or runtime evidence.
- Requirements: `CB-PUBLISH-001`, `CB-OPS-002`, `CB-OPS-003`
- Disposition: `FROZEN`

## CB-CLAIM-008 — DESIGN_ONLY

<!-- claim:CB-CLAIM-008 -->
Terraform is a partial design artifact whose formatting and validation have historical CI evidence; it is not managed deployment or end-to-end infrastructure proof.

- Scope: infra/terraform
- Limitations: Historical validation is not an apply, managed capability probe, security proof, or teardown record.
- Requirements: `CB-SEC-001`, `CB-SEC-002`, `CB-OPS-003`
- Disposition: `DOWNGRADED`

## CB-CLAIM-009 — DESIGN_ONLY

<!-- claim:CB-CLAIM-009 -->
Rollback is currently a design contract supported only indirectly by the local generic compare-and-swap activation primitive; no explicit rollback API, scenario, or managed rollback proof exists.

- Scope: rollback
- Limitations: Generic activation does not prove retained-generation readability, authorization, rollback observability, or managed recovery.
- Requirements: `CB-PUBLISH-004`
- Disposition: `DOWNGRADED`

## CB-CLAIM-010 — LOCAL_VERIFIED

<!-- claim:CB-CLAIM-010 -->
Stage 1 reproduced the committed local simulation byte-for-byte and bound that verification to merged main; the older simulation payload itself still lacks embedded commit, command, and tool provenance.

- Scope: Stage 1 local evidence verification
- Limitations: This is evidence reproducibility, not managed migration or performance proof.
- Requirements: `CB-EVIDENCE-001`, `CB-EVIDENCE-003`
- Disposition: `CORRECTED`
