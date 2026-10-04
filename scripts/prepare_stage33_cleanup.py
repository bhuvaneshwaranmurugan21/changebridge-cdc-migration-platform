"""Compile non-executable cleanup selectors; actual ownership/export/authority remains mandatory."""

from __future__ import annotations

import json
import re
from typing import Any

from scripts.prepare_stage33_bootstrap import (
    ACCOUNT,
    ARTIFACT,
    LOCKS,
    REGION,
    ROLE,
    STATE,
    TOPIC,
    canonical,
    digest,
)

UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
ALIAS = "alias/changebridge-p3s3-state"
RESOURCE_KEYS = {"state_key", "state_alias", "state_bucket", "artifact_bucket",
                 "state_locks", "alerts", "alert_email", "github_actions_role"}


class CleanupPlanError(ValueError):
    """Unsafe or incomplete selectors cannot be used for cleanup."""


def cleanup_plan(inventory: dict[str, Any]) -> dict[str, Any]:
    """Pin known identities and versions, without inventing observations or deletion authority."""
    if set(inventory) != {"account_id", "region", "execution_id", "resources"}:
        raise CleanupPlanError("exact inventory fields required")
    if inventory["account_id"] != ACCOUNT or inventory["region"] != REGION:
        raise CleanupPlanError("inventory outside ChangeBridge binding")
    execution_id = inventory["execution_id"]
    if not isinstance(execution_id, str) or not re.fullmatch(r"[a-z0-9-]{8,64}", execution_id):
        raise CleanupPlanError("invalid execution identity")
    resources = inventory["resources"]
    if (
        not isinstance(resources, dict) or not resources or set(resources) - RESOURCE_KEYS
        or any(not isinstance(record, dict) for record in resources.values())
    ):
        raise CleanupPlanError("unknown or empty resource inventory")
    steps: list[dict[str, Any]] = []

    def add(
        resource: str, service: str, operation: str, request: dict[str, Any],
        identity: dict[str, Any], guards: list[str],
    ) -> None:
        steps.append({
            "id": f"cleanup-{len(steps) + 1:02d}", "resource": resource,
            "service": service, "operation": operation, "request": request,
            "expected_identity": identity, "expected_execution_id": execution_id,
            "depends_on": [steps[-1]["id"]] if steps else [],
            "mandatory_actual_guards": guards,
            "unknown_acknowledgement": "AUTHORITATIVE_READBACK_BEFORE_ANY_RETRY",
        })

    role = resources.get("github_actions_role")
    if role is not None:
        if (
            set(role) != {"arn", "role_id", "inline_policy_name"}
            or role["arn"] != f"arn:aws:iam::{ACCOUNT}:role/{ROLE}"
            or not re.fullmatch(r"AROA[A-Z0-9]{17}", str(role["role_id"]))
            or role["inline_policy_name"] != "ChangeBridgeStage33Backend"
        ):
            raise CleanupPlanError("unknown role identity or policy")
        deny_trust = {"Version": "2012-10-17", "Statement": [{
            "Effect": "Deny", "Principal": {"Federated":
                f"arn:aws:iam::{ACCOUNT}:oidc-provider/token.actions.githubusercontent.com"},
            "Action": "sts:AssumeRoleWithWebIdentity",
        }]}
        add("github_actions_role", "iam", "update-assume-role-policy", {
            "RoleName": ROLE, "PolicyDocument": json.dumps(deny_trust),
        }, role, ["exact RoleId/trust/policies/tags before write", "all proof jobs completed"])
        add("github_actions_role", "iam", "delete-role-policy", {
            "RoleName": ROLE, "PolicyName": role["inline_policy_name"],
        }, role, ["revoke backend permission before final lock/version observation",
                  "exact inline policy digest matches reviewed backend policy"])
    subscription = resources.get("alert_email")
    if subscription is not None:
        if (
            set(subscription) != {"subscription_arn"}
            or not re.fullmatch(re.escape(TOPIC) + ":" + UUID,
                                str(subscription["subscription_arn"]))
        ):
            raise CleanupPlanError("unknown or pending subscription identity")
        add("alert_email", "sns", "unsubscribe", {
            "SubscriptionArn": subscription["subscription_arn"],
        }, subscription, ["actual exact topic/owner/endpoint binding", "preserved alert proof"])
    topic = resources.get("alerts")
    if topic is not None:
        if topic != {"arn": TOPIC}:
            raise CleanupPlanError("unknown topic identity")
        add("alerts", "sns", "delete-topic", {"TopicArn": TOPIC}, topic,
            ["exact ownership/tags", "subscriptions inventoried and removed"])
    table = resources.get("state_locks")
    if table is not None:
        if (
            set(table) != {"arn", "table_id"}
            or table["arn"] != f"arn:aws:dynamodb:{REGION}:{ACCOUNT}:table/{LOCKS}"
            or not re.fullmatch(UUID, str(table["table_id"]))
        ):
            raise CleanupPlanError("unknown lock table identity")
        add("state_locks", "dynamodb", "delete-table", {"TableName": LOCKS}, table,
            ["exact TableId/ownership", "consistent complete scan proves no active locks",
             "final state exported and independently verified"])
    for logical, bucket, prefix in (
        ("state_bucket", STATE, "changebridge/part3/stage3/terraform.tfstate"),
        ("artifact_bucket", ARTIFACT, "changebridge/part3/stage3/immutable/"),
    ):
        record = resources.get(logical)
        if record is None:
            continue
        if (
            set(record) != {"name", "creation_date", "versions"}
            or record["name"] != bucket or not isinstance(record["creation_date"], str)
            or not record["creation_date"] or not isinstance(record["versions"], list)
        ):
            raise CleanupPlanError("unknown bucket identity or version inventory")
        selected = []
        seen = set()
        for version in record["versions"]:
            if (
                not isinstance(version, dict) or set(version) != {"Key", "VersionId"}
                or not isinstance(version["Key"], str)
                or not isinstance(version["VersionId"], str) or not version["VersionId"]
                or version["VersionId"] == "null"
                or (logical == "state_bucket" and version["Key"] != prefix)
                or (logical == "artifact_bucket" and not version["Key"].startswith(prefix))
                or (version["Key"], version["VersionId"]) in seen
            ):
                raise CleanupPlanError("unknown, duplicate or out-of-prefix object version")
            seen.add((version["Key"], version["VersionId"]))
            selected.append(version)
        # One object/version per request makes partial acknowledgements individually reconcilable.
        for version in sorted(selected, key=lambda row: (row["Key"], row["VersionId"])):
            add(logical, "s3api", "delete-object", {
                "Bucket": bucket, "ExpectedBucketOwner": ACCOUNT, **version,
            }, {"name": bucket, "creation_date": record["creation_date"], **version},
                ["fresh owner, execution tags and observed bucket metadata",
                 "complete version/delete-marker inventory matches frozen selected set",
                 "verified durable export readable without the Stage 3 KMS key"])
        add(logical, "s3api", "delete-bucket", {
            "Bucket": bucket, "ExpectedBucketOwner": ACCOUNT,
        }, {"name": bucket, "creation_date": record["creation_date"]},
            ["fresh complete listing proves no versions or delete markers remain",
             "unknown object blocks deletion", "required evidence independently preserved"])
    alias = resources.get("state_alias")
    key = resources.get("state_key")
    if key is not None and (
        set(key) != {"arn", "key_id"}
        or not re.fullmatch(UUID, str(key["key_id"]))
        or key["arn"] != f"arn:aws:kms:{REGION}:{ACCOUNT}:key/{key['key_id']}"
    ):
        raise CleanupPlanError("unknown KMS key identity; never infer a lost creation")
    if alias is not None:
        if key is None or alias != {"name": ALIAS, "target_key_id": key["key_id"]}:
            raise CleanupPlanError("alias target is not the exact inventoried key")
        add("state_alias", "kms", "delete-alias", {"AliasName": ALIAS}, alias,
            ["fresh alias target and exact key identity agree"])
    if key is not None:
        add("state_key", "kms", "schedule-key-deletion", {
            "KeyId": key["arn"], "PendingWindowInDays": 7,
        }, key, ["exact key identity and ownership", "all dependent resources removed",
                 "exports verified readable without this key",
                 "actual PendingDeletion/deletion-date readback; later physical deletion check"])
    if role is not None:
        add("github_actions_role", "iam", "delete-role", {"RoleName": ROLE}, role,
            ["exact RoleId", "no inline/attached policies, boundary or instance profiles",
             "administrator executor is separate from the deleted role"])
    payload = {
        "label": "OFFLINE_CLEANUP_SELECTORS_NOT_DELETION_AUTHORITY",
        "execution_enabled": False, "execution_id": execution_id,
        "inventory_sha256": digest(inventory), "steps": steps,
        "blocking_requirements": [
            "qualified live administrator executor and concrete cleanup authority",
            "fresh ownership/identity/version/lock readbacks before each mutation",
            "durable evidence export independent of the deleted key",
            "48-hour enforcement and actual final absence/pending-deletion proof",
        ],
        "limitations": [
            "named mutations do not provide server-side CAS for every ownership field",
            "S3 creation-date metadata is not an immutable bucket identifier",
            "partial inventories do not establish absence of omitted resources",
            "planned guards are not implemented execution or observations",
            "subscription PendingConfirmation cannot be treated as a confirmed ARN",
            "KMS scheduled deletion is not physical deletion",
        ],
    }
    # Freeze model inputs: callers cannot later mutate returned selector references by aliasing.
    frozen: dict[str, Any] = json.loads(canonical(payload))
    return {**frozen, "plan_sha256": digest(frozen)}
