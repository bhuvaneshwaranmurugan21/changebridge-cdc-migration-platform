# Stage 3 exact-bootstrap authorization packet

Before mutation, a read-only operator probe must prove OIDC trust, candidate-role boundaries,
regional service availability, quota headroom, and absence of name collisions. The resulting
evidence must be reviewed alongside `deployment/stage3/bootstrap-manifest.json`.

If every read-only gate passes, the requested mutation authority will cover only these proposed
objects:

- KMS key plus alias `alias/changebridge-p3s3-state`;
- S3 bucket `changebridge-p3s3-tfstate-857229544428-ap-southeast-2`;
- S3 bucket `changebridge-p3s3-artifacts-857229544428-ap-southeast-2`;
- DynamoDB table `changebridge-p3s3-tf-locks`;
- SNS topic `changebridge-p3s3-alerts` and one redacted verified email subscription;
- IAM role `ChangeBridgePart3GitHubActionsRole` with ChangeBridge-repository OIDC trust.

Creation must be collision-safe, tagged, receipt-producing, non-destructive, and idempotent.
Existing objects must not be adopted merely because their names match. Any collision, unexpected
owner, policy, encryption state, permission boundary, service unavailability, or quota deficit
blocks mutation and requires a design correction or separate authorization.
