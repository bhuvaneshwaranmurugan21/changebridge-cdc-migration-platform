# ChangeBridge Part 3 Stage 3 status

`PART3_STAGE3_AWS_ADMISSION_PENDING_ADMINISTRATOR_CHANNEL_AND_BOOTSTRAP_PROOF`

- Entry checkpoint: `PART3_STAGE2_DEPLOYABLE_PLATFORM_VERIFIED`
- Entry commit: `084407a972d2d3f937e8ac670733f198dd4b0179`
- Entry tree: `3a5ceefaf9dcfcbe97da5a593f76eab0cd5fe257`
- AWS account: `857229544428`
- AWS region: `ap-southeast-2`
- Shared budget: USD 20 monthly
- Alert endpoint: verified and redacted
- Maximum resource lifetime: 48 hours
- Acceptance: 32/52 passed; 20 pending. No requirement has been weakened or rephased.
- Proposed bootstrap allowance: USD 3, not yet accepted and not a hard spend cap.
- AWS mutations: 0
- Claim ceiling: `AWS_ADMISSION_OBSERVED`
- Current gate: exact candidate-role trust and permissions, quota usage headroom, cost acceptance,
  and lifecycle/retention contradiction resolution. The absent role blocks its observation gates.
- Execution authority: standing ChangeBridge-only delegation is recorded; real IAM, budget,
  lifecycle and bootstrap evidence gates remain mandatory.
- Next checkpoint: `PART3_STAGE3_AWS_ADMISSION_VERIFIED`

Both supplied evidence archives and their internal checksums were verified. Collision observations
and regional read API availability pass; archive capture times are unknown and require fresh
timestamped qualification before mutation. Shared budget alerts do not cap spending.

The candidate is published in draft PR #16. Exact head
`ace53c1455ee0fe2b671173ee96320413c14c179` passed all three repository CI lanes:
308 tests, two existing PostgreSQL-service skips, 86.84% coverage against the unchanged 85%
requirement, Ruff, mypy and protected predecessor validators. The earlier partial-run failure
below remains historical evidence; it is not the current full-quality result.

The existing `ChangeBridgeGitHubOidcRole` successfully assumed through the main identity workflow
in run `36984718071`. Stage 3 branch run `36985888482` passed its exact scope guard but failed
OIDC assumption with `Not authorized to perform sts:AssumeRoleWithWebIdentity`; IAM readback
did not execute. This does not identify the precise denying trust-policy condition.
Read-only observer maintenance PR #17 addresses observation through main without changing AWS
trust or permissions. Its merge is not Stage 3 completion. The bootstrap and final merge remain
pending their actual acceptance evidence.

Validation: 14 focused tests, Stage 3 Ruff, Bash syntax, diff whitespace and protected evidence
checks pass. A broader non-integration run passed 285 tests but failed the unchanged 85% coverage
requirement at 76.18%. The untouched entry reproduced 76.18% (271 tests passed). This subset is
not a successful full repository quality lane; see `evidence/part3/stage3/local-validation.json`.
The subsequent passing full lane is recorded separately in `evidence/part3/stage3/exact-head-ci.json`.

Main observer run `36987017324`, at merged main `80d929274f85bfcebcdbc6dd014831db5915d811`,
passed OIDC and STS identity but failed `iam:GetRole`: no identity-based policy allows the action.
An authorized administrator execution channel is needed to grant the bounded observation access.
Standing user authorization is already present; another verbal approval does not supply AWS permissions.
Trust, effective policy, quota and bootstrap proof remain pending.

The existing Stage 3 branch now incorporates the accepted main observer maintenance through a
normal merge. The bounded administrator remediation remains prepared and unexecuted. Its installer
submits the same private policy-byte snapshot that it hashes and validates; explicit apply requires
reviewed RoleId and trust digest and verifies unchanged trust and boundary. No AWS resource write
has occurred. The current candidate must earn its own CI result; the earlier exact-head result
above is historical proof, not a passing result for changed code. See
`evidence/part3/stage3/autonomous-continuation.json`.

The evidence builder now refreshes hashes only. Regenerating the manifest cannot overwrite
observed denials, historical failed validation or stage receipts with hardcoded preparation data.

Current local full-quality verification: 347 passed, two existing PostgreSQL-service skips,
86.84% coverage against the unchanged 85% requirement, Ruff, mypy on all 50 source files and all
11 predecessor validators pass. The new remote candidate requires its own exact-head CI.
No AWS write or Stage 3 completion is claimed.

All three CI workflows for exact head `9d465a6b67b798d3bc6c852844a3cda68d9772b0`
have now completed successfully, including the full quality lane. The new access diagnostic is
prepared to collect current own-role and exact-provider controls directly through one authenticated
administrator session, with sanitized terminal JSON and no archive download or AWS mutation.
It avoids granting the optional observer policy solely to obtain those controls. The dedicated
execution-role design and remaining bootstrap gates still require real AWS evidence; neither
the four-read patch nor the diagnostic provides deployment permissions. Changed diagnostic code
requires its own exact-head CI. See `docs/part3/stage3/AWS_EXECUTION_CONNECTION.md`.

The administrator diagnostic received on 2026-10-03 verifies exact immutable main trust,
no inline or attached policy, no boundary and candidate absence. Its control digest is checked
against the received normalized role fields; GitHub metadata independently confirms the IDs.
The Stage 3 proposal now uses the exact immutable repository identity. The optional observer
patch is unnecessary for this review and remains unexecuted. The next required work is the
qualified administrator bootstrap executor and its real receipts; Stage 3 remains 32/52.

Resume checkpoint: the existing published head `451f8b43cb89aa970ce7ebc3b4cee4fa3c22e929`
was recovered without restarting the stage. An offline bootstrap request compiler now freezes
all eight allowed resources, exact proposed policies, source hashes, serial prerequisites and
required actual readbacks into a private, non-executable package. Its eleven construction and
negative tests pass. The complete AWS installer and lifecycle executor remain unfinished;
no AWS admission criterion is newly marked PASS. This session has no AWS CLI, credential
environment or credentials file, and plugin discovery found no available AWS execution connector.
The standing authorization remains recorded; the authenticated administrator channel is still
missing. Existing AWS evidence and protected predecessor evidence remain unchanged.

Latest resume validation: 396 tests pass, two existing PostgreSQL-service skips, 86.84% coverage;
Ruff, repository mypy, compiler mypy and all eleven predecessor validators pass. Compiler mypy
exposed two existing validator type annotations, corrected without changing runtime checks;
41 focused tests then passed. CloudShell also returns `Site Unavailable` in this session.
See `evidence/part3/stage3/bootstrap-preparation-resume.json` for actual results and remaining work.

Continuation from published `7b234811543c788ac399e578fd946fe9f671a9a1`: a bounded
read-only qualification runner and private durable journal are implemented. Real local process
crash, integrity, writer exclusion and exact-scope rejection tests pass. Cleanup selectors are
compiled with identity/version guards but cannot execute deletion. Mutation execution, mutation
recovery, lifecycle enforcement and the authenticated administrator channel remain unfinished.
469 tests pass, two existing PostgreSQL service skips, 86.84% coverage; 84 focused checks,
Ruff, mypy and frozen predecessor checks pass. Historical receipts remain unchanged.
Stage 3 remains 32 PASS / 20 PENDING, with zero AWS API calls or mutations in this continuation.
See `evidence/part3/stage3/bootstrap-components-resume.json`.

2026-10-05 continuation from `64b76b264e65a9119493ca68787a0302e480c81d`: mutation-attempt
recording now preserves unresolved outcomes through actual process exits and uncommitted SQL
transaction rollback. It neither executes writes nor certifies observations. A dedicated-role
readback comparator rejects trust/permission widening, unbound key identities, unexpected
boundaries, duplicate policy keys and incomplete pagination. Qualification now explicitly
rejects partial empty inventories and ambiguous JSON responses. Proposal retention text is
consistent with the 48-hour operational deadline and seven-day KMS residual; concrete cleanup
execution and lifecycle admission remain unresolved. No historical evidence was rewritten.
525 tests pass, two existing PostgreSQL-service skips, 86.84% coverage; all existing predecessor
validators pass. No AWS API call or mutation occurred. The browser still reports Site Unavailable,
and no AWS execution connector is available. Stage 3 remains 32 PASS / 20 PENDING. Mutation
execution, operation-specific authoritative recovery and enforceable cleanup remain unfinished.

Additional review found a concrete backend mismatch: the customer-key-encrypted lock table
needs a DynamoDB caller decryption path, while the previous role template allowed KMS only
via S3. The proposal now includes only table/account-context-restricted `kms:Decrypt` through
Sydney DynamoDB on the same verified key. No new resource or direct key/grant/admin access is
proposed. Actual policy effectiveness and fresh-caller backend operations remain pending.

Final local continuation validation: 540 tests pass, two existing PostgreSQL-service skips,
86.84% coverage; 185 focused Stage 3 checks pass. SNS cleanup selectors now distinguish
returned pending subscription ARNs from confirmed subscriptions and reject missing or
non-Boolean confirmation state. All cleanup output remains non-executable. Admission
remains 32 PASS / 20 PENDING; no AWS operation or managed proof was performed.

## Resource-control continuation — 2026-10-05

Resumed from 6a655b550045a8e9483c4f78de13e4aa96998712 without restarting.
Exact KMS, approved-bucket and lock-table control comparators now reject physical
identity, policy, encryption, ownership, state and complete-inventory mismatches.
The KMS attempt inspector re-reads the private durable chain and requires an exact
concrete creation-tag binding and unambiguous saved acknowledgement. Pending mutation
and use/retry prohibitions remain in effect. KMS creation tags now use the correct
TagKey/TagValue wire shape; other services retain their proper Key/Value shapes.

Final local validation: 631 tests pass, two existing PostgreSQL-service skips,
86.84% coverage; 90 resource-control/attempt checks pass. Typing passes for 46 source
files. No dependency/provider declarations changed, no AWS call/mutation occurred,
and accepted predecessor evidence remains unchanged. Stage 3 remains 32 PASS / 20
PENDING. Full execution coordination, authoritative unknown-outcome recovery,
independent cleanup enforcement/export and actual AWS admission remain unfinished.

## Private-export continuation — 2026-10-07

Resumed from `34e3b078f13976d6e8c034f738bc56df705c8892` without restarting. A private
mutation-attempt exporter now freezes the durable record chain under the writer lock and
verifies it independently using a separately retained file digest. Actual process exit and
source-journal removal tests demonstrate local readback without the source database or KMS.
Exports reject overwrite, unsafe paths/permissions, altered receipts and unsupported success
transitions. Pending attempts remain pending. This component does not establish AWS provenance,
complete state/artifact export, durable off-host retention or deletion authority.

Validation: 665 tests pass, two existing PostgreSQL-service skips, 86.84% coverage; 34 new export
checks pass; all 13 authority/evidence validators, repository lint and typing for 62 source files
pass. The initial full run correctly rejected incomplete manifest integration; the required-file
list was extended to include both new artifacts and hashes regenerated, then the complete suite
passed. No check or acceptance criterion was weakened. No dependency/provider declaration,
application/runtime behavior or accepted predecessor evidence changed.

Stage 3 remains 32 PASS / 20 PENDING; no AWS API call or mutation occurred. The current available
tools include GitHub but no AWS execution connector, and the host has no AWS CLI. Existing OIDC
identity alone provides no bootstrap permission. Full mutation coordination, operation-specific
authoritative recovery, independently enforceable cleanup, externally retained evidence and live
admission/backend/alert/OIDC proofs remain blocking. Do not merge the draft PR or represent the
local export receipt as a completed AWS gate. See `evidence/part3/stage3/private-export-resume.json`.

## Request binding, scoped readback and lifecycle design — 2026-10-07

Resumed from `a5efdc29c54c647f39ce992894e9845f7ac18188` without restarting. All twenty
bootstrap requests now have strict concrete binding construction, including both KMS policy
paths, an independently approved private alert endpoint digest, immutable execution identity
and actual creation-bound expiry rechecks. Construction grants no execution or prerequisite
approval. A read-only first-key coordinator journals every scoped STS/KMS read before invocation,
preserves raw outcomes, checks identity before key reads, and requires explicit preservation of
interrupted/failed reads before fresh observation. Actual local process denial and SIGKILL tests
leave the original mutation pending; no dependent mutation, use or retry is authorized.

Final validation: 722 tests pass, two existing PostgreSQL-service skips, 86.84% coverage; 57 new
focused checks pass; all 13 authority/evidence validators, Ruff and typing for 54 checked source
files pass. Four initial negative tests exposed a PATH setup error hiding Git; the setup now keeps
real source-integrity validation available. No failing validation was bypassed or weakened.
Accepted predecessor evidence, runtime/application artifacts and dependency/provider declarations
remain unchanged. No AWS API call or mutation occurred.

The existing eight-resource allowlist still cannot provide an independent deadline executor or
key-independent durable evidence destination. A concrete seven-resource lifecycle/evidence scope
and ten-day controller-retention correction is proposed in `LIFECYCLE_SCOPE_DECISION.md` and its
JSON manifest. It is unapproved, unimplemented and unproven. Original acceptance criteria,
48-hour operational deadline, eight-resource manifest and teardown fail-closed status remain
unchanged. The proposal is not a deployable policy package or permission to create its resources.

Stage 3 remains 32 PASS / 20 PENDING. Review that design correction before implementing expanded
lifecycle coordination; an authenticated administrator execution channel is still required for
actual AWS qualification. Full mutation coordination, authoritative recovery, independent cleanup,
external retention and live OIDC/backend/alert proofs remain unfinished. Do not merge draft PR #16
or represent passing repository CI as live admission. See `coordination-design-resume.json`.

## Approved lifecycle preparation — 2026-10-07

Resumed from `c99ac491e5764bac81b413e494c83bc5e616cca6` without restarting. The user approved
the seven named lifecycle/evidence resources and the maximum ten-day retention exception.
`lifecycle-authority.json` freezes that approval against the original proposal digest. It does
not accept the proposed USD 3 allowance or authorize creation before policies, cost and execution
gates pass. The original bootstrap manifest, proposal, acceptance registry, teardown plan and
48-hour operational deadline remain byte-identical.

New components construct scoped lifecycle/Scheduler policies, conditional evidence writes and
bounded schedule requests. A durable local reference and an unqualified S3 adapter implement
immutable journal records plus conditional head commits. Real files/processes exercise competing
writers, identical concurrent intents, SIGKILL, process exit between event/head, corrupted records,
stale revisions and lost local acknowledgements. None permits target retry or claims managed success.
PITR retirement is now explicitly ordered after preserved admission/export/quiescence proof and
before table deletion; no PITR admission requirement is weakened. Source review corrected KMS alias
deletion to require both the exact alias and its exact associated physical key.

Validation: 771 tests pass, two existing PostgreSQL-service skips, 86.84% coverage; 65 focused
checks pass; all 13 authority/evidence validators, Ruff and typing for 56 checked source files pass.
The direct-script validator import path was corrected so both CLI and imported validation execute
the approval check. No dependency/provider declaration, runtime/application artifact or accepted
predecessor evidence changed. No AWS API call, resource creation or merge occurred.

Stage 3 remains 32 PASS / 20 PENDING. The controller handler, full mutation coordination,
operation-specific unknown-outcome recovery, runtime qualification, independently retained final
exports, cost acceptance and authenticated AWS execution/actual admission remain unfinished.
The scope approval is complete; do not request it again. Keep draft PR #16 unmerged until all original
criteria pass. See `LIFECYCLE_IMPLEMENTATION.md` and `lifecycle-preparation-resume.json`.
