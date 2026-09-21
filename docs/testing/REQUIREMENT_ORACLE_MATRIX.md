# Requirement-to-Oracle Matrix

Generated from `oracles/invariants.json`.

| Requirement | ADR | Component | Contract | Invariant/oracle |
|---|---|---|---|---|
| `CB-APPLY-002` | ADR-007 | migration_apply_engine, iceberg_generation_store, reconciliation_coordinator | cdc_envelope, target_record_metadata | `delete_correctness` |
| `CB-APPLY-003` | ADR-005 | migration_apply_engine | applied_transaction, cdc_envelope | `idempotency` |
| `CB-APPLY-004` | ADR-004, ADR-005 | manifest_normalizer, migration_apply_engine, proof_coordinator | cdc_envelope, proof_manifest | `replay_determinism` |
| `CB-APPLY-004` | ADR-005 | migration_apply_engine | applied_transaction, cdc_envelope | `idempotency` |
| `CB-APPLY-004` | ADR-005 | migration_apply_engine, checkpoint_ledger | cdc_envelope, applied_transaction | `conflict_detection` |
| `CB-APPLY-005` | ADR-006 | migration_apply_engine, checkpoint_ledger | frontier_checkpoint, applied_transaction | `failure_atomicity` |
| `CB-BOUNDARY-001` | ADR-002 | postgres_source, dms_transport, generation_registry | migration_generation, cdc_envelope | `boundary` |
| `CB-BOUNDARY-002` | ADR-002 | postgres_source, dms_transport, generation_registry | migration_generation, cdc_envelope | `boundary` |
| `CB-BOUNDARY-002` | ADR-002, ADR-006 | checkpoint_ledger, migration_apply_engine | frontier_checkpoint, applied_transaction | `continuity` |
| `CB-CHECKPOINT-001` | ADR-006 | checkpoint_ledger, migration_apply_engine | frontier_checkpoint, applied_transaction | `checkpoint_coupling` |
| `CB-CHECKPOINT-002` | ADR-006 | migration_apply_engine, checkpoint_ledger | frontier_checkpoint, applied_transaction | `failure_atomicity` |
| `CB-EVIDENCE-001` | ADR-014 | evidence_manifest_store | evidence_bundle, stage_receipt | `evidence_binding` |
| `CB-EVIDENCE-002` | ADR-014 | evidence_manifest_store | evidence_bundle, stage_receipt | `evidence_binding` |
| `CB-EVIDENCE-003` | ADR-014 | evidence_manifest_store | evidence_bundle, stage_receipt | `evidence_binding` |
| `CB-ISOLATION-001` | ADR-001, ADR-010 | iceberg_generation_store, active_generation_pointer | migration_generation, active_generation | `generation_isolation` |
| `CB-ORDER-001` | ADR-003, ADR-004 | manifest_normalizer, migration_apply_engine | cdc_envelope | `order` |
| `CB-ORDER-002` | ADR-002, ADR-006 | checkpoint_ledger, migration_apply_engine | frontier_checkpoint, applied_transaction | `continuity` |
| `CB-ORDER-003` | ADR-003, ADR-004 | manifest_normalizer, migration_apply_engine | cdc_envelope | `order` |
| `CB-ORDER-003` | ADR-004, ADR-005 | manifest_normalizer, migration_apply_engine, proof_coordinator | cdc_envelope, proof_manifest | `replay_determinism` |
| `CB-PUBLISH-001` | ADR-011, ADR-014 | proof_coordinator, publication_controller | gate_result, proof_manifest, publication_event | `proof_before_publication` |
| `CB-PUBLISH-002` | ADR-011 | publication_controller, active_generation_pointer | active_generation, publication_event | `single_publisher_cas` |
| `CB-PUBLISH-003` | ADR-011 | publication_controller, active_generation_pointer | active_generation, publication_event | `stale_writer_rejection` |
| `CB-PUBLISH-004` | ADR-012, ADR-015 | rollback_retirement_controller, active_generation_pointer | rollback_event, active_generation, proof_manifest | `rollback_safety` |
| `CB-RECON-003` | ADR-011, ADR-014 | proof_coordinator, publication_controller | gate_result, proof_manifest, publication_event | `proof_before_publication` |
| `CB-SCHEMA-001` | ADR-008 | schema_coordinator, manifest_normalizer | schema_contract, cdc_envelope, orders_source_contract | `schema_safety` |
| `CB-SCHEMA-003` | ADR-008 | schema_coordinator, manifest_normalizer | schema_contract, cdc_envelope, orders_source_contract | `schema_safety` |
| `CB-SCHEMA-003` | ADR-011, ADR-014 | proof_coordinator, publication_controller | gate_result, proof_manifest, publication_event | `proof_before_publication` |
