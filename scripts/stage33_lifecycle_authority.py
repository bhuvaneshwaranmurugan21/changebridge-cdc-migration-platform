"""Approved preparation scope and exact lifecycle policies; no AWS creation authority."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import timedelta
from pathlib import Path
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
from scripts.stage33_execution_bindings import ExecutionBindings, utc
from scripts.validate_part3_stage3 import ROOT

EVIDENCE = f"changebridge-p3s3-evidence-{ACCOUNT}-{REGION}"
FUNCTION = "changebridge-p3s3-lifecycle"
LIFECYCLE_ROLE = "ChangeBridgePart3LifecycleRole"
SCHEDULER_ROLE = "ChangeBridgePart3SchedulerRole"
QUEUE = "changebridge-p3s3-lifecycle-failures"
APPROVED_PROPOSAL_SHA256 = "435ccaae8997e1acde98ea8c6bf0f2008d1296c3a7cd08e0a134b2a226fd55c7"
APPROVAL_TEXT_SHA256 = "754c7b5dc4094ca196c0cdf05a30cf5c3649d541aa370e1b19b6256bb195fcf9"
FUNCTION_ARN = f"arn:aws:lambda:{REGION}:{ACCOUNT}:function:{FUNCTION}"
QUEUE_ARN = f"arn:aws:sqs:{REGION}:{ACCOUNT}:{QUEUE}"
GROUP_ARN = f"arn:aws:scheduler:{REGION}:{ACCOUNT}:schedule-group/default"
LOG_ARN = f"arn:aws:logs:{REGION}:{ACCOUNT}:log-group:/aws/lambda/{FUNCTION}:*"


class LifecycleAuthorityError(ValueError):
    """Preparation approval cannot be substituted for an execution gate."""


def approval(root: Path | None = None) -> dict[str, Any]:
    root = ROOT if root is None else root
    raw = (root / "deployment/stage3/lifecycle-scope-correction.proposed.json").read_bytes()
    proposal = json.loads(raw)
    authority: dict[str, Any] = json.loads(
        (root / "deployment/stage3/lifecycle-authority.json").read_bytes()
    )
    if (
        set(authority) != {
            "account_id", "approval_received_at_utc", "approval_text", "approval_text_sha256",
            "approved_preparation", "approved_resources", "aws_resource_creation_authorized",
            "controller_retention_maximum_days", "cost_limit_accepted", "label",
            "original_operational_deadline_hours", "pending_execution_gates",
            "predecessor_acceptance_weakened", "proposal_sha256", "proposal_source_commit",
            "region", "repository", "runtime_dependencies_qualified", "schema_version",
        }
        or authority["schema_version"] != "1.0.0"
        or authority["label"] != "APPROVED_LIFECYCLE_PREPARATION_NOT_AWS_CREATION_AUTHORITY"
        or authority["approval_received_at_utc"] != "2026-10-07T06:32:20Z"
        or authority["pending_execution_gates"] != [
            "exact policies qualified", "cost bound accepted and verified",
            "runtime matrix qualified",
            "authenticated administrator channel",
            "fresh identity, collisions, usage and control qualification",
            "independent scheduled execution, external evidence retention and cleanup verification",
        ]
        or authority["proposal_sha256"] != APPROVED_PROPOSAL_SHA256
        or hashlib.sha256(raw).hexdigest() != APPROVED_PROPOSAL_SHA256
        or authority["approval_text_sha256"] != APPROVAL_TEXT_SHA256
        or authority["proposal_source_commit"] != "c99ac491e5764bac81b413e494c83bc5e616cca6"
        or authority["cost_limit_accepted"] is not False
        or authority["runtime_dependencies_qualified"] is not False
        or authority["approved_resources"] != proposal["proposed_additional_resources"]
        or len(authority["approved_resources"]) != 7
        or authority["approval_text_sha256"]
        != hashlib.sha256(authority["approval_text"].encode()).hexdigest()
        or authority["account_id"] != ACCOUNT
        or authority["region"] != REGION
        or authority["repository"] != "bhuvaneshwaranmurugan21/changebridge-cdc-migration-platform"
        or authority["approved_preparation"] is not True
        or authority["aws_resource_creation_authorized"] is not False
        or authority["controller_retention_maximum_days"] != 10
        or authority["original_operational_deadline_hours"] != 48
        or authority["predecessor_acceptance_weakened"] is not False
    ):
        raise LifecycleAuthorityError("lifecycle scope, approval or preserved deadline changed")
    return authority


def prefix(execution_id: str) -> str:
    if not re.fullmatch(r"[a-z0-9-]{8,64}", execution_id):
        raise LifecycleAuthorityError("exact execution prefix required")
    return f"executions/{execution_id}/"


def policy(statements: list[dict[str, Any]]) -> dict[str, Any]:
    return {"Version": "2012-10-17", "Statement": statements}


def allow(sid: str, actions: list[str], resources: list[str], **fields: Any) -> dict[str, Any]:
    return {"Sid": sid, "Effect": "Allow", "Action": actions, "Resource": resources, **fields}


def policies(bindings: ExecutionBindings) -> dict[str, Any]:
    """Prepare exact scoped documents, retaining unproven effectiveness and creation guards.

    The initial lifecycle role has only evidence IO/logging. Physical-key cleanup privileges
    are a separate binding phase, never wildcard KMS administration before CreateKey returns.
    The seven-resource approval does not approve these policies for attachment/use.
    """
    approved = approval()
    bindings.validate()
    root = prefix(bindings.execution_id)
    bucket = f"arn:aws:s3:::{EVIDENCE}"
    evidence = policy(
        [
            allow(
                "ReadFrozenAuthority",
                ["s3:GetObject", "s3:GetObjectVersion"],
                [bucket + "/" + root + "authority/*"],
            ),
            allow(
                "ReadOwnJournalAndExports",
                ["s3:GetObject", "s3:GetObjectVersion"],
                [
                    bucket + "/" + root + "events/*",
                    bucket + "/" + root + "exports/*",
                    bucket + "/" + root + "head.json",
                ],
            ),
            allow(
                "WriteOwnJournalAndExports",
                ["s3:PutObject"],
                [
                    bucket + "/" + root + "events/*",
                    bucket + "/" + root + "exports/*",
                    bucket + "/" + root + "head.json",
                ],
                Condition={"StringEquals": {"s3:x-amz-server-side-encryption": "AES256"}},
            ),
            allow(
                "ListOwnEvidenceOnly",
                ["s3:ListBucket", "s3:ListBucketVersions"],
                [bucket],
                Condition={"StringLike": {"s3:prefix": [root, root + "*"]}},
            ),
            allow(
                "WriteOwnPrecreatedLogStreams",
                ["logs:CreateLogStream", "logs:PutLogEvents"],
                [LOG_ARN],
            ),
        ]
    )
    evidence["Statement"].append(
        {
            "Sid": "NeverEraseOwnAuthorityOrJournal",
            "Effect": "Deny",
            "Action": ["s3:DeleteObject", "s3:DeleteObjectVersion"],
            "Resource": [bucket + "/" + root + "*"],
        }
    )
    scheduler = policy(
        [
            allow("InvokeOnlyLifecycleFunction", ["lambda:InvokeFunction"], [FUNCTION_ARN]),
            allow("SendOnlyLifecycleDeliveryFailures", ["sqs:SendMessage"], [QUEUE_ARN]),
        ]
    )
    trust = policy(
        [
            {
                "Effect": "Allow",
                "Principal": {"Service": "scheduler.amazonaws.com"},
                "Action": "sts:AssumeRole",
                "Condition": {
                    "StringEquals": {"aws:SourceAccount": ACCOUNT, "aws:SourceArn": GROUP_ARN}
                },
            }
        ]
    )
    transport = policy(
        [
            {
                "Sid": "DenyPlaintextTransport",
                "Effect": "Deny",
                "Principal": "*",
                "Action": "s3:*",
                "Resource": [bucket, bucket + "/*"],
                "Condition": {"Bool": {"aws:SecureTransport": "false"}},
            },
            {
                "Sid": "DenyUnencryptedWrites",
                "Effect": "Deny",
                "Principal": "*",
                "Action": "s3:PutObject",
                "Resource": [bucket + "/*"],
                "Condition": {"StringNotEquals": {"s3:x-amz-server-side-encryption": "AES256"}},
            },
            {
                "Sid": "DenyImmutableRecordOverwrite",
                "Effect": "Deny",
                "Principal": "*",
                "Action": "s3:PutObject",
                "Resource": [
                    bucket + "/" + root + "events/*",
                    bucket + "/" + root + "exports/*",
                    bucket + "/" + root + "authority/*",
                ],
                "Condition": {"Null": {"s3:if-none-match": "true"}},
            },
            {
                "Sid": "DenyHeadWithoutConditionalWrite",
                "Effect": "Deny",
                "Principal": "*",
                "Action": "s3:PutObject",
                "Resource": [bucket + "/" + root + "head.json"],
                "Condition": {"Null": {"s3:if-none-match": "true", "s3:if-match": "true"}},
            },
        ]
    )
    cleanup: dict[str, Any] | None = None
    if bindings.key_arn is not None:
        key = bindings.key_arn
        cleanup = policy(
            evidence["Statement"]
            + [
                allow(
                    "ObserveAndRetireExactKey",
                    [
                        "kms:DescribeKey",
                        "kms:GetKeyPolicy",
                        "kms:ListResourceTags",
                        "kms:ScheduleKeyDeletion",
                        "kms:DeleteAlias",
                    ],
                    [key],
                ),
                allow(
                    "RemoveExactAlias",
                    ["kms:DeleteAlias"],
                    [f"arn:aws:kms:{REGION}:{ACCOUNT}:alias/changebridge-p3s3-state"],
                ),
                allow(
                    "InspectAndRetireOwnBackendRole",
                    [
                        "iam:GetRole",
                        "iam:ListRolePolicies",
                        "iam:GetRolePolicy",
                        "iam:ListAttachedRolePolicies",
                        "iam:ListInstanceProfilesForRole",
                        "iam:UpdateAssumeRolePolicy",
                        "iam:DeleteRolePolicy",
                        "iam:DeleteRole",
                    ],
                    [f"arn:aws:iam::{ACCOUNT}:role/{ROLE}"],
                ),
                allow(
                    "InspectAndRetireOwnLocks",
                    [
                        "dynamodb:DescribeTable",
                        "dynamodb:DescribeContinuousBackups",
                        "dynamodb:ListTagsOfResource",
                        "dynamodb:Scan",
                        "dynamodb:UpdateContinuousBackups",
                        "dynamodb:DeleteTable",
                    ],
                    [f"arn:aws:dynamodb:{REGION}:{ACCOUNT}:table/{LOCKS}"],
                ),
                allow(
                    "InspectAndRetireOwnAlertTopic",
                    [
                        "sns:GetTopicAttributes",
                        "sns:ListTagsForResource",
                        "sns:ListSubscriptionsByTopic",
                        "sns:DeleteTopic",
                        "sns:GetSubscriptionAttributes",
                        "sns:Unsubscribe",
                    ],
                    [TOPIC],
                ),
                # SNS authorizes subscription reads/removal against the exact topic ARN.
                # The request still requires the actual original subscription/owner receipt.
                allow(
                    "InspectAndRetireOwnBuckets",
                    [
                        "s3:GetBucketLocation",
                        "s3:GetBucketTagging",
                        "s3:GetBucketVersioning",
                        "s3:GetEncryptionConfiguration",
                        "s3:GetBucketPublicAccessBlock",
                        "s3:GetBucketOwnershipControls",
                        "s3:GetBucketPolicy",
                        "s3:ListBucketVersions",
                        "s3:ListBucketMultipartUploads",
                        "s3:DeleteBucket",
                    ],
                    [f"arn:aws:s3:::{STATE}", f"arn:aws:s3:::{ARTIFACT}"],
                ),
                allow(
                    "ExportAndRemoveExactAllowedVersions",
                    ["s3:GetObjectVersion", "s3:DeleteObjectVersion"],
                    [
                        f"arn:aws:s3:::{STATE}/changebridge/part3/stage3/terraform.tfstate",
                        f"arn:aws:s3:::{ARTIFACT}/changebridge/part3/stage3/immutable/*",
                    ],
                ),
                allow(
                    "DecryptExactLockTableForQuiescence",
                    ["kms:Decrypt"],
                    [key],
                    Condition={
                        "StringEquals": {
                            "kms:ViaService": f"dynamodb.{REGION}.amazonaws.com",
                            "kms:CallerAccount": ACCOUNT,
                            "kms:EncryptionContext:aws:dynamodb:tableName": LOCKS,
                            "kms:EncryptionContext:aws:dynamodb:subscriberId": ACCOUNT,
                        }
                    },
                ),
                allow(
                    "DecryptExactKeyForOwnedExports",
                    ["kms:Decrypt"],
                    [key],
                    Condition={
                        "StringEquals": {
                            "kms:ViaService": f"s3.{REGION}.amazonaws.com",
                            "kms:CallerAccount": ACCOUNT,
                        },
                        "StringLike": {
                            "kms:EncryptionContext:aws:s3:arn": [
                                f"arn:aws:s3:::{STATE}/changebridge/part3/stage3/terraform.tfstate",
                                f"arn:aws:s3:::{ARTIFACT}/changebridge/part3/stage3/immutable/*",
                            ]
                        },
                    },
                ),
            ]
        )
    result = {
        "label": "EXACT_LIFECYCLE_POLICY_CONSTRUCTION_NOT_ATTACHMENT_AUTHORITY",
        "execution_enabled": False,
        "policy_effectiveness_proven": False,
        "authority_sha256": digest(approved),
        "execution_id": bindings.execution_id,
        "initial_lifecycle_permissions": evidence,
        "lifecycle_trust": policy(
            [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "lambda.amazonaws.com"},
                    "Action": "sts:AssumeRole",
                }
            ]
        ),
        "scheduler_trust": trust,
        "scheduler_permissions": scheduler,
        "evidence_bucket_policy": transport,
        "physical_key_bound_cleanup_permissions": cleanup,
        "remaining_binding_gates": [
            "actual subscription ARN/owner and effective topic-scoped permission",
            "backup residual qualification",
            "recoverable first-key unknown outcome",
            "complete IAM effectiveness and ownership/cleanup qualification",
        ],
    }
    frozen: dict[str, Any] = json.loads(canonical(result))
    return frozen


def schedule(bindings: ExecutionBindings, first_creation_utc: str) -> dict[str, Any]:
    approval()
    bindings.validate()
    first = utc(first_creation_utc)
    if (
        first < utc(bindings.prepared_at_utc)
        or not 0 < (utc(bindings.expires_at_utc) - first).total_seconds() <= 48 * 3600
    ):
        raise LifecycleAuthorityError("original creation-bound 48-hour deadline required")
    expiry = first + timedelta(days=10)
    return {
        "Name": FUNCTION,
        "GroupName": "default",
        "ScheduleExpression": "rate(15 minutes)",
        "ScheduleExpressionTimezone": "UTC",
        "FlexibleTimeWindow": {"Mode": "OFF"},
        "StartDate": first.isoformat(),
        "EndDate": expiry.isoformat(),
        "State": "ENABLED",
        "Target": {
            "Arn": FUNCTION_ARN,
            "RoleArn": f"arn:aws:iam::{ACCOUNT}:role/{SCHEDULER_ROLE}",
            "RetryPolicy": {"MaximumEventAgeInSeconds": 900, "MaximumRetryAttempts": 2},
            "DeadLetterConfig": {"Arn": QUEUE_ARN},
            "Input": json.dumps(
                {
                    "execution_id": bindings.execution_id,
                    "schedule_arn": (
                        f"arn:aws:scheduler:{REGION}:{ACCOUNT}:schedule/default/{FUNCTION}"
                    ),
                    "delivery_id": "<aws.scheduler.execution-id>",
                },
                sort_keys=True,
            ),
        },
        "ClientToken": bindings.execution_id,
    }
