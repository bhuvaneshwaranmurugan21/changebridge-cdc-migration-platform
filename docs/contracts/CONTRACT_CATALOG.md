# Contract Catalog

Generated from `contracts/catalog.json`; the JSON registry is authoritative.

| Contract | Version | Owner | Authority | Local validator |
|---|---:|---|---|---|
| `active_generation` | `1.0.0` | publication-controller | `contracts/control/control-records-v1.schema.json#/$defs/active_generation` | `changebridge.contracts.publication_verdict` |
| `applied_transaction` | `1.0.0` | target-apply-adapter | `contracts/control/control-records-v1.schema.json#/$defs/applied_transaction` | `scripts/validate_contract_oracle_authority.py` |
| `cdc_envelope` | `1.0.0` | normalizer | `contracts/cdc-envelope-v1.schema.json#` | `changebridge.contracts.validate_cdc_event` |
| `evidence_bundle` | `1.0.0` | evidence-assembler | `contracts/control/control-records-v1.schema.json#/$defs/evidence_bundle` | `changebridge.contracts.verify_artifact_manifest` |
| `frontier_checkpoint` | `1.0.0` | checkpoint-store | `contracts/control/control-records-v1.schema.json#/$defs/frontier_checkpoint` | `scripts/validate_contract_oracle_authority.py` |
| `gate_result` | `1.0.0` | proof-controller | `contracts/control/control-records-v1.schema.json#/$defs/gate_result` | `changebridge.contracts.validate_proof_manifest` |
| `migration_generation` | `1.0.0` | generation-controller | `contracts/control/control-records-v1.schema.json#/$defs/migration_generation` | `scripts/validate_contract_oracle_authority.py` |
| `orders_source_contract` | `1.0.0` | schema-registry | `contracts/orders-v1.json#` | `jsonschema.Draft202012Validator` |
| `proof_manifest` | `1.0.0` | proof-controller | `contracts/control/control-records-v1.schema.json#/$defs/proof_manifest` | `changebridge.contracts.validate_proof_manifest` |
| `publication_event` | `1.0.0` | publication-controller | `contracts/control/control-records-v1.schema.json#/$defs/publication_event` | `changebridge.contracts.publication_verdict` |
| `reconciliation_run` | `1.0.0` | reconciliation-runner | `contracts/control/control-records-v1.schema.json#/$defs/reconciliation_run` | `scripts/validate_contract_oracle_authority.py` |
| `rollback_event` | `1.0.0` | rollback-controller | `contracts/control/control-records-v1.schema.json#/$defs/rollback_event` | `scripts/validate_contract_oracle_authority.py` |
| `schema_contract` | `1.0.0` | schema-compatibility-gate | `contracts/control/control-records-v1.schema.json#/$defs/schema_contract` | `scripts/validate_contract_oracle_authority.py` |
| `source_workload` | `1.0.0` | workload-driver | `contracts/source-workload-v1.schema.json#` | `jsonschema.Draft202012Validator` |
| `stage_receipt` | `1.0.0` | evidence-assembler | `contracts/control/control-records-v1.schema.json#/$defs/stage_receipt` | `scripts/validate_contract_oracle_authority.py` |
| `target_record_metadata` | `1.0.0` | target-apply-adapter | `contracts/target-record-metadata-v1.schema.json#` | `jsonschema.Draft202012Validator` |

All v1 contracts reject unknown fields and unknown versions. Contract presence is specification authority, not runtime-conformance proof.
