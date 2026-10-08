# Lifecycle preparation and execution boundary

The seven-resource scope and ten-day retention exception are approved for preparation.
Creation is blocked. The original eight-resource manifest, acceptance registry, 48-hour
deadline and historical receipts are unchanged. Account binding is the Sky Is The Limit
account in Sydney; identifiers remain in machine guards. This work touches ChangeBridge only.

## Implemented components

`stage33_lifecycle_authority.py` verifies the exact approval text, frozen proposal digest,
resource list, preserved deadlines and pending gates. It constructs separate initial evidence
permissions, exact Scheduler invocation permissions, default schedule-group trust, conditional
evidence-bucket writes and a physical-key-bound cleanup policy. Initial permissions include
no bootstrap creation or deletion. Cleanup permissions use the exact original key, backend
role, table, topic and bucket prefixes. SNS subscription operations authorize against the
exact topic ARN; actual subscription identity and owner must still be observed. Constructed
policies remain explicitly unqualified and are not attachment authority.

The recurring delivery request uses UTC, a 15-minute interval, flexible window OFF, bounded
retry age/count, the approved failure queue and an explicit end date. It is construction only.
Controller installation before bootstrap, its anchor/readback, actual invocation and delivery
failure qualification remain unfinished. Schedule existence does not prove a met deadline.

`stage33_lifecycle_store.py` implements immutable event objects followed by a conditional head,
with execution/package binding, hash-linked records, distinct record IDs, bounded record/byte
counts and exact readback after writes. A lost storage acknowledgement is reconciled by one
read of the intended bytes. It never retries a target mutation or interprets a committed journal
as target success. Uncommitted or orphan events cannot authorize a dispatch.

The SQLite reference uses actual private durable transactions. Concurrent writers, process exit,
SIGKILL before commit, stale compare-and-set, changed records, database substitution and lost
local acknowledgements are exercised against real files. Its monotonic revisions prevent local
ABA. These observations establish local behavior, not AWS provenance or S3 durability. S3 ETags
are opaque compare tokens; no cross-service or production exactly-once guarantee is claimed.

The S3 adapter is implemented but has not been instantiated or live-qualified. It fixes regional
TLS endpoints, expected bucket owner, SSE-S3, full-object SHA-256, non-null version identities
and a single SDK attempt. Deployment must pin the actual role ID and qualified SDK model digest;
Scheduler event fields cannot supply those pins. A put acknowledgement is verified against its
original immutable version. Missing/denied/ambiguous readback blocks further work. The controller
cannot write its own frozen authority or delete its journal. External immutable authority and
retention remain separate proof obligations.

KMS alias removal requires permission on both the exact alias and its associated physical key;
the generated cleanup policy includes both. Actual key-policy delegation, alias target binding
and effective identity permissions still require qualification before attachment or use.

The original cleanup selector now retires PITR only after admission evidence is preserved,
backend access is revoked, no active locks remain and final state export is independently
verified. It requires fresh PITR DISABLED readback before table deletion and checks for unexpected
backup residuals. This retirement step cannot replace required PITR-enabled admission proof.
The reason is AWS's documented 35-day system backup on deletion of a PITR-enabled table.
Whether the bounded retirement sequence leaves no such residual must still be observed.

## Remaining blockers

- Complete the controller handler, full guarded mutation dispatch and operation-specific recovery.
  The current components do not form a deployable independent cleanup executor.
- Qualify and freeze the Lambda/SDK runtime and source bundle; no new package was installed here.
- Bind the original creation receipts, subscription owner, all immutable versions and effective IAM.
  Lost first-key acknowledgement cannot be resolved by adopting a name/tag match.
- Verify cleanup/export invariants and the final retention destination independently of the
  controller, its evidence bucket and the bootstrap KMS key. Do not erase the sole readable copy.
- Price all fifteen objects with explicit request/storage/log/invocation limits; accept and verify
  the cost boundary. USD 3 remains proposed, and budget notifications are not a hard cap.
- Establish an authenticated administrator execution channel, perform fresh qualification,
  then prove actual scheduled cleanup, OIDC/backend/alert controls and every pending criterion.

Repository CI cannot discharge these AWS gates. The draft PR remains unmerged until all original
acceptance criteria pass. No AWS API call or resource creation occurred in this continuation.

## Primary API references

- https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes.html
- https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes-enforce.html
- https://docs.aws.amazon.com/scheduler/latest/UserGuide/cross-service-confused-deputy-prevention.html
- https://docs.aws.amazon.com/service-authorization/latest/reference/list_sns.html
- https://docs.aws.amazon.com/kms/latest/developerguide/alias-access.html
- https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/PointInTimeRecovery_Howitworks.html

These references support request and policy construction, not effective deployment or admission.

## Offline SDK model qualification — 2026-10-07

The repository already declares the AWS SDK extra (`boto3>=1.35`). Under the user's standing
delegation of implementation/validation, a separate disposable environment now qualifies
`boto3==1.43.108` and `botocore==1.43.108`, with only their five required transitive packages.
All seven downloaded wheel hashes were compared to their primary PyPI release records.
Dependency declarations are unchanged. `sdk-model-qualification.json` records exact artifacts,
requirements and the actual SDK profile. It supersedes only the earlier absence of a local SDK
probe; it does not revise the frozen approval receipt or earlier validation history.

On Python 3.12.14, actual SDK parameter validation accepted current/versioned GetObject,
conditional PutObject with IfNoneMatch and IfMatch, the bounded CreateSchedule request and
PITR-retirement request. An unsupported request was rejected. Credential resolution was absent,
metadata credential discovery disabled, configuration/credential files isolated, and regional
clients constructed without any AWS API invocation. The actual S3 API-model fingerprint is
`dc2dae37167575b343c9623a7aea7e46b11524402e3d78a536a6bb0cc717037e`.

This establishes local model compatibility only. The managed Lambda source bundle, its actual
runtime/model/role pins, effective policies, independent execution and real S3 observations must
still be qualified. The controller handler and full mutation/recovery coordinator remain incomplete.
