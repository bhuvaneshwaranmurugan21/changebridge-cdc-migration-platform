# Stage 3 execution approval: unresolved decisions

This is a proposed security and lifecycle resolution, not an approval receipt or an AWS
execution result. No AWS API was called to prepare it. The user's broad completion authorization
does not resolve the previously explicit destructive-action and retention gates. Acceptance
criteria must remain pending until their actual evidence exists.

## Exact security boundary

The only proposed resources remain the eight objects in `bootstrap-manifest.json`, in account
`857229544428`, region `ap-southeast-2`. No other-project resource may be adopted, changed, or
deleted. Fresh collision and ownership checks are mandatory before each mutation. An unexpected
or inaccessible existing resource blocks execution; matching names alone are not proof of ownership.

`oidc-trust-policy.proposed.json` binds the GitHub provider, audience and exact ChangeBridge Stage 3
branch. It does not authorize other repositories, `main`, pull-request subjects, or wildcard
subjects. `role-permissions.proposed.json` proposes only exact backend-state, lock-table and
read-only artifact access. It grants no workload deployment, platform, IAM administration,
bucket deletion, object deletion, or KMS administration permissions. Removing a Terraform lock
item is not permission to delete the lock table.

Both JSON documents wrap a proposed IAM `policy`; the wrapper is not an AWS policy document and
must never be submitted directly to AWS. The exact KMS key ARN is deliberately unresolved and
must come from an independently verified bootstrap receipt. The placeholder must not be replaced
by a wildcard. After approval of this exact policy template, substituting only the verified ARN
and recording the resulting exact policy digest require no additional approval. Any other policy
or scope change requires separate approval before attachment or use.
The state key and artifact prefix are proposals, not already assigned backend coordinates.

No managed permissions-boundary resource is proposed. The proposed boundary is explicitly none;
the created role's actual boundary, trust policy, inline policies and attached policies must be
read back and reconciled against the approved policy before assumption. An unexpected policy or
boundary fails closed. The absent candidate role is not evidence of an established secure role.

## Specific confirmations still required

1. Accept the proposed **USD 3 Stage 3 bootstrap allowance** for at most 48 active hours, including
   the bounded configuration and verification requests. The shared USD 20 monthly budget remains
   unchanged. Its alerts are notification controls, not a guaranteed hard spending cap. Portfolio
   credits do not increase the Stage 3 allowance.
2. Accept **48-hour teardown of every Stage 3 bootstrap resource other than the KMS key's mandatory
   pending-deletion residual**, measured from the first successful resource creation. No resource
   may stay operational beyond that deadline. An expiry tag is not automated enforcement, and
   merely writing a disposition plan does not satisfy actual teardown.
3. Explicitly approve the **sole KMS physical-retention exception**: after preservation of required
   evidence and teardown of dependent objects, schedule the exact key for deletion with a seven-day
   waiting period no later than the 48-hour deadline. The key must be `PendingDeletion`, not active,
   after 48 hours. AWS cannot physically delete the key immediately. The residual must be inventoried
   and its eventual deletion independently verified; do not claim the key vanished within 48 hours.
4. Replace any conflicting "retain through Part 3" text with the approved 48-hour disposition.
   Retaining state, artifacts, or other bootstrap resources through later stages requires separate
   explicit retention/lifetime approval before mutation; it cannot be inferred from completion urgency.
5. Before destructive cleanup, obtain **separate exact cleanup authorization** identifying the
   bootstrap execution, resource ARNs/immutable IDs, inventory digest, evidence-export digest,
   selected bucket object versions/delete markers, and exact KMS key ARN. Confirm no active locks,
   no unexported state, and successful preservation of required evidence. Never delete objects
   needed by another project or make required evidence unreadable by deleting its only decryption key.

If cleanup authority or safe evidence retention is unresolved before creation, creation remains
blocked. A partial bootstrap must be recorded accurately; it is not a completed acceptance gate.
Email alerting remains pending until the operator confirms the SNS subscription and the exact
confirmed subscription is read back. No policy draft, expiry tag, or proposed cleanup substitutes
for bootstrap, alert-confirmation, verification, pull-request or merge receipts.

## AWS reference boundaries

- [KMS ScheduleKeyDeletion API](https://docs.aws.amazon.com/kms/latest/APIReference/API_ScheduleKeyDeletion.html):
  the waiting period must be 7–30 days; seven days is the proposed residual, not immediate deletion.
- [Managing costs with AWS Budgets](https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-managing-costs.html):
  notification delays can permit actual costs to exceed a budget threshold.
- [SNS email subscription confirmation](https://docs.aws.amazon.com/sns/latest/dg/sns-email-notifications.html):
  an email subscription must be confirmed before it is active.
