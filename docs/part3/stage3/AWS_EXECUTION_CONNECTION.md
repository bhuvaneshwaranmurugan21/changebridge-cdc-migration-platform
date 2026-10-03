# Resolve the AWS execution connection

The missing capability is an authenticated AWS administrator execution channel, not user
authorization. The main GitHub workflow can assume `ChangeBridgeGitHubOidcRole`, but its actual
`iam:GetRole` call was denied. The Stage 3 branch cannot assume that role. Neither failure proves
the complete current trust, permissions boundary, attached policies, or bootstrap permissions.

The four-read observer installer remains an optional bounded diagnostic remediation. It does
not provide bootstrap or platform deployment access. Direct inspection through one authenticated
`AccountFullAccessRole` session can collect the necessary controls without installing that policy.

## Minimal next handoff

`scripts/collect_stage33_access_diagnostic.sh` is a read-only, ChangeBridge-specific collector.
Run only its checksum-verified published bytes in AWS CloudShell in account `857229544428`,
region `ap-southeast-2`. It prints a sanitized JSON result in the terminal. There is no archive
download, IAM write, resource creation, or credential export. Keep its private raw receipt directory
private; the terminal result excludes the administrator session identity.

The result allows independent review of actual role trust, inline policies, attached-policy and
boundary versions, the exact GitHub OIDC provider, and candidate-role collision. Collection does
not mean admission passed. Any denial, policy drift or ambiguous candidate observation stops the
collector and retains the original private failure receipt. Existing stage acceptance criteria
remain unchanged. A fresh full regional qualification is still required before bootstrap mutation.

## Reusable execution route

1. Review the real administrator diagnostic and fresh Stage 3 qualification. Preserve the existing
   main role and the repository's global role variable; never borrow another project's role.
2. Prepare and validate exact bootstrap changes and any required execution-role permissions
   against observed controls, account, region, resource names, cost and lifecycle authority.
   Record the exact documents and immutable digests before the administrator executes them.
3. Establish the dedicated `ChangeBridgePart3GitHubActionsRole`, then read back its actual trust,
   permissions and boundary. Bind a dedicated workflow to it and prove real branch assumption.
   Check the actual OIDC subject format; do not infer a trust correction from a failed assumption.
4. Execute only the authorized ChangeBridge steps through short-lived GitHub OIDC sessions,
   retaining policy, operation, readback, cost and teardown evidence.

The current candidate role template provides backend and artifact access only and trusts only the
Stage 3 branch. It cannot deploy the remaining platform or automatically authorize later branches.
Later scoped roles or exact subject updates must be prepared and qualified before use. This is a
reusable execution design, not a claim that one diagnostic command has enabled every AWS operation.

GitHub OIDC removes the need for long-lived AWS access-key secrets. AWS recommends restricting
the trust subject to the intended repository and branches:

- https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws
- https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_create_for-idp_oidc.html

At preparation time no AWS connector or administrator session is available to this execution
environment. If that remains true, executing this read-only command in an authenticated CloudShell
is the indispensable external step. Additional verbal permission cannot supply credentials or
override AWS IAM. No access keys, passwords, session tokens, or one-time login codes belong in chat.
