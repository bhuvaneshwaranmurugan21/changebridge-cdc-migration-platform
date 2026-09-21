# ChangeBridge Interview Walkthrough

This walkthrough is a repository navigation aid. It does not replace the owner rehearsal and does not promote any evidence label.

## Central proposition

For generation `G`, ChangeBridge models an immutable snapshot at frontier `S`, a contiguous transaction-preserving CDC interval `(S,F]`, a deterministic proof set evaluated at `F`, and compare-and-swap publication of the proven generation.

## Fifteen-minute navigation route

1. Start with `COMPLETION_CONTRACT.md` for completion and evidence semantics.
2. Use `docs/architecture.md` and the ADR index for generation, boundary, checkpoint, proof, publication and rollback decisions.
3. Use `contracts/catalog.json` and `contracts/canonicalization-v1.json` for identity and compatibility.
4. Use `oracles/invariants.json` and the adversarial fixtures for executable failure reasoning.
5. Use `claims/claims.json` to separate local proof, design intent and unclaimed managed behavior.
6. Finish with `readiness/implementation-manifest.json` for the non-authorizing implementation order.

## Invariant defense map

| Invariant | Repository authority | Proof boundary |
|---|---|---|
| `boundary` | `changebridge.oracles:boundary` | DMS captured every native log record. |
| `continuity` | `changebridge.oracles:continuity` | Transport completeness inside an interval. |
| `order` | `changebridge.oracles:order` | Managed transport preserved native transaction order. |
| `idempotency` | `changebridge.oracles:idempotency` | Exactly-once delivery. |
| `conflict_detection` | `changebridge.oracles:conflict_detection` | Every producer computes identities correctly. |
| `checkpoint_coupling` | `changebridge.oracles:checkpoint_coupling` | Iceberg and external ledger durability. |
| `failure_atomicity` | `changebridge.oracles:failure_atomicity` | Distributed transaction atomicity. |
| `delete_correctness` | `changebridge.oracles:delete_correctness` | Managed table retention and compaction behavior. |
| `schema_safety` | `changebridge.oracles:schema_safety` | All semantic compatibility dimensions. |
| `generation_isolation` | `changebridge.oracles:generation_isolation` | Physical S3/Iceberg namespace isolation. |
| `proof_before_publication` | `changebridge.oracles:proof_before_publication` | Each managed gate implementation is correct. |
| `single_publisher_cas` | `changebridge.oracles:single_publisher_cas` | DynamoDB consistency or consumer pinning. |
| `stale_writer_rejection` | `changebridge.oracles:stale_writer_rejection` | Managed contention behavior under load. |
| `replay_determinism` | `changebridge.oracles:replay_determinism` | All platforms or dependency versions agree. |
| `rollback_safety` | `changebridge.oracles:rollback_safety` | Managed consumer recovery or recovery time. |
| `evidence_binding` | `changebridge.oracles:evidence_binding` | The measured system behavior was correct. |

## Approved public claims

### CB-CLAIM-001 — `LOCAL_VERIFIED`

<!-- claim:CB-CLAIM-001 -->
The SQLite reference engine locally verifies contiguous frontiers, identical replay, conflicting replay rejection, tombstones, failure rollback, schema gates, reconciliation, and compare-and-swap publication.

Limitation: This is local reference-model proof, not DMS, Spark, Iceberg, DynamoDB, Step Functions, or distributed-runtime proof.

### CB-CLAIM-002 — `DESIGN_ONLY`

<!-- claim:CB-CLAIM-002 -->
The repository contains an accepted design-only architecture authority and a partial AWS reference topology; it does not contain a complete deployable migration platform or managed runtime proof.

Limitation: Source database, replication instance, Glue apply job, Step Functions state machine, budgets, lease controls, managed cutover, and teardown proof are absent.

### CB-CLAIM-003 — `UNCLAIMED`

<!-- claim:CB-CLAIM-003 -->
ChangeBridge makes no AWS throughput, availability, recovery-time, scale, or cost claim because no qualifying managed measurement exists.

Limitation: Future measurements require a bounded workload, raw observations, exact run lineage, and teardown evidence.

### CB-CLAIM-004 — `LOCAL_VERIFIED`

<!-- claim:CB-CLAIM-004 -->
The local reference engine prevents publication before its modeled gates pass and changes the active generation through a versioned compare-and-swap pointer.

Limitation: Managed multi-table consumer behavior is design-only; no atomic cross-Iceberg-table transaction is claimed.

### CB-CLAIM-005 — `LOCAL_VERIFIED`

<!-- claim:CB-CLAIM-005 -->
The deterministic local failure laboratory executes 13 named checks and reproduced byte-for-byte at the Stage 1 merged commit.

Limitation: The checks exercise local control-plane semantics only and do not invoke managed AWS services.

### CB-CLAIM-006 — `DESIGN_ONLY`

<!-- claim:CB-CLAIM-006 -->
The current Spark file is an interface and input-shape adapter: it validates five columns and counts rows, but performs no Iceberg write, MERGE, delete application, checkpoint coupling, or idempotent target transaction.

Limitation: It is not an Iceberg apply engine and must not be described as production-ready.

### CB-CLAIM-007 — `UNCLAIMED`

<!-- claim:CB-CLAIM-007 -->
Step Functions orchestration is an unimplemented target design: no state-machine definition, Terraform resource, test, or run evidence exists.

Limitation: Architecture prose is not implementation or runtime evidence.

### CB-CLAIM-008 — `DESIGN_ONLY`

<!-- claim:CB-CLAIM-008 -->
Terraform is a partial design artifact whose formatting and validation have historical CI evidence; it is not managed deployment or end-to-end infrastructure proof.

Limitation: Historical validation is not an apply, managed capability probe, security proof, or teardown record.

### CB-CLAIM-009 — `DESIGN_ONLY`

<!-- claim:CB-CLAIM-009 -->
Rollback now has an accepted design-only eligibility and publication contract, while the local engine still provides only a generic compare-and-swap activation primitive; no explicit rollback API, consumer-resolution scenario, or managed rollback proof exists.

Limitation: The accepted contract is DESIGN_ONLY. Generic local activation does not prove retained-generation readability, authorization, consumer pinning, rollback observability, or managed recovery.

### CB-CLAIM-010 — `LOCAL_VERIFIED`

<!-- claim:CB-CLAIM-010 -->
Stage 1 reproduced the committed local simulation byte-for-byte and bound that verification to merged main; the older simulation payload itself still lacks embedded commit, command, and tool provenance.

Limitation: This is evidence reproducibility, not managed migration or performance proof.

## Adversarial follow-ups

- Why is timestamp order insufficient, and which typed fields establish order?
- What happens after a target commit succeeds but checkpoint acknowledgement is ambiguous?
- Why does consumer-visible generation consistency not prove cross-table storage atomicity?
- How is an identical replay distinguished from a conflicting replay?
- Why can a successful DMS task not prove a correct migration?
- Which exact proof gates must be sealed before publication?
- How does stale-writer rejection differ from single-publisher compare-and-swap?
- What evidence would be required before claiming managed performance or zero downtime?

## What Part 1 proves

Part 1 proves that repository truth, completion rules, architecture, contracts, invariants, local oracles, claims and the implementation handoff are internally consistent and locally reproducible at an exact repository state.

## What Part 1 does not prove

Part 1 does not prove DMS capture correctness, Spark or Iceberg adapter conformance, managed checkpoint durability, AWS availability, exactly-once delivery, zero-downtime cutover, production performance, cost, teardown, or project release completion.

## Owner rehearsal rule

`CB-INTERVIEW-001` becomes satisfied only after the owner completes the timed repository walkthrough and adversarial follow-ups recorded in `evidence/part1/stage5/interview-rehearsal.json`.
