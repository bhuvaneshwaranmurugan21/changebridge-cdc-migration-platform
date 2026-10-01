# Stage 3 AWS admission handoff

Stage 3 may begin only from `PART3_STAGE2_DEPLOYABLE_PLATFORM_VERIFIED`. Before any mutation it
must bind and independently verify the exact AWS account, region, budget ceiling, billing alarms,
OIDC trust, execution role, backend coordinates, quotas, supported services, network prerequisites,
artifact bucket, and lifecycle deadline. It must obtain separate stage-specific authorization.

Stage 2 supplies deployable structure and static proof only. It supplies no AWS receipt and no
managed-service claim.
