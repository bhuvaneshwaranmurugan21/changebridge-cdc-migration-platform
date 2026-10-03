# Stage 3 bounded existing-role observer remediation

The main IAM observer authenticated as `ChangeBridgeGitHubOidcRole` but was denied `iam:GetRole`:
AWS reported that no identity-based policy allows the action. This is not evidence of an explicit
deny, SCP, permissions boundary, or missing administrator permission. Those controls remain unobserved.

`ChangeBridgeStage33RoleObserver.proposed.json` is a valid minimal IAM document for one inline
policy named `ChangeBridgeStage33RoleObserver`, attached only to the existing role ARN
`arn:aws:iam::857229544428:role/ChangeBridgeGitHubOidcRole`. It permits four reads of that exact
role: `GetRole`, `ListRolePolicies`, `ListAttachedRolePolicies`, and `GetRolePolicy`. It does not
permit any IAM write, trust change, policy attachment, other-role read, or self-grant by the target role.
Preparation creates no new logical AWS resource and records no actual AWS write.

The later standing ChangeBridge delegation covers preparing and resolving this bounded access
gap. An actual qualified administrator connection is still required; verbal authorization and
GitHub identity-only credentials do not supply the missing AWS permissions. The optional
administrative executor `scripts/install_stage33_role_observer.sh` defaults to read-only preflight
and requires a reviewed exact policy-file SHA256. It freezes the policy bytes in a private
receipt directory before hashing, validating and submitting that same snapshot. Explicit apply
also requires independently reviewed `--expected-role-id` and `--expected-trust-sha256` values
from the qualified preflight; changed role identity or trust blocks the write. It verifies account `857229544428`, region
`ap-southeast-2`, an actual `AccountFullAccessRole` session, target role ARN/RoleId, and target-policy
absence or exact equivalence. A mismatched same-name policy blocks execution and is never overwritten.

The executor's explicit apply mode can make only one `PutRolePolicy` write, and then verifies the
actual canonical policy digest, stable role identity, unchanged trust and unchanged permissions boundary. A second execution
with the identical policy makes no write. Ambiguous acknowledgement is reconciled by readback,
not blind retry. Denied or inconclusive calls retain actual stderr and exit status. `PutRolePolicy`
has no conditional create/CAS API: use a qualified exclusive executor and do not describe a
read-then-write collision check as atomic.

After the real Phase 1 receipt, rerun the bounded observer from exact merged main. Attached-policy
and permissions-boundary ARNs must be collected before preparing any Phase 2 `GetPolicy` or
`GetPolicyVersion` grant. Its resources must contain only those independently observed ARNs; no
wildcard or guessed managed-policy/boundary ARN is permitted. An actual boundary or SCP denial
must be resolved at its true controlling layer, without disabling or weakening it for convenience.

This remediation does not establish the new candidate bootstrap role, grant bootstrap mutation
permissions, change OIDC branch trust, confirm quotas, or complete Stage 3. Raw administrator
identity receipts are private; redact session identities before any public evidence commit.
Removing this exact inline observer policy after its purpose ends requires proof that it is the
same policy installed by this execution; no existing unrelated permission may be deleted.
