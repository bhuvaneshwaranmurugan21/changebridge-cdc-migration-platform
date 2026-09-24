# Stage 1 Skeptical Review

## What could still make the proof misleading?

**Could equal seeds accidentally depend on the same database state?** No. Each of the three runs
creates a distinct empty schema, applies migrations, executes, captures evidence, and drops that
schema. Same-seed equality is logical; physical LSNs are independently different.

**Is `pg_current_wal_lsn()` being mistaken for a consistent snapshot?** No. The only accepted
capture method creates a logical slot with an exported snapshot and imports that exact snapshot on
a second transaction while the exporter remains valid.

**Does a row-change record at `S` violate `(S,F]`?** The governed CDC position is the source
transaction's COMMIT LSN, not a row-level decoding record's start LSN. The receipt records both;
the row observation may equal `S`, while the commit frontier must be strictly greater.

**Could the integration test silently skip?** Not in the required GitHub lane. That lane sets the
explicit integration flag and calls only the marked integration suite. A skip or missing report
prevents artifact upload and fails acceptance.

**Is this DMS proof?** No. The output plugin and local client prove PostgreSQL snapshot-boundary
semantics only. DMS position mapping and transport conformance remain later work.

**Were Part 1 checks weakened to make Part 2 pass?** No. The historical validator and 115 tests run
from the exact frozen Part 1 tree. Current-tree tests are additive, and protected evidence digests
are independently recomputed.

**What is the largest remaining risk?** The boundary is not yet carried through a DMS-shaped
envelope and target apply path. Stage 2 must consume these identities and ordering rules without
reinterpreting them.
