# ChangeBridge Requirement-to-Proof Matrix

Generated deterministically from the authoritative requirements registry.

| Requirement | Status | Minimum evidence | Owner | Current proof | Future proof |
|---|---|---|---|---|---|
| `CB-APPLY-001` | `PARTIAL` | `LOCAL_VERIFIED` | `part2-runtime` | `tests/test_engine.py` | `future:tests/integration/test_iceberg_apply.py` |
| `CB-APPLY-002` | `PARTIAL` | `LOCAL_VERIFIED` | `part2-runtime` | `tests/test_engine.py` | `future:tests/integration/test_iceberg_apply.py` |
| `CB-APPLY-003` | `SATISFIED` | `LOCAL_VERIFIED` | `part2-runtime` | `evidence/local-simulation.json`<br>`tests/test_engine.py` | None |
| `CB-APPLY-004` | `SATISFIED` | `LOCAL_VERIFIED` | `part2-runtime` | `evidence/local-simulation.json`<br>`tests/test_engine.py` | None |
| `CB-APPLY-005` | `SATISFIED` | `LOCAL_VERIFIED` | `part2-runtime` | `evidence/local-simulation.json`<br>`tests/test_engine.py` | None |
| `CB-BOUNDARY-001` | `PARTIAL` | `LOCAL_VERIFIED` | `part1-stage3` | `tests/test_engine.py` | `future:tests/contracts/test_boundary.py` |
| `CB-BOUNDARY-002` | `PARTIAL` | `LOCAL_VERIFIED` | `part1-stage3` | `tests/test_engine.py` | `future:tests/contracts/test_boundary.py` |
| `CB-BOUNDARY-003` | `UNSATISFIED` | `AWS_VERIFIED` | `part3-managed-proof` | None | `future:evidence/managed/frontier-lineage.json` |
| `CB-CHECKPOINT-001` | `PARTIAL` | `LOCAL_VERIFIED` | `part1-stage3` | `tests/test_engine.py` | `future:tests/model/test_checkpoint_coupling.py` |
| `CB-CHECKPOINT-002` | `SATISFIED` | `LOCAL_VERIFIED` | `part2-runtime` | `evidence/local-simulation.json`<br>`tests/test_engine.py` | None |
| `CB-CHECKPOINT-003` | `UNSATISFIED` | `LOCAL_VERIFIED` | `part2-runtime` | None | `future:evidence/managed/restart.json`<br>`future:tests/model/test_restart.py` |
| `CB-EVIDENCE-001` | `PARTIAL` | `LOCAL_VERIFIED` | `part1-stage2` | `evidence/part1/stage2/validation-report.json` | `future:external-continuation-checkpoint.json` |
| `CB-EVIDENCE-002` | `SATISFIED` | `LOCAL_VERIFIED` | `part1-stage2` | `evidence/part1/stage2/validation-report.json`<br>`tests/test_completion_authority.py` | None |
| `CB-EVIDENCE-003` | `SATISFIED` | `LOCAL_VERIFIED` | `part1-stage2` | `evidence/part1/stage2/determinism-report.json` | None |
| `CB-EVIDENCE-004` | `SATISFIED` | `LOCAL_VERIFIED` | `part1-stage2` | `tests/fixtures/completion-authority/invalid-cases.json`<br>`tests/test_completion_authority.py` | None |
| `CB-INTERVIEW-001` | `DEFERRED` | `LOCAL_VERIFIED` | `part1-stage5` | None | `future:evidence/part1/stage5/interview-rehearsal.json` |
| `CB-ISOLATION-001` | `PARTIAL` | `LOCAL_VERIFIED` | `part1-stage3` | `tests/test_engine.py` | `future:tests/model/test_generation_isolation.py` |
| `CB-ISOLATION-002` | `UNSATISFIED` | `LOCAL_VERIFIED` | `part2-runtime` | None | `future:tests/model/test_replay_isolation.py` |
| `CB-OPS-001` | `PARTIAL` | `LOCAL_VERIFIED` | `part2-runtime` | `evidence/local-simulation.json`<br>`tests/test_schema_and_cutover.py` | None |
| `CB-OPS-002` | `PARTIAL` | `AWS_VERIFIED` | `part3-managed-proof` | None | `future:evidence/managed/operations.json` |
| `CB-OPS-003` | `UNSATISFIED` | `AWS_VERIFIED` | `part3-managed-proof` | None | `future:evidence/managed/stage-receipt.json` |
| `CB-OPS-004` | `UNSATISFIED` | `MEASURED` | `part3-managed-proof` | None | `future:evidence/managed/measurements.json` |
| `CB-ORDER-001` | `PARTIAL` | `LOCAL_VERIFIED` | `part1-stage4` | None | `future:tests/contracts/test_cdc_envelope.py` |
| `CB-ORDER-002` | `SATISFIED` | `LOCAL_VERIFIED` | `part2-runtime` | `evidence/local-simulation.json`<br>`tests/test_engine.py` | None |
| `CB-ORDER-003` | `PARTIAL` | `LOCAL_VERIFIED` | `part1-stage4` | None | `future:tests/contracts/test_ordering.py` |
| `CB-ORDER-004` | `PARTIAL` | `LOCAL_VERIFIED` | `part2-runtime` | `tests/test_engine.py` | `future:tests/test_transaction_atomicity.py` |
| `CB-PUBLISH-001` | `PARTIAL` | `LOCAL_VERIFIED` | `part1-stage4` | `evidence/local-simulation.json`<br>`tests/test_schema_and_cutover.py` | `future:tests/model/test_publication_oracle.py` |
| `CB-PUBLISH-002` | `SATISFIED` | `LOCAL_VERIFIED` | `part2-runtime` | `evidence/local-simulation.json`<br>`tests/test_schema_and_cutover.py` | None |
| `CB-PUBLISH-003` | `SATISFIED` | `LOCAL_VERIFIED` | `part2-runtime` | `evidence/local-simulation.json`<br>`tests/test_schema_and_cutover.py` | None |
| `CB-PUBLISH-004` | `PARTIAL` | `LOCAL_VERIFIED` | `part2-runtime` | None | `future:evidence/managed/rollback.json`<br>`future:tests/model/test_rollback.py` |
| `CB-RECON-001` | `PARTIAL` | `LOCAL_VERIFIED` | `part1-stage3` | `tests/test_reconciliation.py` | `future:evidence/managed/reconciliation.json` |
| `CB-RECON-002` | `PARTIAL` | `LOCAL_VERIFIED` | `part2-runtime` | `tests/test_reconciliation.py` | `future:tests/test_hierarchical_reconciliation.py` |
| `CB-RECON-003` | `SATISFIED` | `LOCAL_VERIFIED` | `part2-runtime` | `evidence/local-simulation.json`<br>`tests/test_reconciliation.py`<br>`tests/test_schema_and_cutover.py` | None |
| `CB-RELEASE-001` | `DEFERRED` | `LOCAL_VERIFIED` | `final-release` | None | `future:release/release-verification.json` |
| `CB-SCHEMA-001` | `PARTIAL` | `LOCAL_VERIFIED` | `part1-stage4` | `tests/test_schema_and_cutover.py` | `future:tests/contracts/test_schema_identity.py` |
| `CB-SCHEMA-002` | `PARTIAL` | `LOCAL_VERIFIED` | `part2-runtime` | `evidence/local-simulation.json`<br>`tests/test_schema_and_cutover.py` | None |
| `CB-SCHEMA-003` | `PARTIAL` | `LOCAL_VERIFIED` | `part2-runtime` | `evidence/local-simulation.json`<br>`tests/test_schema_and_cutover.py` | None |
| `CB-SEC-001` | `PARTIAL` | `AWS_VERIFIED` | `part3-managed-proof` | None | `future:evidence/managed/security.json` |
| `CB-SEC-002` | `UNSATISFIED` | `AWS_VERIFIED` | `part3-managed-proof` | None | `future:evidence/managed/teardown.json` |
