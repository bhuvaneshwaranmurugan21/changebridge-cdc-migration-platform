# Stage 3 admission blocker review

This review is a proposal for resolving dependencies, not permission to create resources or change
acceptance requirements. No existing requirement is marked complete by substituting a proposal
for observed behavior.

## Verified progress

Both supplied archives match their SHA-256 identities and all 30 listed member checksums. Their
observations support `ST33-AC-33` (point-in-time name absence) and `ST33-AC-34` (regional read API
availability). Together with the original local packet this supports 32/52 criteria, not 36/52.
Neither archive records collection time, so requalification must carry UTC timestamps before
any authorized bootstrap. Absence is not reservation of an AWS name.

## Security dependency correction required

`ST33-AC-31` and `ST33-AC-32` require observed trust and candidate-role policies. The proposed role
does not exist. Those observations cannot precede its creation, while the authorization packet
currently requires all read-only gates to pass before creation. This dependency is circular.

A proposed correction is to review exact provider/audience, branch-bound OIDC trust JSON,
permissions and any permissions boundary before asking for creation authority, then verify actual
role trust and policy readbacks after authorized creation and before any role use. Both security
reviews must remain mandatory. This requires explicit authority correction; the requirements
remain pending as written. No role policy JSON is currently approved and no role is authorized.

## Headroom evidence still required

DMS account attributes expose usage and limits. Glue and Step Functions quota ceilings were
observed, but complete current usage and a bounded demand comparison were not collected. A
service limit is not unused capacity. Preserve `ST33-AC-35` pending.

## Cost and lifecycle decision still required

The USD 3 bootstrap-only allowance is proposed, not accepted. The USD 20 shared monthly budget
provides notifications, not automatic shutdown or a hard spend cap. USD 140 credit context is not
this stage's allowance. Preserve `ST33-AC-36` pending.

The contract requires maximum resource lifetime of 48 hours, but the proposed manifest retains
state/artifact resources through Part 3 and keys through project closure. KMS deletion is also
subject to a service waiting period. These policies are inconsistent; tagging expiry or recording
a disposition does not resolve them. A reviewed lifecycle policy must distinguish resource use,
evidence retention, and unavoidable pending deletion, and obtain approval for any exception.
Until then, do not create resources or silently reinterpret 48 hours as only an expiry tag.

## Remaining execution boundary

`ST33-AC-37` requires separate exact-resource authorization. `ST33-AC-38` through `45` require
real bootstrap configuration/readback, inventory and recovery evidence. `ST33-AC-46` through `52`
require the published exact head, PR validation, guarded merge, fresh main and final checkpoint.
Repository-only preparation cannot satisfy those requirements.

The focused Stage 3 checks pass, but the broader marker-filtered non-integration run fails the
unchanged repository coverage threshold (76.18% versus 85%). The untouched predecessor reproduces
the same result. This diagnoses a partial-validation coverage shortfall, not a Stage 3 regression;
it does not turn the failed command into a success. Complete repository quality validation remains
pending, and no threshold or test has been changed to obtain a passing result.

No AWS operation, resource creation, platform deployment or managed correctness is claimed by
this review. Resume from the preserved Stage 3 branch; do not restart completed predecessors.

## Subsequent exact-head verification

The historical partial coverage failure above remains unchanged. Exact head `ace53c1` subsequently
passed full repository CI with 308 tests, two existing PostgreSQL-service skips and 86.84% coverage;
Ruff, mypy, qualified Iceberg integration and predecessor-preservation validators passed.

Current main OIDC assumption succeeded in run `36984718071`. The Stage 3 branch assumption was
denied in run `36985888482`, before any IAM-policy readback. Read-only observer PR #17 uses the
already functioning main execution path and does not widen role trust or permission scope.
The absent new candidate role and actual bootstrap gates remain unproven. Zero AWS resource
mutations are recorded. This continuation is execution evidence, not a completion declaration.

## Fresh administrator observation and subject correction

The 2026-10-03 diagnostic records the exact existing role, main-only immutable trust, empty
inline and attached policy inventories, absent boundary, exact provider and absent candidate.
GitHub repository and owner IDs were independently checked. The proposed Stage 3 subject's
legacy name-only format was incorrect and is corrected to the immutable numeric-ID format.
This resolves the proposal error while preserving repository and branch isolation.

The four-read observer patch is unnecessary for facts already collected through the administrator.
The next operation must establish the full qualified bootstrap; neither repeating identity checks
nor changing the existing main role supplies the missing dedicated bootstrap route. Candidate
readback, quotas, cost/lifecycle and real bootstrap gates remain pending. No acceptance count,
historical failed run, completed predecessor evidence or AWS resource has been changed by this review.
