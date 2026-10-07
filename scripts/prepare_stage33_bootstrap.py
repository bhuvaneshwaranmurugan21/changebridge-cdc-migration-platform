#!/usr/bin/env python3
"""Compile the bounded bootstrap request package; never invoke AWS or authorize writes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from scripts.validate_part3_stage3 import ROOT, validate_proposed_policies

ACCOUNT = "857229544428"
REGION = "ap-southeast-2"
KEY = "__VERIFIED_NEW_KMS_KEY_ARN__"
EMAIL = "__PRIVATE_APPROVED_ALERT_EMAIL__"
ROLE = "ChangeBridgePart3GitHubActionsRole"
STATE = f"changebridge-p3s3-tfstate-{ACCOUNT}-{REGION}"
ARTIFACT = f"changebridge-p3s3-artifacts-{ACCOUNT}-{REGION}"
LOCKS = "changebridge-p3s3-tf-locks"
TOPIC = f"arn:aws:sns:{REGION}:{ACCOUNT}:changebridge-p3s3-alerts"
EXPIRY = "__FIRST_CREATION_PLUS_AT_MOST_48_HOURS_UTC__"
EXECUTION_ID = "__BOOTSTRAP_EXECUTION_ID__"
SOURCES = (
    "deployment/stage3/bootstrap-manifest.json",
    "deployment/stage3/oidc-trust-policy.proposed.json",
    "deployment/stage3/role-permissions.proposed.json",
    "deployment/stage3/teardown-plan.json",
    "docs/part3/stage3/ADMINISTRATOR_BOOTSTRAP_EXECUTION.md",
    "scripts/prepare_stage33_bootstrap.py",
    "scripts/stage33_bootstrap_journal.py",
    "scripts/stage33_mutation_journal.py",
    "scripts/verify_stage33_role_controls.py",
    "scripts/verify_stage33_key_controls.py",
    "scripts/verify_stage33_storage_controls.py",
    "scripts/verify_stage33_lock_controls.py",
    "scripts/reconcile_stage33_key_attempt.py",
    "scripts/export_stage33_evidence.py",
    "scripts/prepare_stage33_cleanup.py",
    "scripts/qualify_stage33_bootstrap.py",
    "scripts/collect_stage33_access_diagnostic.sh",
    "scripts/validate_stage33_access_evidence.py",
    "evidence/part3/stage3/administrator-access-diagnostic.json",
)


def canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def compile_package() -> dict[str, Any]:
    """Freeze reviewed scope into requests, dependencies and required real readbacks."""
    source_bytes = {name: (ROOT / name).read_bytes() for name in SOURCES}
    validate_proposed_policies()
    manifest = json.loads(source_bytes[SOURCES[0]])
    expected = {
        "state-key": ("AWS::KMS::Key", "provider-assigned"),
        "state-key-alias": ("AWS::KMS::Alias", "alias/changebridge-p3s3-state"),
        "state-bucket": ("AWS::S3::Bucket", STATE),
        "artifact-bucket": ("AWS::S3::Bucket", ARTIFACT),
        "state-locks": ("AWS::DynamoDB::Table", LOCKS),
        "alerts": ("AWS::SNS::Topic", "changebridge-p3s3-alerts"),
        "alert-email": ("AWS::SNS::Subscription", "VERIFIED_REDACTED"),
        "github-actions-role": ("AWS::IAM::Role", ROLE),
    }
    rows = manifest["resources"]
    actual = {r["logical_name"]: (r["type"], r["physical_name"]) for r in rows}
    if (
        len(rows) != 8 or actual != expected or manifest["account_id"] != ACCOUNT
        or manifest["region"] != REGION or manifest["maximum_lifetime_hours"] != 48
        or manifest["manifest_status"] != "PROPOSED_NOT_AUTHORIZED"
        or manifest["schema_version"] != "1.0.0"
    ):
        raise ValueError("bootstrap authority or eight-resource allowlist drift")
    tags = [
        {"Key": "Project", "Value": "ChangeBridge"},
        {"Key": "Owner", "Value": "bhuvaneshwaranmurugan21"},
        {"Key": "Stage", "Value": "part3-stage3"},
        {"Key": "CostCenter", "Value": "changebridge-p3s3"},
        {"Key": "ExpiresAt", "Value": EXPIRY},
        {"Key": "ExecutionId", "Value": EXECUTION_ID},
    ]
    steps: list[dict[str, Any]] = []

    def add(resource: str, service: str, operation: str, request: dict[str, Any]) -> None:
        previous = steps[-1]["id"] if steps else None
        steps.append({
            "id": f"bootstrap-{len(steps) + 1:02d}", "resource": resource,
            "service": service, "operation": operation, "request": request,
            "depends_on": [previous] if previous else [],
            "acknowledgement_is_not_configuration_proof": True,
            "on_unknown_outcome": "STOP_AND_AUTHORITATIVELY_RECONCILE_NO_BLIND_RETRY",
        })

    key_policy = {"Version": "2012-10-17", "Statement": [{
        "Sid": "AccountKeyAdministration", "Effect": "Allow",
        "Principal": {"AWS": f"arn:aws:iam::{ACCOUNT}:root"},
        "Action": "kms:*", "Resource": "*",
    }]}
    # KMS Resource * denotes this key in its own key policy, not a role-wide permission.
    add("state-key", "kms", "create-key", {
        "Description": "ChangeBridge Part 3 Stage 3 state encryption",
        "KeyUsage": "ENCRYPT_DECRYPT", "KeySpec": "SYMMETRIC_DEFAULT",
        "MultiRegion": False, "Policy": json.dumps(key_policy),
        "Tags": [{"TagKey": t["Key"], "TagValue": t["Value"]} for t in tags],
    })
    add("state-key-alias", "kms", "create-alias", {
        "AliasName": "alias/changebridge-p3s3-state", "TargetKeyId": KEY,
    })
    for logical, bucket in (("state-bucket", STATE), ("artifact-bucket", ARTIFACT)):
        base = {"Bucket": bucket, "ExpectedBucketOwner": ACCOUNT}
        add(logical, "s3api", "create-bucket", {
            "Bucket": bucket, "CreateBucketConfiguration": {"LocationConstraint": REGION},
            "ObjectOwnership": "BucketOwnerEnforced",
        })
        add(logical, "s3api", "put-public-access-block", {
            **base, "PublicAccessBlockConfiguration": {
                "BlockPublicAcls": True, "IgnorePublicAcls": True,
                "BlockPublicPolicy": True, "RestrictPublicBuckets": True,
            },
        })
        add(logical, "s3api", "put-bucket-versioning", {
            **base, "VersioningConfiguration": {"Status": "Enabled"},
        })
        add(logical, "s3api", "put-bucket-encryption", {
            **base, "ServerSideEncryptionConfiguration": {"Rules": [{
                "ApplyServerSideEncryptionByDefault": {
                    "SSEAlgorithm": "aws:kms", "KMSMasterKeyID": KEY,
                }, "BucketKeyEnabled": False,
            }]},
        })
        policy = {"Version": "2012-10-17", "Statement": [{
            "Sid": "DenyInsecureTransport", "Effect": "Deny", "Principal": "*",
            "Action": "s3:*", "Resource": [f"arn:aws:s3:::{bucket}",
                                           f"arn:aws:s3:::{bucket}/*"],
            "Condition": {"Bool": {"aws:SecureTransport": "false"}},
        }]}
        add(logical, "s3api", "put-bucket-policy", {**base, "Policy": json.dumps(policy)})
        add(logical, "s3api", "put-bucket-tagging", {**base, "Tagging": {"TagSet": tags}})
    add("state-locks", "dynamodb", "create-table", {
        "TableName": LOCKS, "BillingMode": "PAY_PER_REQUEST",
        "AttributeDefinitions": [{"AttributeName": "LockID", "AttributeType": "S"}],
        "KeySchema": [{"AttributeName": "LockID", "KeyType": "HASH"}],
        "SSESpecification": {"Enabled": True, "SSEType": "KMS", "KMSMasterKeyId": KEY},
        "Tags": tags,
    })
    add("state-locks", "dynamodb", "update-continuous-backups", {
        "TableName": LOCKS, "PointInTimeRecoverySpecification": {
            "PointInTimeRecoveryEnabled": True,
        },
    })
    add("alerts", "sns", "create-topic", {"Name": "changebridge-p3s3-alerts", "Tags": tags})
    add("alert-email", "sns", "subscribe", {
        "TopicArn": TOPIC, "Protocol": "email", "Endpoint": EMAIL,
        "ReturnSubscriptionArn": True,
    })
    trust = json.loads(source_bytes[SOURCES[1]])["policy"]
    permissions = json.loads(source_bytes[SOURCES[2]])["policy"]
    kms_placeholder = "__BIND_EXACT_KMS_KEY_ARN_FROM_VERIFIED_BOOTSTRAP_RECEIPT__"
    bindings = [s for s in permissions["Statement"] if s["Resource"] == kms_placeholder]
    if len(bindings) != 2:
        raise ValueError("exact S3 and lock-table KMS bindings required")
    for statement in bindings:
        statement["Resource"] = KEY
    add("github-actions-role", "iam", "create-role", {
        "RoleName": ROLE, "AssumeRolePolicyDocument": json.dumps(trust),
        "MaxSessionDuration": 3600, "Tags": tags,
    })
    add("github-actions-role", "iam", "put-role-policy", {
        "RoleName": ROLE, "PolicyName": "ChangeBridgeStage33Backend",
        "PolicyDocument": json.dumps(permissions),
    })
    readbacks = {
        "state-key": ["describe-key", "get-key-policy", "list-resource-tags"],
        "state-key-alias": ["list-aliases filtered by verified key ID and exact alias"],
        "state-bucket": ["head-bucket", "get-bucket-location", "get-bucket-versioning",
                         "get-public-access-block", "get-bucket-ownership-controls",
                         "get-bucket-encryption", "get-bucket-policy", "get-bucket-tagging"],
        "artifact-bucket": ["same exact-owner storage controls as state-bucket",
                            "version-ID and checksum-bound artifact verification"],
        "state-locks": ["describe-table", "describe-continuous-backups", "list-tags-of-resource"],
        "alerts": ["get-topic-attributes", "list-tags-for-resource"],
        "alert-email": ["get-subscription-attributes with confirmed subscription ARN"],
        "github-actions-role": ["get-role", "list-role-policies", "get-role-policy",
                                "list-attached-role-policies", "actual exact-subject OIDC use"],
    }
    if any((ROOT / name).read_bytes() != value for name, value in source_bytes.items()):
        raise ValueError("source drift during package compilation")
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()
    tree = subprocess.run(
        ["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()
    payload = {
        "schema_version": "1.0.0", "label": "OFFLINE_REQUEST_PACKAGE_NOT_AWS_PROOF",
        "execution_enabled": False, "account_id": ACCOUNT, "region": REGION,
        "repository": "bhuvaneshwaranmurugan21/changebridge-cdc-migration-platform",
        "base_commit": commit, "base_tree": tree, "working_tree_dirty": bool(dirty),
        "source_sha256": {p: hashlib.sha256(source_bytes[p]).hexdigest() for p in SOURCES},
        "steps": steps, "required_actual_readbacks": readbacks,
        "unresolved_bindings": [KEY, EMAIL, EXPIRY, EXECUTION_ID],
        "blocking_conditions": [
            "authenticated administrator channel absent",
            "fresh collision, provider, identity and quota-usage qualification required",
            "USD 3 allowance acceptance and cost estimate required",
            "independent 48-hour enforcement and viable exact-bound cleanup executor unresolved",
            "durable evidence export independent of deleted KMS key required",
            "actual configuration, SNS confirmation and OIDC receipts absent",
        ],
        "not_implemented": [
            "mutation runner", "operation-specific authoritative mutation reconciliation",
            "collision ownership reconciliation", "cleanup executor",
        ],
    }
    return {**payload, "package_sha256": digest(payload)}


def write_package(output: Path) -> None:
    """Create a new private file, rejecting overwrite and symlinks atomically."""
    package = compile_package()
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(canonical(package))
        stream.flush()
        os.fsync(stream.fileno())


def verify_package(path: Path) -> None:
    """Reject tampered or stale requests against the current source and Git identity."""
    if json.loads(path.read_bytes()) != compile_package():
        raise ValueError("bootstrap package is tampered or stale; execution remains disabled")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--output", type=Path)
    mode.add_argument("--verify", type=Path)
    args = parser.parse_args()
    if args.verify is not None:
        verify_package(args.verify)
        print("OFFLINE_REQUEST_PACKAGE_VERIFIED: not AWS execution evidence")
    else:
        write_package(args.output)
        print("OFFLINE_REQUEST_PACKAGE_CREATED: execution disabled; no AWS operations")


if __name__ == "__main__":
    main()
