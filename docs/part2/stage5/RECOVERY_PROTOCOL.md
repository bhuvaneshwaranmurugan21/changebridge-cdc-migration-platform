# Stage 5 recovery protocol

The schema decision is written before Iceberg mutation. Iceberg then commits the field addition
and four identity properties in one metadata transaction: apply token, decision ID, policy digest,
and candidate digest. The control receipt is written afterward.

If the process exits after Iceberg commit but before the receipt, the retry reloads table metadata,
finds the deterministic token, verifies the candidate digest, schema ID, metadata location, and
policy identity, then records the missing receipt as recovered. It does not execute a second
Iceberg transaction or create a data snapshot.

Recovery fails closed when the token or candidate identity conflicts. CDC remains blocked until an
exact compatible receipt exists. Schema handling never advances the Stage 4 source checkpoint.
