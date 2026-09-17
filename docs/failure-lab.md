# Failure lab

Run `make evidence`. The command exits non-zero unless every check passes.

<!-- claim:CB-CLAIM-005 -->
The deterministic local failure laboratory executes 13 named checks and reproduced byte-for-byte
at the Stage 1 merged commit.

| Executable check | Injection | Required proof |
|---|---|---|
| `contiguous_batch` | Apply `(100,130]` after frontier 100 | Batch applies and frontier becomes 130 |
| `idempotent_batch_replay` | Submit the identical batch twice | Second submission returns `replayed`; no data/frontier change |
| `delete_tombstone` | Delete an existing order | Row is absent from active state and retained as a tombstone |
| `frontier_gap_blocked` | Start after the stored frontier | Batch is rejected before a write |
| `conflicting_transaction_replay_blocked` | Reuse a transaction ID with different content | Digest conflict blocks the whole batch |
| `crash_atomicity` | Raise immediately before commit | Data and frontier both roll back |
| `nullable_schema_addition` | Add a nullable field | Candidate remains compatible |
| `breaking_schema_blocked` | Remove a required field | Candidate is blocked with a reason |
| `frontier_reconciliation` | Compare expected and actual data at frontier 130 | Counts and canonical digests match |
| `settlement_mismatch_detected` | Modify one expected amount | Equal row counts do not hide digest mismatch |
| `lag_gate` | Report 31 seconds against a 30-second threshold | Cutover gate fails |
| `proof_gated_cutover` | Pass every modeled proof | Ready generation becomes active |
| `concurrent_cutover_blocked` | Reuse a stale pointer version | Conditional update fails |

The local lab exercises the control-plane semantics, not DMS, Iceberg, Spark, DynamoDB, or
CloudWatch. The managed-service experiment is defined in the runbook.
