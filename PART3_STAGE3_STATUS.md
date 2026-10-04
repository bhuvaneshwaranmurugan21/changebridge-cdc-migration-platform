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
