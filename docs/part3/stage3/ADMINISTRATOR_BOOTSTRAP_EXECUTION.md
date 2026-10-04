# Administrator bootstrap execution contract

This is the concrete preparation contract for one authenticated, checksum-bound ChangeBridge
administrator run. A complete installer implementing this contract is not yet present or
verified. This document does not establish an AWS resource, grant access, or satisfy an execution
criterion. The Stage 3 registry remains **32 of 52 PASS, 20 PENDING** until the required actual
evidence is validated. Existing accepted Part 1 and Part 2 evidence remains immutable.

## Observed root cause and execution route

The operator's read-only diagnostic ran on 2026-10-03 from 05:20:54Z to 05:21:07Z in account
`857229544428`, region `ap-southeast-2`, through `AccountFullAccessRole`. It observed
`ChangeBridgeGitHubOidcRole`, immutable RoleId `AROA4PFW4ZPWEB3YXXLX3`, with no inline policies,
no attached policies and no permissions boundary. Its trust accepts only
`repo:bhuvaneshwaranmurugan21@276895096/changebridge-cdc-migration-platform@1332970949:ref:refs/heads/main`
with audience `sts.amazonaws.com` and the account's exact GitHub OIDC provider.
`ChangeBridgePart3GitHubActionsRole` was absent with a qualified `NoSuchEntity` response.

The existing role can prove identity on main; it provides no bootstrap permissions. Installing
four self-inspection permissions would not resolve execution access and is unnecessary for
the information already collected. Preserve that role, its trust and all repository-global role
variables. No resource from LedgerGuard or another project may be read for adoption, changed,
reused or deleted as part of this bootstrap.

The reusable route is administrator creation and configuration of the exact Stage 3 bootstrap,
followed by real dedicated-role OIDC assumption and bounded backend verification. The new role
must retain the reviewed backend-state, lock and read-only artifact permission boundary of
`role-permissions.proposed.json`. That role is not an administrator, bootstrap creator, platform
deployer or Stage 4 executor. Later deployment permissions and trust subjects require their own
concrete scoped authority; completion urgency does not supply them.

## Required executable package before the handoff

Prepare and validate one immutable installer package containing the execution contract, exact
resource manifest, policy documents, source checksums and deterministic operation plan. Freeze
the bytes before using them. The package must expose check-only and explicitly authorized
execution modes, retain private raw receipts, and emit a sanitized terminal summary without
credentials, administrator session identifiers or email addresses. Generated receipts must bind
the package digest, repository commit/tree, account, region, execution ID and timestamps.

Correct the dedicated role's proposed ordinary repository subject to the actual immutable-ID
subject format and the exact `part3-stage3-aws-admission` ref before administrator execution.
Validate the dedicated workflow's actual audience and subject without publishing its OIDC token.
Do not widen trust to wildcard branches, pull requests, another repository or another project.
The larger diagnostic identity-controls digest is not a trust-only digest and must not be supplied
to an argument that expects one. Submit the inner IAM `policy`, never its proposal wrapper.

The installer must be tested for real JSON validation, exact identity guards, deterministic
operation construction and failure handling. Local tests are evidence about the installer;
they are not AWS bootstrap receipts or policy-effectiveness proof. No mocked AWS success may
satisfy a managed acceptance criterion.

## One administrator run, with mandatory gates

1. Freeze and verify the reviewed package, bind the exact account and region, and verify the
   actual caller is the qualified `AccountFullAccessRole`. The role name alone is not proof that
   every required mutation is allowed. Preserve actual denied-operation errors; never infer
   absence or permission from a generic failure.
2. Repeat fresh qualification within this same run: exact provider, existing-role controls,
   candidate collision, every named bootstrap collision, required regional API availability,
   bounded quota usage and headroom, and the approved cost/lifecycle disposition. Quota ceilings
   alone are not available headroom. An inaccessible collision cannot be treated as absence.
   Match immutable identities and ownership, not names alone. No policy simulation or administrator
   privilege is a substitute for actual execution and readback.
3. Bind the exact eight-resource manifest and the accepted USD 3 bootstrap allowance, at most
   48 active hours from first successful creation, before the first write. Resolve conflicting
   retention language and prove the authorized cleanup route and evidence export are viable.
   Do not start if safe cleanup or retention is unresolved.
4. Create or authoritatively reconcile only the allowlisted objects below, with prerequisite
   dependencies respected. Unknown existing objects stop the run. Never overwrite an unrelated
   object or destructively replace a partial result to obtain success. Record original request,
   acknowledgement, immutable identity and actual configuration after every operation.
5. Establish the dedicated role only after the verified physical KMS key ARN can be bound into
   its exact permissions. Read back its real RoleId, trust, every inline and attached policy,
   any boundary, and the exact referenced policy versions. Reject unexpected permissions or
   observed drift. Complete this security observation before the first dedicated-role use.
6. Publish the dedicated workflow with its own explicit role ARN rather than changing a global
   variable. Prove actual assumption from the exact authorized subject, and perform bounded
   backend, locking and artifact-read verification against the created identities. Verify genuine
   denied out-of-scope operations without mutating another project's resources. Capture actual
   idempotency and ambiguous-acknowledgement reconciliation results; do not assert unseen success.
7. Complete alert confirmation, resource inventory, evidence export and acceptance reconciliation.
   Run existing validators and complete exact-head CI, guarded merge, fresh-main verification and
   the continuation checkpoint only after every required Stage 3 criterion has actual evidence.

The run may stop with a bounded partial-bootstrap receipt. Resume from its immutable inventory
and verified identities; do not restart creation or request successive manual read-only reports.
One authenticated invocation does not guarantee that an external SNS confirmation is available.

## Exact allowlist and configuration receipts

| Object | Exact name or identity | Required actual receipt |
|---|---|---|
| KMS key | Newly assigned key ARN in the bound account and region | Key identity, state, policy, ownership and lifecycle disposition |
| KMS alias | `alias/changebridge-p3s3-state` | Exact target key ARN and ownership |
| State bucket | `changebridge-p3s3-tfstate-857229544428-ap-southeast-2` | Owner, region, versioning, encryption with the verified key, all public-access blocks, bucket-owner-enforced ownership, TLS policy and tags |
| Artifact bucket | `changebridge-p3s3-artifacts-857229544428-ap-southeast-2` | Same storage controls, plus exact uploaded artifact versions and checksum binding |
| Lock table | `changebridge-p3s3-tf-locks` | ARN, status, schema, encryption, point-in-time recovery and tags |
| Alert topic | `changebridge-p3s3-alerts` | ARN, configured access and tags |
| Email subscription | Exact approved endpoint kept private | Actual confirmed subscription ARN and exact topic/endpoint binding, with public endpoint redacted |
| Dedicated role | `ChangeBridgePart3GitHubActionsRole` | RoleId, actual exact trust, permissions, boundary observation and successful bounded OIDC use |

No new OIDC provider, permissions-boundary resource, scheduler, DMS resource, Glue resource,
migration bucket or platform deployment is part of this allowlist. If the configuration requires
another resource or a different permission design, stop and resolve that design explicitly.

## Security observation timing and unchanged acceptance semantics

Before creation, observe the actual provider and qualify the intended exact subject and candidate
absence. An absent role has no actual permissions or boundary to inspect. Its absence is not
a secure-role receipt. After authorized creation, observe the dedicated role's actual trust,
permissions and boundary, and then prove its use. This removes the sequencing deadlock without
weakening the requirement that security controls be observed before use.

`ST33-AC-31` and `ST33-AC-32` remain pending until their full required observations exist; the
existing main role is not interchangeable with the candidate. Preserve the registry and its
failure semantics. Collision and regional API observations must be refreshed before mutation;
they do not prove deployment capability. The diagnostic does not establish quota headroom,
approved cost disposition, bootstrap success, subscription confirmation or project completion.

## Lifecycle, recovery and evidence preservation

USD 3 remains the proposed bounded Stage 3 allowance and must be made concrete in the execution
authority record before creation; this document does not record its acceptance. Portfolio credits
and the shared monthly budget do not increase it. Budget and SNS notifications are alerts, not hard spending caps. Record the cost
estimate, run timestamps and remaining allowance, and stop new work when a bound is exceeded.

Every operational bootstrap resource must be torn down within 48 hours of the first successful
creation. An expiry tag, a future plan or an expiring CloudShell session is not enforcement.
The sole physical-retention exception is the exact KMS key: after evidence preservation and
dependent cleanup, schedule its deletion with the minimum seven-day waiting period no later than
the 48-hour deadline. It must be `PendingDeletion`, not operational, after that deadline; record
the residual and later verify actual deletion. Do not claim the key physically vanished in 48 hours.

Before destructive cleanup, bind the authorized executor to exact ARNs and immutable IDs,
inventory digest, exported evidence digest, selected bucket object versions and delete markers,
and the verified key ARN. Prove no active locks or unexported state remain. Preserve required
receipts and evidence in a durable destination readable after the key is deleted; export and
verify before cleanup. Teardown must never erase another project's data or the only decryptable
copy of accepted evidence. No retention beyond the approved lifetime may be assumed.

For any failed acknowledgement, record the original error and reconcile through authoritative
readback before retrying. Unknown outcomes and mismatched identity or configuration stop the run.
Do not blindly repeat IAM or resource writes, widen policy, disable validation, or claim partial
configuration as completed bootstrap. SNS email confirmation requires an actual recipient action;
`PendingConfirmation` cannot be relabelled as success or replaced with the existing budget email
subscriber. Wait only within bounded execution limits and otherwise preserve a pending checkpoint.

## Remaining external conditions after preparation

- An authenticated administrator must execute the exact reviewed installer; repository access
  and verbal delegation do not create an AWS administrator session.
- Actual AWS operations must pass effective permissions and fresh qualification. Unexpected
  denial or collision requires diagnosis, not automatic access escalation or adoption.
- The email recipient must confirm the exact SNS subscription if it is newly created.
- An authorized, viable cleanup executor and durable evidence-export route must exist before
  creation; the declared eight resources provide no automatic expiry mechanism by themselves.

Once these conditions and real execution receipts exist, the dedicated OIDC route can remove
repeated CloudShell handoffs for its permitted backend work. It does not itself enable the
remaining platform stages or prove managed migration, performance, publication or rollback.

## Offline request compiler checkpoint

`python -m scripts.prepare_stage33_bootstrap --output /tmp/changebridge-bootstrap-package.json`
creates a new mode-0600 file and refuses overwrite or symlink substitution. It performs no AWS
operation. The package freezes source hashes, the exact eight-resource request scope, ordered
prerequisites, key/email/expiry placeholders, the inner role policies and required actual readbacks.
It labels itself `OFFLINE_REQUEST_PACKAGE_NOT_AWS_PROOF` and keeps execution disabled. It rejects
account, region, lifetime, resource-inventory and proposed-policy drift.

This compiler is **not the complete installer**. The separate read-only qualification runner and private fsynced journal now exist; the
mutation runner, mutation recovery, ownership adoption and cleanup executor remain unimplemented. Its serial request
sequence is a construction plan, not permission to send requests: table readiness, collision
qualification, resolved bindings and all prior execution gates remain mandatory. In particular,
the KMS create acknowledgement must be reconciled before any key-dependent request, the table
must be ACTIVE before PITR configuration, and the SNS subscription must be genuinely confirmed.
No generated package or unit test satisfies an AWS acceptance criterion. Do not substitute literal
placeholders into a live AWS command or treat the package digest as an execution receipt.

The package records its Git base commit/tree and whether the working tree was dirty.
`python -m scripts.prepare_stage33_bootstrap --verify /tmp/changebridge-bootstrap-package.json`
rejects changed requests, stale sources or changed Git identity, even if the caller recomputes
the payload digest. Verification is local integrity checking and does not authorize execution.

## Read-only qualification and cleanup selectors

`qualify_stage33_bootstrap.py` permits only exact identity, security-control and collision reads.
Its private journal persists intents and raw receipts before decisions, rejects torn or altered
records and prevents concurrent writers. A lost read acknowledgement remains unknown; explicit
read-only resume preserves that outcome before fresh observation. Errors are not resource absence
unless their exact operation and qualified service error agree. Neither a local hash chain nor
structural tests authenticate an AWS observation. No quota or complete admission proof is claimed.

`prepare_stage33_cleanup.py` compiles selectors from a supplied inventory. It rejects foreign
resources, unresolved keys, pending subscriptions and unsafe or duplicate object versions.
Selectors require actual ownership, lock, version and independently readable export guards;
these guards are not an implemented deletion executor. Bucket creation dates are not immutable
identities, and many named AWS mutations lack an ownership compare-and-set. A planned seven-day
KMS deletion is neither immediate physical deletion nor proof of the 48-hour operational deadline.
The lifecycle enforcement design and authenticated administrator channel remain blocking.
