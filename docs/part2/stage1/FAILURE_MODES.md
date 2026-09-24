# Stage 1 Failure Modes

| Failure | Detection | Required behavior |
|---|---|---|
| Arbitrary current WAL position substituted for snapshot handoff | Capture-method validation | Reject `CBSNP020_UNQUALIFIED_CAPTURE_METHOD` |
| Missing or malformed LSN | Typed comparator | Reject without string ordering or coercion |
| LSN half exceeds 32 bits | Parser bounds | Reject `CBPOS003_MALFORMED_VALUE` |
| Second frontier for a generation | Frontier registry | Reject `CBSNP002_SECOND_FRONTIER` |
| First transaction missing from controlled stream | Planned/decoded transaction digest comparison | Reject `CBSNP019_FIRST_TRANSACTION_GAP` |
| Transaction commit at or below `S` | Numeric commit-LSN comparison | Reject `CBSNP009_NONADVANCING_FIRST_POSITION` |
| Row change below `S` | Numeric row-change comparison | Reject `CBSNP017_CHANGE_PRECEDES_FRONTIER` |
| Source, generation, workload, or schema identity mismatch | Receipt validation | Reject with the identity-specific diagnostic |
| Exporter closes before snapshot import | Real PostgreSQL negative probe | PostgreSQL rejects the expired snapshot; no receipt is sealed |
| Dirty namespace | Pre-create namespace inventory | Reject `CBSRC024_DIRTY_REUSED_NAMESPACE` |
| Nondeterministic schedule | Workload validation and repeated runs | Fail; do not sort away semantic order |
| Aborted mutation appears committed | Replay/state comparison | Fail history and state proof |
| Slot cleanup fails | Receipt cleanup contract | Stage remains failed and cleanup diagnostic is retained |
| Part 1 protected digest changes | Current-tree preservation | Block publication |
| PostgreSQL integration is skipped | Required service-container lane | Block pull-request acceptance |

Failed attempts are non-authoritative. They cannot be edited into success or reused for another
generation. Root-cause corrections receive a new commit and a fresh exact-head run.
