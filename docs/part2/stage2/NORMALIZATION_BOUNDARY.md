# Part 2 Stage 2 normalization boundary

Stage 2 consumes immutable local manifests whose objects use the explicitly versioned
`changebridge.synthetic-dms-s3.full-images/1.0.0` profile. Manifest bytes, source and schema
identity, generation, run, Stage 1 boundary lineage, sequence, size, checksum, and row count are
validated before a record is normalized.

The implementation emits valid canonical CDC envelopes or immutable quarantine records, never
both for one raw record. Canonical order is numeric PostgreSQL commit LSN, transaction sequence,
event sequence, and accepted event identity. Arrival time, file order, and commit timestamp are not
ordering authority.

JSON, JSONL, and Parquet are exercised locally. The Parquet profile stores canonical UTF-8 record
JSON plus an independent SHA-256 column, preventing PyArrow conversion from silently changing
identity material. A separate compatibility probe covers decimal precision/scale, UTC timestamps,
binary, null, Unicode, and row-order metadata.

This is transparently synthetic contract evidence. It does not prove AWS DMS emission, S3
delivery, retries, recovery, managed ordering, performance, or production readiness.
