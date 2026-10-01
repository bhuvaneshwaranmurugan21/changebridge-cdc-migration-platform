# Part 3 Stage 2 deployable platform

Stage 2 turns the accepted local ChangeBridge semantics into a deployable AWS definition without
contacting AWS. It does not deploy or validate managed behavior. Account, region, deployment
identity, artifact location, cost owner, and expiry remain `UNASSIGNED`; the Terraform admission
guard therefore blocks resource creation.

The platform defines encrypted landing, evidence, and Iceberg warehouse storage; Glue catalog;
DMS transaction-preserving landing; generation, checkpoint, publication-revision, and active
pointer ledgers; five checksum-bound Glue job roles; proof-gated Step Functions orchestration; and
bounded alarms. Runtime processing cannot mutate the active pointer. Publication receives a
separate policy and must follow the Part 2 expected-revision protocol.

The infrastructure consumes Part 2 contracts. It does not redefine generation identity, source
frontiers, event ordering, checkpoint finalization, schema admission, reconciliation gates, or
publication CAS. Terraform structure is not evidence of AWS acceptance, runtime correctness,
cross-table atomicity, production exactly-once delivery, scale, or cost.

## Fail-closed inputs

Deployment requires all of the following to be assigned by Stage 3: expected account, region,
deployment ID, immutable artifact location and digest, cost center, expiry, remote-state
coordinates, execution identity, and OIDC binding. There is no usable account or region default.

## Lifecycle

The orchestration admits snapshot load, CDC apply, schema admission, reconciliation proof and
publication. The proof choice defaults to rejection and reaches publication only for `PROVEN`.
Retries are bounded. Managed recovery and rollback proof remain later-stage obligations.
