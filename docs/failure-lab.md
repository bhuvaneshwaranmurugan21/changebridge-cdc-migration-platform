# Failure lab

Run `make evidence`. The command exits non-zero unless every check passes.

| Scenario | Injection | Required proof |
|---|---|---|
| Identical batch replay | Submit the same batch twice | Second submission returns `replayed`; no data/frontier change |
| Conflicting transaction | Reuse a transaction ID with different content | Digest conflict blocks the whole batch |
| Frontier gap | Start after the stored frontier | Batch rejected before a write |
| Hard delete | Delete an existing order | Row is absent from active state and retained as a tombstone |
| Worker crash | Raise immediately before commit | Data and frontier both roll back |
| Additive schema | Add nullable field | Candidate remains compatible |
| Breaking schema | Remove required field | Candidate is blocked with a reason |
| Value mismatch | Modify one expected amount | Equal row counts do not hide digest mismatch |
| Excessive lag | Report 31s against 30s SLO | Cutover gate fails |
| Valid cutover | Pass every proof | Ready generation becomes active |
| Concurrent cutover | Reuse stale pointer version | Conditional update fails |

The local lab exercises the control-plane semantics, not DMS, Iceberg, Spark, DynamoDB, or
CloudWatch. The managed-service experiment is defined in the runbook.
