# Independent lifecycle scope decision

## Approval overlay — 2026-10-07

The user approved preparation of the seven objects below and their maximum ten-day
controller/private-evidence retention exception. The frozen approval is recorded in
`deployment/stage3/lifecycle-authority.json`, bound to this proposal at commit
`c99ac491e5764bac81b413e494c83bc5e616cca6`. The proposal JSON and earlier evidence remain
unchanged; their unapproved status describes the earlier checkpoint. The original eight
objects retain the 48-hour operational deadline. The approval neither accepts the proposed
USD 3 allowance nor authorizes resource creation before exact policies, cost and execution
gates are verified. Stage 3 remains 32 PASS / 20 PENDING.

`LIFECYCLE_IMPLEMENTATION.md` records implemented components, their actual validation and
remaining work. No deployed function, actual scheduled execution, policy effectiveness or
external retention has been proven. The previous narrative follows as the historical proposal.

Status: proposed design correction, not an approved resource manifest, deployed controller,
completed installer or AWS acceptance receipt. The original eight-resource allowlist, Stage 3
contract and acceptance registry remain unchanged. Stage 3 stays 32 PASS / 20 PENDING.

## Why bootstrap cannot start under the current design

The original manifest contains the state key and alias, two buckets, locks, alerts and the dedicated
backend role. None can independently execute cleanup after the administrator session disappears.
The backend role cannot administer keys, buckets or IAM. An expiry tag cannot invoke deletion;
a local journal or export cannot establish off-host retention. Reusing the existing main role,
a shared account scheduler or another project's evidence bucket would violate project isolation.

The current teardown plan therefore correctly says
`BLOCKED_NO_INDEPENDENT_EXECUTOR_WITHIN_EIGHT_RESOURCE_ALLOWLIST`. The administrator execution
contract explicitly says that no scheduler is allowlisted and requires a different resource or
permission design to be resolved before execution. This is a design dependency, not a request
for another approval of the already authorized repository work.

## Concrete proposed boundary

`deployment/stage3/lifecycle-scope-correction.proposed.json` lists seven additional named objects:
a private key-independent evidence bucket; a lifecycle Lambda function; its execution role;
a Scheduler invocation role; a precreated log group; one recurring Scheduler schedule; and
one failure queue. They belong only to ChangeBridge in the assigned Sydney region. No new OIDC
provider, shared-role change, global repository-variable change or platform deployment is proposed.

The evidence bucket uses SSE-S3, versioning, all public-access blocks, owner-enforced ownership,
TLS-only access and private receipts. Its encryption must remain independent of the bootstrap
KMS key. Exact conditional object writes and a separately retained digest must bind one execution
and chain; reading a newly uploaded object back is insufficient proof of its long-term retention.
The public repository receives sanitized evidence only. Raw identities and alert endpoints stay
private. The controller's role is bounded to these named objects, the exact original inventory and
its explicit private evidence prefix. Its policy must be compiled and reviewed before deployment;
this proposal contains no executable policy or wildcard administrator grant.

The scheduler role invokes only the exact controller and writes delivery failures to its exact
queue. The controller checks its frozen package/execution identity and original resource receipts
on every invocation. It does not create a replacement bootstrap, infer ownership from names/tags,
remove foreign resources or delete anything with missing export, active locks or unresolved
identity. Duplicate delivery must resume from authoritative receipts. Missing acknowledgements
remain unknown until an operation-specific authoritative correlation is proven; repeated creates,
name/tag adoption and a local success envelope are forbidden.

## Deadline and retention correction

The original eight operational resources retain their 48-hour deadline. Begin guarded cleanup
by hour 46, leaving a two-hour operational margin, and independently observe actual completion.
An EventBridge schedule has 60-second invocation precision and may encounter delivery failures;
its existence is not a guarantee that cleanup met the deadline. Use UTC, a recurring 15-minute
schedule, flexible window OFF, bounded retries, failure routing and a fixed end date. Require
actual scheduled invocation and failed-delivery evidence before bootstrap admission.

The original exact KMS key must enter PendingDeletion by the 48-hour deadline, with the minimum
seven-day waiting period. It does not physically disappear at hour 48. The proposed seven
controller/evidence objects need a separately approved maximum ten-day retention exception from
first bootstrap creation: up to two operational days, seven deletion-wait days and one verification
buffer. This exception is explicit and unapproved; it must never be applied silently to the
original operational objects. If actual completion cannot fit, preserve evidence, mark the deadline
failure and obtain a concrete correction rather than declare completion.

After verified KMS absence, record the final complete inventory in a destination that remains
readable after retiring the controller and its evidence bucket. Bind exact exported versions and
independently retained digests before any final destruction. No blanket controller self-destruction
or deletion of the sole readable receipt is proposed. A verified external final-retention destination
is still required; this proposal does not manufacture one.

## Cost, preparation and execution gates

USD 3 is still the proposed bootstrap allowance, not accepted and not a hard cap. Current official
regional prices, bounded invocation/storage/log/queue volumes and all fifteen resources must be
estimated before creation. Do not rely on credits, free tiers or shared budget alerts to prove a cap.
If the accepted allowance cannot cover the design, request the exact revised allowance before use.

First review this scope and retention design. Then implement the exact controller, durable remote
journal, least-privilege policies, deployment/cleanup requests, independent verification and tests.
Qualify its runtime and any undeclared package separately. Publish and validate their exact source
head before using an authenticated administrator channel to create and qualify the seven
controller resources. Only after actual independent execution and evidence-export checks pass
may the original eight-resource bootstrap begin. New scope approval alone supplies neither
credentials nor a completed controller.

No AWS CLI or authenticated administrator channel is available in the current execution environment.
The accepted existing main OIDC role has no permissions and is not a substitute for that channel.
The user must supply a usable authenticated session or another approved execution connection;
no long-lived secret, session token or password should be pasted into chat. The assistant remains
responsible for the executable package, repository work, evidence validation and merges after all
criteria pass. Confirming an actual SNS email subscription also remains an external recipient action.

## Primary references

- https://docs.aws.amazon.com/scheduler/latest/UserGuide/schedule-types.html
- https://docs.aws.amazon.com/lambda/latest/dg/lambda-intro-execution-role.html
- https://docs.aws.amazon.com/kms/latest/developerguide/deleting-keys.html

These references explain API/runtime constraints. They do not certify the proposed design,
current pricing, effective permissions, actual schedule delivery or successful cleanup.
