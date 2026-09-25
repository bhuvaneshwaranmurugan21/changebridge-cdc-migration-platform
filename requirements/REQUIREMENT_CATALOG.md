# ChangeBridge Requirement Catalog

Generated deterministically from `requirements/completion-requirements.json`.
The JSON registry is authoritative.

## CB-APPLY-001 — Insert correctness

- Normative level: `MUST`
- Current status: `PARTIAL`
- Minimum evidence: `LOCAL_VERIFIED`
- Owner: `part2-runtime`
- Source conditions: 3
- Source invariants: idempotency

A valid insert event MUST create exactly the intended keyed target state once.

**Failure condition:** A valid insert is missing, duplicated, or creates a value different from the normalized after image.

**Current limitation:** Local SQLite behavior exists; Iceberg mutation does not.

## CB-APPLY-002 — Update correctness

- Normative level: `MUST`
- Current status: `PARTIAL`
- Minimum evidence: `LOCAL_VERIFIED`
- Owner: `part2-runtime`
- Source conditions: 3
- Source invariants: conflict_detection, idempotency

A valid update event MUST transform exactly the keyed target row to the normalized after image while retaining auditable source lineage.

**Failure condition:** The wrong key or value is mutated, a conflict is silently overwritten, or lineage is lost.

**Current limitation:** The local oracle does not validate an event before image against current target state.

## CB-APPLY-003 — Delete and tombstone correctness

- Normative level: `MUST`
- Current status: `SATISFIED`
- Minimum evidence: `LOCAL_VERIFIED`
- Owner: `part2-runtime`
- Source conditions: 3
- Source invariants: delete_correctness

A valid delete MUST remove the keyed row from active state and retain an auditable tombstone with source position.

**Failure condition:** A deleted row remains active, an unrelated row is removed, or the delete cannot be audited to its source position.

**Current limitation:** Satisfied only in the local oracle; Iceberg delete/compaction behavior is unimplemented.

## CB-APPLY-004 — Idempotent identical replay

- Normative level: `MUST`
- Current status: `SATISFIED`
- Minimum evidence: `LOCAL_VERIFIED`
- Owner: `part2-runtime`
- Source conditions: 3, 10
- Source invariants: idempotency, replay_determinism

Replaying an identical immutable batch or transaction MUST be a deterministic no-op.

**Failure condition:** An identical replay changes data, frontier, ledger, or output classification.

**Current limitation:** Satisfied only in the local reference engine.

## CB-APPLY-005 — Conflicting replay rejection

- Normative level: `MUST`
- Current status: `SATISFIED`
- Minimum evidence: `LOCAL_VERIFIED`
- Owner: `part2-runtime`
- Source conditions: 3, 5, 10
- Source invariants: conflict_detection, replay_determinism

Reusing a batch or transaction identity with different canonical content MUST fail closed before publication.

**Failure condition:** Conflicting content is accepted, ignored, or partially applied under an existing identity.

**Current limitation:** Local oracle only; distributed writer conflict behavior remains unproven.

## CB-BOUNDARY-001 — Single snapshot frontier

- Normative level: `MUST`
- Current status: `PARTIAL`
- Minimum evidence: `LOCAL_VERIFIED`
- Owner: `part1-stage3`
- Source conditions: 1
- Source invariants: boundary

ChangeBridge MUST bind each migration generation to exactly one immutable source snapshot frontier S.

**Failure condition:** A generation has no frontier, more than one frontier, or a frontier that can change after snapshot sealing.

**Current limitation:** Satisfied for the isolated PostgreSQL exported-snapshot path. AWS DMS checkpoint mapping and managed-source proof remain unverified.

## CB-BOUNDARY-002 — Half-open CDC coverage

- Normative level: `MUST`
- Current status: `PARTIAL`
- Minimum evidence: `LOCAL_VERIFIED`
- Owner: `part1-stage3`
- Source conditions: 1
- Source invariants: boundary, continuity

ChangeBridge MUST define generation coverage as the snapshot at S followed by CDC events in the half-open interval (S, F].

**Failure condition:** The first CDC event overlaps S, a source position after S is omitted, or an event beyond F is included in proof at F.

**Current limitation:** Satisfied for local PostgreSQL transaction commit LSNs. DMS checkpoint semantics, transport delivery, and terminal target frontier F remain later-stage proof.

## CB-BOUNDARY-003 — Frontier lineage

- Normative level: `MUST`
- Current status: `PARTIAL`
- Minimum evidence: `AWS_VERIFIED`
- Owner: `part3-managed-proof`
- Source conditions: 1, 11
- Source invariants: boundary, evidence_binding

ChangeBridge MUST retain source identity, engine/version, snapshot checkpoint, terminal frontier F, and generation identity in the proof lineage.

**Failure condition:** The proof cannot uniquely identify the source, generation, S, F, or producing run.

**Current limitation:** Local lineage now binds source, server/image, generation, workload, schema, snapshot, S and producing run; managed terminal F and AWS run lineage remain absent.

## CB-CHECKPOINT-001 — Target commit and checkpoint coupling

- Normative level: `MUST`
- Current status: `PARTIAL`
- Minimum evidence: `LOCAL_VERIFIED`
- Owner: `part1-stage3`
- Source conditions: 4
- Source invariants: checkpoint_coupling, failure_atomicity

The source checkpoint MUST advance only in the same success decision as the durable target commit and transaction ledger.

**Failure condition:** Any failed or indeterminate target application can advance the restart checkpoint.

**Current limitation:** SQLite transaction coupling exists locally; Iceberg/checkpoint coupling is not designed or implemented.

## CB-CHECKPOINT-002 — Failure leaves committed state unchanged

- Normative level: `MUST`
- Current status: `SATISFIED`
- Minimum evidence: `LOCAL_VERIFIED`
- Owner: `part2-runtime`
- Source conditions: 4, 5
- Source invariants: failure_atomicity, checkpoint_coupling

A failed batch MUST leave target state, transaction ledger, batch ledger, and generation frontier at the previous committed state.

**Failure condition:** A failed batch changes any committed data or advancement record.

**Current limitation:** Satisfied for one SQLite transaction only; no distributed target proof exists.

## CB-CHECKPOINT-003 — Deterministic restart

- Normative level: `MUST`
- Current status: `UNSATISFIED`
- Minimum evidence: `LOCAL_VERIFIED`
- Owner: `part2-runtime`
- Source conditions: 4, 10, 11
- Source invariants: checkpoint_coupling, replay_determinism

After interruption, ChangeBridge MUST restart from the last mutually committed target/checkpoint state and produce the same result as uninterrupted execution.

**Failure condition:** Restart skips, duplicates, reorders, or changes the final state or proof set.

**Current limitation:** No explicit restart API or restart suite exists.

## CB-EVIDENCE-001 — Exact repository and run binding

- Normative level: `MUST`
- Current status: `PARTIAL`
- Minimum evidence: `LOCAL_VERIFIED`
- Owner: `part1-stage2`
- Source conditions: 13, 14, 15
- Source invariants: evidence_binding

Every proof artifact MUST bind repository, stage, exact commit/tree, command or procedure, inputs, result, digest, evidence label, limitations, and run identity when applicable.

**Failure condition:** A proof cannot be traced to the exact repository state, procedure, result, and limitation it supports.

**Current limitation:** The self-referential final commit and merge identities require external post-publication checkpoints.

## CB-EVIDENCE-002 — Claim-to-proof compatibility

- Normative level: `MUST`
- Current status: `SATISFIED`
- Minimum evidence: `LOCAL_VERIFIED`
- Owner: `part1-stage2`
- Source conditions: 14
- Source invariants: evidence_binding

Every material public claim MUST use an allowed evidence label whose minimum proof is satisfied by named references.

**Failure condition:** A public claim is missing, stronger than its registry wording, or uses an incompatible proof class.

**Current limitation:** Satisfaction is limited to current registered repository claim surfaces.

## CB-EVIDENCE-003 — Deterministic evidence generation

- Normative level: `MUST`
- Current status: `SATISFIED`
- Minimum evidence: `LOCAL_VERIFIED`
- Owner: `part1-stage2`
- Source conditions: 10, 13
- Source invariants: replay_determinism, evidence_binding

Canonical evidence generated from unchanged inputs MUST be byte-identical across clean executions.

**Failure condition:** Unchanged canonical inputs produce different bytes or digests.

**Current limitation:** Volatile GitHub run metadata is intentionally external to canonical payloads.

## CB-EVIDENCE-004 — Fail-closed authority validation

- Normative level: `MUST`
- Current status: `SATISFIED`
- Minimum evidence: `LOCAL_VERIFIED`
- Owner: `part1-stage2`
- Source conditions: 13, 14
- Source invariants: evidence_binding

Malformed, unknown, stale, unsafe, unregistered, cross-project, or proof-incompatible authority records MUST fail validation.

**Failure condition:** Any designed invalid case passes or fails for an incidental diagnostic instead of its intended rule.

**Current limitation:** The validator proves repository authority structure, not runtime CDC behavior.

## CB-INTERVIEW-001 — Senior-level explainability

- Normative level: `MUST`
- Current status: `DEFERRED`
- Minimum evidence: `LOCAL_VERIFIED`
- Owner: `project-final-interview`
- Source conditions: 16
- Source invariants: evidence_binding

The project owner MUST be able to explain each major design choice, invariant, failure path, evidence boundary, tradeoff, and limitation by pointing to repository authority.

**Failure condition:** A major claim, limitation, or failure response depends on chat memory or cannot be located and defended from the repository.

**Current limitation:** Part 1 creates the repository walkthrough; the human rehearsal remains mandatory at final ChangeBridge project completion.

## CB-ISOLATION-001 — Immutable generation isolation

- Normative level: `MUST`
- Current status: `PARTIAL`
- Minimum evidence: `LOCAL_VERIFIED`
- Owner: `part1-stage3`
- Source conditions: 6, 7
- Source invariants: generation_isolation

Each migration attempt MUST write to a distinct generation whose candidate state is isolated from the active generation.

**Failure condition:** Candidate writes alter active-generation data or share mutable state with another attempt.

**Current limitation:** Physically isolated generation ownership is locally verified for one filesystem Hadoop catalog profile; Glue/S3 and concurrent distributed ownership remain unverified.

## CB-ISOLATION-002 — Backfill and replay isolation

- Normative level: `MUST`
- Current status: `UNSATISFIED`
- Minimum evidence: `LOCAL_VERIFIED`
- Owner: `part2-runtime`
- Source conditions: 6, 10
- Source invariants: generation_isolation, rollback_safety

Backfill and replay operations MUST use isolated generation or run identities and MUST NOT mutate the active generation in place.

**Failure condition:** A backfill or replay can mutate, replace, or advance the active generation directly.

**Current limitation:** No explicit backfill or replay subsystem exists.

## CB-OPS-001 — Fail-closed lag gate

- Normative level: `MUST`
- Current status: `PARTIAL`
- Minimum evidence: `LOCAL_VERIFIED`
- Owner: `part2-runtime`
- Source conditions: 5, 9
- Source invariants: proof_before_publication

Cutover MUST be blocked when CDC lag is missing, stale, or above the approved threshold.

**Failure condition:** Cutover is allowed with unknown, stale, or excessive lag.

**Current limitation:** Local numeric gate exists; no CloudWatch or DMS lag lineage exists.

## CB-OPS-002 — Operational observability and runbooks

- Normative level: `MUST`
- Current status: `PARTIAL`
- Minimum evidence: `AWS_VERIFIED`
- Owner: `part3-managed-proof`
- Source conditions: 13
- Source invariants: evidence_binding

Every critical migration state, gate failure, recovery action, cutover, and rollback MUST be observable and linked to an executable runbook.

**Failure condition:** A critical state or failure lacks a signal, owner, response, or run-bound evidence link.

**Current limitation:** A design runbook and partial CloudWatch declarations exist; no executed runbook evidence exists.

## CB-OPS-003 — Managed migration proof

- Normative level: `MUST`
- Current status: `UNSATISFIED`
- Minimum evidence: `AWS_VERIFIED`
- Owner: `part3-managed-proof`
- Source conditions: 11
- Source invariants: checkpoint_coupling, failure_atomicity, replay_determinism, rollback_safety, evidence_binding

At least one managed AWS run MUST prove happy path, injected failure, recovery, restart, deterministic replay, cutover, and rollback at an exact commit.

**Failure condition:** No exact-commit managed run covers every required lifecycle path with recoverable evidence.

**Current limitation:** No managed migration run exists.

## CB-OPS-004 — Bounded performance and cost measurement

- Normative level: `MUST`
- Current status: `UNSATISFIED`
- Minimum evidence: `MEASURED`
- Owner: `part3-managed-proof`
- Source conditions: 12
- Source invariants: evidence_binding

Performance, lag, recovery, throughput, and cost claims MUST come from immutable bounded workloads with raw observations and exact run lineage.

**Failure condition:** A numeric operational claim lacks workload, environment, raw data, method, bound, or exact run identity.

**Current limitation:** No performance or cost measurement exists.

## CB-ORDER-001 — Complete normalized event envelope

- Normative level: `MUST`
- Current status: `PARTIAL`
- Minimum evidence: `LOCAL_VERIFIED`
- Owner: `part1-stage4`
- Source conditions: 2
- Source invariants: order, replay_determinism, delete_correctness

Each normalized CDC event MUST preserve source position, transaction identity, order, operation, primary key, before image, after image, schema version, and deterministic replay identity.

**Failure condition:** Any required source semantic is absent, ambiguous, lossy, or excluded from replay identity.

**Current limitation:** The v1 envelope and one explicit synthetic local profile now have runtime conformance proof. AWS DMS emission and managed transport remain unverified.

## CB-ORDER-002 — Contiguous batch chain

- Normative level: `MUST`
- Current status: `SATISFIED`
- Minimum evidence: `LOCAL_VERIFIED`
- Owner: `part2-runtime`
- Source conditions: 2, 5
- Source invariants: continuity

Applied CDC batches MUST form a contiguous chain from the stored generation frontier to the declared batch end frontier.

**Failure condition:** A batch starts anywhere other than the committed frontier or advances to a non-increasing end frontier.

**Current limitation:** Satisfied only for the local SQLite oracle, not managed transport.

## CB-ORDER-003 — Deterministic transaction order

- Normative level: `MUST`
- Current status: `PARTIAL`
- Minimum evidence: `LOCAL_VERIFIED`
- Owner: `part1-stage4`
- Source conditions: 2, 3, 10
- Source invariants: order, replay_determinism

Transactions and events MUST be applied in a deterministic order consistent with committed source order.

**Failure condition:** Equivalent immutable inputs can produce different event order or target state.

**Current limitation:** Typed source order and local envelope ordering are verified for the explicit synthetic profile; AWS DMS delivery and target-apply conformance remain unverified.

## CB-ORDER-004 — Transaction boundary preservation

- Normative level: `MUST`
- Current status: `PARTIAL`
- Minimum evidence: `LOCAL_VERIFIED`
- Owner: `part2-runtime`
- Source conditions: 2, 3
- Source invariants: order, failure_atomicity

ChangeBridge MUST preserve source transaction boundaries through normalized ingestion and target application.

**Failure condition:** A subset of a committed source transaction becomes visible or checkpointed.

**Current limitation:** Source boundaries and local normalization transaction metadata are verified for the explicit synthetic profile; target atomicity remains unverified.

## CB-PUBLISH-001 — Proof before publication

- Normative level: `MUST`
- Current status: `PARTIAL`
- Minimum evidence: `LOCAL_VERIFIED`
- Owner: `part1-stage4`
- Source conditions: 7, 9
- Source invariants: proof_before_publication

A candidate generation MUST become publishable only after every required schema, reconciliation, lag, pre-migration, rollback, and evidence gate passes.

**Failure condition:** Any failed, missing, stale, or unbound mandatory gate permits publication.

**Current limitation:** The complete eight-gate truth table and manifest semantics are locally verified; runtime orchestration and managed publication remain unimplemented.

## CB-PUBLISH-002 — Single publisher compare-and-swap

- Normative level: `MUST`
- Current status: `SATISFIED`
- Minimum evidence: `LOCAL_VERIFIED`
- Owner: `part2-runtime`
- Source conditions: 7, 9
- Source invariants: single_publisher_cas

Consumer-visible generation publication MUST use a single versioned compare-and-swap decision.

**Failure condition:** Publication requires multiple independently visible pointer mutations or can lose a concurrent update.

**Current limitation:** Satisfied only in the SQLite oracle; no DynamoDB managed proof exists.

## CB-PUBLISH-003 — Stale writer rejection

- Normative level: `MUST`
- Current status: `SATISFIED`
- Minimum evidence: `LOCAL_VERIFIED`
- Owner: `part2-runtime`
- Source conditions: 5, 7
- Source invariants: stale_writer_rejection

A publisher using a stale expected pointer version MUST be rejected without changing the active generation.

**Failure condition:** A stale expected version changes the active pointer or reports success.

**Current limitation:** Local SQLite proof only.

## CB-PUBLISH-004 — Explicit rollback safety

- Normative level: `MUST`
- Current status: `PARTIAL`
- Minimum evidence: `LOCAL_VERIFIED`
- Owner: `part2-runtime`
- Source conditions: 7, 11
- Source invariants: rollback_safety, single_publisher_cas

Rollback MUST be an explicit, authorized compare-and-swap transition to a retained, readable, previously proven generation.

**Failure condition:** Rollback can target an unproven/unreadable generation, mutate data in reverse, or bypass pointer concurrency control.

**Current limitation:** The generic local activation primitive exists, but no rollback API or executable rollback scenario exists.

## CB-RECON-001 — Frozen-frontier reconciliation

- Normative level: `MUST`
- Current status: `PARTIAL`
- Minimum evidence: `LOCAL_VERIFIED`
- Owner: `part1-stage3`
- Source conditions: 8, 9
- Source invariants: proof_before_publication

Source and candidate reconciliation MUST compare data representing the same frozen frontier F.

**Failure condition:** Source and target proofs use different frontiers or omit frontier lineage.

**Current limitation:** Stage 3 proves the snapshot admission comparison at S; final source/target proof at F and managed acquisition remain future work.

## CB-RECON-002 — Hierarchical deterministic proof

- Normative level: `MUST`
- Current status: `PARTIAL`
- Minimum evidence: `LOCAL_VERIFIED`
- Owner: `part2-runtime`
- Source conditions: 8, 12
- Source invariants: evidence_binding

Reconciliation MUST produce deterministic machine-readable totals, partitions, and localized key-range or bucket proofs.

**Failure condition:** The same immutable inputs yield different proof, partitions omit rows, or mismatch cannot be localized below full-table scope.

**Current limitation:** Current reconciliation uses counts and full-table canonical digests only.

## CB-RECON-003 — Mismatch blocks publication

- Normative level: `MUST`
- Current status: `SATISFIED`
- Minimum evidence: `LOCAL_VERIFIED`
- Owner: `part2-runtime`
- Source conditions: 5, 8, 9
- Source invariants: proof_before_publication

Any unresolved reconciliation mismatch MUST block readiness and publication.

**Failure condition:** A generation with a failed or missing reconciliation proof can become ready or active.

**Current limitation:** Satisfied only for the local gate object.

## CB-RELEASE-001 — Final release mutual binding

- Normative level: `MUST`
- Current status: `DEFERRED`
- Minimum evidence: `LOCAL_VERIFIED`
- Owner: `final-release`
- Source conditions: 15
- Source invariants: evidence_binding

Final main, required CI, annotated tag, released assets, checksums, and PROJECT_COMPLETION_VERIFIED MUST mutually identify one immutable release state.

**Failure condition:** Any final binding references a different commit, run, tag, asset, checksum, or completion decision.

**Current limitation:** Stage 2 defines the obligation and does not create a release or tag.

## CB-SCHEMA-001 — Versioned schema identity

- Normative level: `MUST`
- Current status: `PARTIAL`
- Minimum evidence: `LOCAL_VERIFIED`
- Owner: `part1-stage4`
- Source conditions: 2, 5
- Source invariants: schema_safety

Every snapshot and CDC event MUST bind to a versioned source contract and canonical schema digest.

**Failure condition:** A record is accepted without an exact contract identity or schema digest.

**Current limitation:** The accepted local profile binds source, normalized envelope, and Iceberg snapshot metadata; managed producers and schema registries remain unverified.

## CB-SCHEMA-002 — Compatible evolution acceptance

- Normative level: `MUST`
- Current status: `PARTIAL`
- Minimum evidence: `LOCAL_VERIFIED`
- Owner: `part2-runtime`
- Source conditions: 5
- Source invariants: schema_safety, replay_determinism

A schema change classified as compatible MUST be applied deterministically without corrupting existing data or replay identity.

**Failure condition:** A compatible change is applied differently across retries or damages prior rows.

**Current limitation:** Only nullable field addition is locally demonstrated.

## CB-SCHEMA-003 — Incompatible evolution quarantine

- Normative level: `MUST`
- Current status: `PARTIAL`
- Minimum evidence: `LOCAL_VERIFIED`
- Owner: `part2-runtime`
- Source conditions: 5, 9
- Source invariants: schema_safety, proof_before_publication

An incompatible or unknown schema change MUST quarantine the affected generation before target mutation or publication.

**Failure condition:** An incompatible or unclassified schema reaches candidate data or publication.

**Current limitation:** The current checker reports incompatibility but no generation quarantine state exists.

## CB-SEC-001 — Least privilege and protected data

- Normative level: `MUST`
- Current status: `PARTIAL`
- Minimum evidence: `AWS_VERIFIED`
- Owner: `part3-managed-proof`
- Source conditions: 13
- Source invariants: evidence_binding

Managed ChangeBridge resources MUST use least-privilege identities, encryption, bounded network access, and no committed credentials.

**Failure condition:** A resource is unencrypted, unnecessarily exposed, over-privileged, or requires committed credentials.

**Current limitation:** Terraform is partial and has no deployed-state security proof.

## CB-SEC-002 — Teardown and residual-state verification

- Normative level: `MUST`
- Current status: `UNSATISFIED`
- Minimum evidence: `AWS_VERIFIED`
- Owner: `part3-managed-proof`
- Source conditions: 13
- Source invariants: evidence_binding

Every bounded managed run MUST execute an approved teardown and verify expected retained evidence and absence of unintended billable resources.

**Failure condition:** Run resources remain unintentionally active or teardown evidence cannot be reconciled to the deployment inventory.

**Current limitation:** No managed resources are created in Part 1.
