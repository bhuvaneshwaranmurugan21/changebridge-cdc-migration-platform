# Invariant Oracles

Generated from `oracles/invariants.json`; the JSON registry and referenced Python predicates are authoritative.

## `boundary` — Snapshot and CDC boundary

Snapshot state is exactly at S and CDC contributes only positions in (S,F].

- Predicate: for every CDC position p: S < p <= F
- Local oracle: `changebridge.oracles:boundary`
- Proves: Bounded interval membership for canonical positions.
- Does not prove: DMS captured every native log record.
- Evidence label: `LOCAL_VERIFIED`

## `continuity` — Contiguous frontier chain

Every applied interval begins at the previously committed frontier with no gap or overlap.

- Predicate: for ordered intervals i: i.end == next.start
- Local oracle: `changebridge.oracles:continuity`
- Proves: Declared interval adjacency.
- Does not prove: Transport completeness inside an interval.
- Evidence label: `LOCAL_VERIFIED`

## `order` — Deterministic total order

Equivalent immutable inputs produce one unique source-consistent event order.

- Predicate: order keys are strictly increasing and unique
- Local oracle: `changebridge.oracles:order`
- Proves: Uniqueness and monotonicity of canonical order keys.
- Does not prove: Managed transport preserved native transaction order.
- Evidence label: `LOCAL_VERIFIED`

## `idempotency` — Identical replay idempotency

Reapplying identical immutable input leaves logical target state unchanged.

- Predicate: logical digest before replay equals logical digest after replay
- Local oracle: `changebridge.oracles:idempotency`
- Proves: Logical digest stability for the bounded replay.
- Does not prove: Exactly-once delivery.
- Evidence label: `LOCAL_VERIFIED`

## `conflict_detection` — Replay conflict rejection

One immutable event or transaction identity cannot bind to two payload digests.

- Predicate: same identity and different digest is rejected before mutation
- Local oracle: `changebridge.oracles:conflict_detection`
- Proves: The supplied conflict was not applied.
- Does not prove: Every producer computes identities correctly.
- Evidence label: `LOCAL_VERIFIED`

## `checkpoint_coupling` — Checkpoint and target commit coupling

A source frontier advances only with a matching durable target commit receipt.

- Predicate: checkpoint <= durable target frontier and receipt identity matches
- Local oracle: `changebridge.oracles:checkpoint_coupling`
- Proves: Bounded numeric frontier and receipt coupling.
- Does not prove: Iceberg and external ledger durability.
- Evidence label: `LOCAL_VERIFIED`

## `failure_atomicity` — Failure atomicity

A failed apply is invisible or deterministically recoverable without double application.

- Predicate: visible pre-state equals failure state, or recovery completes without double apply
- Local oracle: `changebridge.oracles:failure_atomicity`
- Proves: The modeled pre/post state relation.
- Does not prove: Distributed transaction atomicity.
- Evidence label: `LOCAL_VERIFIED`

## `delete_correctness` — Delete and tombstone correctness

A delete removes active state, preserves auditable lineage, and participates in reconciliation.

- Predicate: row absent and tombstone present and reconciliation includes deletion
- Local oracle: `changebridge.oracles:delete_correctness`
- Proves: The three bounded delete outcomes.
- Does not prove: Managed table retention and compaction behavior.
- Evidence label: `LOCAL_VERIFIED`

## `schema_safety` — Schema safety and quarantine

Unknown or incompatible source contracts are quarantined before candidate mutation or publication.

- Predicate: incompatible data never reaches active state and is quarantined
- Local oracle: `changebridge.oracles:schema_safety`
- Proves: The bounded quarantine outcome.
- Does not prove: All semantic compatibility dimensions.
- Evidence label: `LOCAL_VERIFIED`

## `generation_isolation` — Generation isolation

Candidate writes cannot mutate the consumer-visible active generation.

- Predicate: a write aimed at active generation is rejected unless it is outside migration flow
- Local oracle: `changebridge.oracles:generation_isolation`
- Proves: The supplied generation-write relation.
- Does not prove: Physical S3/Iceberg namespace isolation.
- Evidence label: `LOCAL_VERIFIED`

## `proof_before_publication` — Proof before publication

Publication requires all eight current, passing, same-boundary proof gates.

- Predicate: exact required gate set, all PASS, one boundary digest, one input revision
- Local oracle: `changebridge.oracles:proof_before_publication`
- Proves: Proof-set completeness, pass state, freshness, and boundary equality.
- Does not prove: Each managed gate implementation is correct.
- Evidence label: `LOCAL_VERIFIED`

## `single_publisher_cas` — Single-publisher compare and swap

At most one writer succeeds for one expected pointer revision.

- Predicate: success count <= 1 and expected revision is enforced
- Local oracle: `changebridge.oracles:single_publisher_cas`
- Proves: The recorded schedule has no more than one success.
- Does not prove: DynamoDB consistency or consumer pinning.
- Evidence label: `LOCAL_VERIFIED`

## `stale_writer_rejection` — Stale writer rejection

A stale expected revision cannot mutate the active pointer.

- Predicate: stale write is rejected and pointer remains unchanged
- Local oracle: `changebridge.oracles:stale_writer_rejection`
- Proves: Pointer immutability for the stale attempt.
- Does not prove: Managed contention behavior under load.
- Evidence label: `LOCAL_VERIFIED`

## `replay_determinism` — Replay determinism

Equivalent immutable inputs yield identical logical-state and proof digests.

- Predicate: first and second logical digests match and first and second proof digests match
- Local oracle: `changebridge.oracles:replay_determinism`
- Proves: Two bounded executions agree on semantic digests.
- Does not prove: All platforms or dependency versions agree.
- Evidence label: `LOCAL_VERIFIED`

## `rollback_safety` — Rollback eligibility and auditability

Rollback targets only a retained, readable, proven generation and records the decision.

- Predicate: target is proven, retained, readable, and decision is auditable
- Local oracle: `changebridge.oracles:rollback_safety`
- Proves: All four eligibility facts are true in the supplied case.
- Does not prove: Managed consumer recovery or recovery time.
- Evidence label: `LOCAL_VERIFIED`

## `evidence_binding` — Evidence lineage integrity

Evidence binds verified artifact digests, commit, run, resources, references, labels, limitations, and producer versions.

- Predicate: artifact, commit, run, and reference verification all pass
- Local oracle: `changebridge.oracles:evidence_binding`
- Proves: Internal lineage and digest integrity for supplied evidence.
- Does not prove: The measured system behavior was correct.
- Evidence label: `LOCAL_VERIFIED`
