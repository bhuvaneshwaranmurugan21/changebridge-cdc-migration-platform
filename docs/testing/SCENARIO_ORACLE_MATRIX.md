# Scenario-to-Oracle Matrix

Generated from the deterministic oracle and adversarial fixture corpora.

## Positive and minimal counterexample cases

| Scenario | Invariant | Expected |
|---|---|---:|
| `ST4-SC-01` | `boundary` — Snapshot and CDC boundary | PASS |
| `ST4-SC-01-N` | `boundary` — Snapshot and CDC boundary | FAIL |
| `ST4-SC-02` | `continuity` — Contiguous frontier chain | PASS |
| `ST4-SC-02-N` | `continuity` — Contiguous frontier chain | FAIL |
| `ST4-SC-03` | `order` — Deterministic total order | PASS |
| `ST4-SC-03-N` | `order` — Deterministic total order | FAIL |
| `ST4-SC-04` | `idempotency` — Identical replay idempotency | PASS |
| `ST4-SC-04-N` | `idempotency` — Identical replay idempotency | FAIL |
| `ST4-SC-05` | `conflict_detection` — Replay conflict rejection | PASS |
| `ST4-SC-05-N` | `conflict_detection` — Replay conflict rejection | FAIL |
| `ST4-SC-06` | `checkpoint_coupling` — Checkpoint and target commit coupling | PASS |
| `ST4-SC-06-N` | `checkpoint_coupling` — Checkpoint and target commit coupling | FAIL |
| `ST4-SC-07` | `failure_atomicity` — Failure atomicity | PASS |
| `ST4-SC-07-N` | `failure_atomicity` — Failure atomicity | FAIL |
| `ST4-SC-08` | `delete_correctness` — Delete and tombstone correctness | PASS |
| `ST4-SC-08-N` | `delete_correctness` — Delete and tombstone correctness | FAIL |
| `ST4-SC-09` | `schema_safety` — Schema safety and quarantine | PASS |
| `ST4-SC-09-N` | `schema_safety` — Schema safety and quarantine | FAIL |
| `ST4-SC-10` | `generation_isolation` — Generation isolation | PASS |
| `ST4-SC-10-N` | `generation_isolation` — Generation isolation | FAIL |
| `ST4-SC-11` | `proof_before_publication` — Proof before publication | PASS |
| `ST4-SC-11-N` | `proof_before_publication` — Proof before publication | FAIL |
| `ST4-SC-12` | `single_publisher_cas` — Single-publisher compare and swap | PASS |
| `ST4-SC-12-N` | `single_publisher_cas` — Single-publisher compare and swap | FAIL |
| `ST4-SC-13` | `stale_writer_rejection` — Stale writer rejection | PASS |
| `ST4-SC-13-N` | `stale_writer_rejection` — Stale writer rejection | FAIL |
| `ST4-SC-14` | `replay_determinism` — Replay determinism | PASS |
| `ST4-SC-14-N` | `replay_determinism` — Replay determinism | FAIL |
| `ST4-SC-15` | `rollback_safety` — Rollback eligibility and auditability | PASS |
| `ST4-SC-15-N` | `rollback_safety` — Rollback eligibility and auditability | FAIL |
| `ST4-SC-16` | `evidence_binding` — Evidence lineage integrity | PASS |
| `ST4-SC-16-N` | `evidence_binding` — Evidence lineage integrity | FAIL |

## Adversarial cases

| Scenario | Mutation | Exact diagnostic | Invariants |
|---|---|---|---|
| `ADV-001` | `missing_contract_version` | `CBCON001_SCHEMA_REJECTED` | schema_safety |
| `ADV-002` | `unknown_contract_version` | `CBCON001_SCHEMA_REJECTED` | schema_safety |
| `ADV-003` | `prohibited_extra_field` | `CBCON001_SCHEMA_REJECTED` | schema_safety |
| `ADV-004` | `malformed_source_position` | `CBPOS003_MALFORMED_VALUE` | order |
| `ADV-005` | `incomparable_source_position` | `CBPOS004_INCOMPARABLE_KINDS` | order |
| `ADV-006` | `equal_position_duplicate_sequence` | `CBORACLE_FALSE` | order |
| `ADV-007` | `missing_primary_key` | `CBCON001_SCHEMA_REJECTED` | delete_correctness |
| `ADV-008` | `invalid_operation_image` | `CBEVT002_INVALID_IMAGE_COMBINATION` | delete_correctness |
| `ADV-009` | `schema_identity_digest_mismatch` | `CBEVT005_SCHEMA_IDENTITY_MISMATCH` | schema_safety |
| `ADV-010` | `same_event_changed_payload` | `CBREPLAY_CONFLICT` | conflict_detection |
| `ADV-011` | `snapshot_cdc_gap` | `CBORACLE_FALSE` | boundary, continuity |
| `ADV-012` | `batch_overlap` | `CBORACLE_FALSE` | continuity |
| `ADV-013` | `checkpoint_regression` | `CBCTL002_CHECKPOINT_REGRESSION` | checkpoint_coupling |
| `ADV-014` | `checkpoint_commit_mismatch` | `CBORACLE_FALSE` | checkpoint_coupling |
| `ADV-015` | `ambiguous_commit_acknowledgement` | `CBORACLE_FALSE` | failure_atomicity |
| `ADV-016` | `missing_proof_gate` | `CBPRF001_GATE_SET_INVALID` | proof_before_publication |
| `ADV-017` | `duplicate_proof_gate` | `CBPRF002_DUPLICATE_GATE` | proof_before_publication |
| `ADV-018` | `failed_proof_gate` | `CBPRF003_GATE_NOT_PASSING` | proof_before_publication |
| `ADV-019` | `stale_proof_gate` | `CBPRF005_STALE_GATE` | proof_before_publication |
| `ADV-020` | `cross_generation_proof_gate` | `CBPRF004_CROSS_BOUNDARY_GATE` | proof_before_publication |
| `ADV-021` | `cross_generation_write` | `CBORACLE_FALSE` | generation_isolation |
| `ADV-022` | `stale_publication_attempt` | `CBPUB005_STALE_REVISION` | stale_writer_rejection |
| `ADV-023` | `rollback_unproven_target` | `CBCON001_SCHEMA_REJECTED` | rollback_safety |
| `ADV-024` | `tampered_artifact` | `CBEVD003_ARTIFACT_DIGEST_MISMATCH` | evidence_binding |
| `ADV-025` | `floating_identity_material` | `CBCAN003_FLOAT_FORBIDDEN` | replay_determinism |
| `ADV-026` | `naive_timestamp` | `CBCAN005_NAIVE_TIMESTAMP` | replay_determinism |
