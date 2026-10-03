# Part 3 Stage 3 AWS admission

Stage 3 binds the deployable ChangeBridge definition to one observed AWS boundary without
representing observation as deployment. The accepted boundary is account `857229544428` in
`ap-southeast-2`. The operator verified an alert endpoint, but the address is deliberately absent
from this public repository.

The existing `portfolio-labs-monthly-cost` budget is a shared monthly USD 20 guardrail with actual
50%, actual 80%, and forecasted 100% email notifications. The approximately USD 140 portfolio
credit context is not a ChangeBridge allowance. Stage 3 resources have a maximum 48-hour lifetime.
The USD 3 bootstrap allowance is proposed only; it has not been accepted. Budget notifications are
alerts, not enforcement of a hard spending cap. Retain-through-Part-3 language in the bootstrap
proposal conflicts with the lifetime bound and remains a blocking design correction, including
the AWS KMS deletion waiting period. Expiry tags alone do not perform teardown.

## Authority boundary

The current authorization permits read-only qualification and repository preparation. It does not
permit creating, changing, or deleting an AWS resource. The bootstrap manifest is therefore a
proposal, not an execution receipt. Exact-resource authorization is a non-substitutable gate.

The bootstrap is restricted to encrypted remote state and runtime artifact storage, state locking,
alert routing, and a
repository-bound GitHub OIDC role. It excludes the ChangeBridge DMS, Glue, S3 data plane,
DynamoDB migration control plane, Step Functions workflow, and all managed workloads.

`AWS_ADMISSION_OBSERVED` means that account, region, budget, alerting, and the proposed boundary
are reviewable. It does not mean AWS bootstrap, deployability, managed correctness, performance,
or production readiness has been proven.

## Received read-only evidence

`evidence/part3/stage3/aws-readonly-review.json` binds both received archive digests and records
their verified internal checksums. It supports observed name absence and regional API availability.
The candidate role is absent: operator-role observations cannot prove candidate-role permissions,
boundaries, or exact trust. Quota values are not complete usage/headroom evidence. The observed
default VPC, subnets, availability zones and route do not prove a managed workload can deploy.
Neither archive records capture time; repeat timestamped qualification immediately before any
separately authorized write. All existing acceptance requirements remain unchanged.
