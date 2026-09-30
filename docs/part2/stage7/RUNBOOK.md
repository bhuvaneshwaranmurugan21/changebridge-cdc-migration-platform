# Stage 7 bounded publication runbook

## Preconditions

- Verify the exact Stage 6 merge and `PART2_STAGE6_RECONCILIATION_VERIFIED` checkpoint.
- Verify every predecessor evidence path is byte-identical.
- Verify the Iceberg JAR SHA-256 before starting Spark.
- Require the execution proof, publication binding, and complete table map to validate.

## Operate

- Use one authorization, expected revision, and immutable attempt ID per decision.
- On an acknowledgement timeout, query the attempt ledger; do not issue a new mutation.
- After publication, pin the returned revision before resolving any table.
- Treat a snapshot or row-count mismatch as an incident. Preserve the pointer outcome and request
  a separately authorized recovery decision.
- Execute first-publication fallback only with explicit authorization. Confirm pointer absence,
  source routing, revision increment, and source readability.

## Stop conditions

Stop on dependency drift, predecessor drift, proof or table-map mismatch, unresolved attempt
outcome, non-monotonic revision, incomplete consumer resolution, or any request to expand the
claim beyond the local evidence boundary.
