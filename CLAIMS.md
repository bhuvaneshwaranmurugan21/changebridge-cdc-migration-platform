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
The repository contains an accepted design-only architecture authority and a partial AWS reference topology; it does not contain a complete deployable migration platform or managed runtime proof.

- Scope: accepted architecture authority and partial Terraform declarations
- Limitations: Source database, replication instance, Glue apply job, Step Functions state machine, budgets, lease controls, managed cutover, and teardown proof are absent.
- Requirements: `CB-OPS-002`, `CB-OPS-003`, `CB-SEC-001`
- Disposition: `CORRECTED`

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
Rollback now has an accepted design-only eligibility and publication contract, while the local engine still provides only a generic compare-and-swap activation primitive; no explicit rollback API, consumer-resolution scenario, or managed rollback proof exists.

- Scope: rollback
- Limitations: The accepted contract is DESIGN_ONLY. Generic local activation does not prove retained-generation readability, authorization, consumer pinning, rollback observability, or managed recovery.
- Requirements: `CB-PUBLISH-004`
- Disposition: `CORRECTED`

## CB-CLAIM-010 — LOCAL_VERIFIED

<!-- claim:CB-CLAIM-010 -->
Stage 1 reproduced the committed local simulation byte-for-byte and bound that verification to merged main; the older simulation payload itself still lacks embedded commit, command, and tool provenance.

- Scope: Stage 1 local evidence verification
- Limitations: This is evidence reproducibility, not managed migration or performance proof.
- Requirements: `CB-EVIDENCE-001`, `CB-EVIDENCE-003`
- Disposition: `CORRECTED`

## CB-CLAIM-011 — LOCAL_VERIFIED

<!-- claim:CB-CLAIM-011 -->
A deterministic workload was executed in isolated PostgreSQL 17.11 schemas, and a real exported logical snapshot was locally bound to one typed PostgreSQL LSN frontier; repeated same-seed runs matched logically while their physical LSNs remained run-specific.

- Scope: isolated PostgreSQL source workload and snapshot boundary
- Limitations: This does not verify AWS DMS position mapping or delivery, downstream normalization, target application, Iceberg behavior, performance, availability, cost, exactly-once delivery, zero downtime, or production readiness.
- Requirements: `CB-BOUNDARY-001`, `CB-BOUNDARY-002`, `CB-BOUNDARY-003`, `CB-ORDER-003`, `CB-ORDER-004`, `CB-SCHEMA-001`
- Disposition: `CORRECTED`

## CB-CLAIM-012 — LOCAL_VERIFIED

<!-- claim:CB-CLAIM-012 -->
A versioned local adapter deterministically normalizes the declared synthetic DMS/S3-shaped JSON, JSONL, and Parquet fixture profile into canonical ChangeBridge envelopes and quarantines malformed or ambiguous inputs with stable reason codes.

- Scope: local manifest normalizer for one explicit synthetic fixture profile
- Limitations: No AWS DMS emission, S3 delivery, managed retry/recovery, target apply, performance, availability, exactly-once, zero-downtime, or production-readiness proof is established.
- Requirements: `CB-BOUNDARY-002`, `CB-BOUNDARY-003`, `CB-ORDER-001`, `CB-ORDER-003`, `CB-ORDER-004`, `CB-SCHEMA-001`, `CB-SCHEMA-002`, `CB-EVIDENCE-001`
- Disposition: `CORRECTED`

## CB-CLAIM-013 — LOCAL_VERIFIED

<!-- claim:CB-CLAIM-013 -->
The complete accepted 72-row snapshot at S is locally loaded through real Spark 3.5.9 into generation-isolated Iceberg 1.11.0 tables; identical replay creates no new target snapshot, and a process killed after Iceberg commit recovers from checksum-pinned commit metadata without rewriting.

- Scope: bounded local Spark/Iceberg snapshot generation at S
- Limitations: The proof uses a local filesystem Hadoop catalog and file-backed SQLite. It does not prove S3 or Glue durability, distributed exactly-once delivery, post-S CDC apply, schema evolution, publication, performance, availability, zero downtime, or production readiness.
- Requirements: `CB-BOUNDARY-001`, `CB-BOUNDARY-003`, `CB-ISOLATION-001`, `CB-RECON-001`, `CB-SCHEMA-001`, `CB-EVIDENCE-001`
- Disposition: `CORRECTED`
