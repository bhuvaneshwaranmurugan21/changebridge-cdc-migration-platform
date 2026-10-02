#!/usr/bin/env python3
"""Fail-closed validator for the Part 3 Stage 3 admission packet."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
ENTRY = "084407a972d2d3f937e8ac670733f198dd4b0179"
ENTRY_TREE = "3a5ceefaf9dcfcbe97da5a593f76eab0cd5fe257"
PASSED_IDS = {f"ST33-AC-{number:02d}" for number in range(1, 31)} | {"ST33-AC-33", "ST33-AC-34"}


class Stage33Error(AssertionError):
    """Stable Stage 3 validation failure."""


def fail(code: str, detail: str) -> None:
    raise Stage33Error(f"{code}: {detail}")


def load(path: str) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((ROOT / path).read_text(encoding="utf-8")))


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()


def validate_proposed_policies() -> None:
    trust = load("deployment/stage3/oidc-trust-policy.proposed.json")
    permissions = load("deployment/stage3/role-permissions.proposed.json")
    for proposal in (trust, permissions):
        if (
            proposal["schema_version"] != "1.0.0"
            or proposal["status"] != "PROPOSED_NOT_AUTHORIZED"
            or proposal["execution_enabled"] is not False
            or proposal["role_name"] != "ChangeBridgePart3GitHubActionsRole"
        ):
            fail("ST33_POLICY_AUTHORITY", "policy proposal cannot authorize execution")
    expected_trust = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "ExactChangeBridgeStage3BranchOnly",
                "Effect": "Allow",
                "Principal": {
                    "Federated": (
                        "arn:aws:iam::857229544428:oidc-provider/token.actions.githubusercontent.com"
                    )
                },
                "Action": "sts:AssumeRoleWithWebIdentity",
                "Condition": {
                    "StringEquals": {
                        "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
                        "token.actions.githubusercontent.com:sub": (
                            "repo:bhuvaneshwaranmurugan21/changebridge-cdc-migration-platform:"
                            "ref:refs/heads/part3-stage3-aws-admission"
                        ),
                    }
                },
            }
        ],
    }
    if trust["policy"] != expected_trust or trust["actual_trust_readback_required"] is not True:
        fail("ST33_OIDC_POLICY", "exact provider, audience or Stage 3 branch trust drifted")
    placeholder = "__BIND_EXACT_KMS_KEY_ARN_FROM_VERIFIED_BOOTSTRAP_RECEIPT__"
    state_bucket = "arn:aws:s3:::changebridge-p3s3-tfstate-857229544428-ap-southeast-2"
    state_key = "changebridge/part3/stage3/terraform.tfstate"
    artifact_prefix = "changebridge/part3/stage3/immutable/"
    if (
        permissions["proposed_permissions_boundary"] != "NONE_NO_NEW_BOUNDARY_RESOURCE"
        or permissions["actual_policy_and_boundary_readback_required"] is not True
        or permissions["unresolved_bindings"]
        != ["EXACT_KMS_KEY_ARN_FROM_VERIFIED_BOOTSTRAP_RECEIPT"]
        or permissions["proposed_state_key"] != state_key
        or permissions["proposed_artifact_prefix"] != artifact_prefix
        or not permissions["binding_rule"]
    ):
        fail("ST33_PERMISSION_POLICY", "unresolved key or proposed boundary authority drifted")
    expected_statements = {
        "ExactBackendBucketLocation": ({"s3:GetBucketLocation"}, state_bucket, None),
        "ExactBackendStateListing": (
            {"s3:ListBucket"},
            state_bucket,
            {"StringEquals": {"s3:prefix": state_key}},
        ),
        "VersionedBackendStateOnly": (
            {"s3:GetObject", "s3:GetObjectVersion", "s3:PutObject"},
            f"{state_bucket}/{state_key}",
            None,
        ),
        "ImmutableArtifactReadOnly": (
            {"s3:GetObject", "s3:GetObjectVersion"},
            "arn:aws:s3:::changebridge-p3s3-artifacts-857229544428-ap-southeast-2/"
            f"{artifact_prefix}*",
            None,
        ),
        "ExactBackendLockTableOnly": (
            {
                "dynamodb:DescribeTable",
                "dynamodb:GetItem",
                "dynamodb:PutItem",
                "dynamodb:DeleteItem",
            },
            "arn:aws:dynamodb:ap-southeast-2:857229544428:table/changebridge-p3s3-tf-locks",
            None,
        ),
        "ExactVerifiedKeyViaRegionalS3Only": (
            {"kms:Decrypt", "kms:GenerateDataKey"},
            placeholder,
            {
                "StringEquals": {
                    "kms:CallerAccount": "857229544428",
                    "kms:ViaService": "s3.ap-southeast-2.amazonaws.com",
                }
            },
        ),
    }
    policy = permissions["policy"]
    statements = policy["Statement"]
    if (
        set(policy) != {"Version", "Statement"}
        or policy["Version"] != "2012-10-17"
        or len(statements) != len(expected_statements)
        or {row["Sid"] for row in statements} != set(expected_statements)
    ):
        fail("ST33_PERMISSION_POLICY", "minimal backend/artifact statement inventory drifted")
    for row in statements:
        actions, resource, condition = expected_statements[row["Sid"]]
        actual_actions = [row["Action"]] if isinstance(row["Action"], str) else row["Action"]
        expected_keys = {"Sid", "Effect", "Action", "Resource"}
        if condition is not None:
            expected_keys.add("Condition")
        if (
            set(row) != expected_keys
            or row["Effect"] != "Allow"
            or len(actual_actions) != len(set(actual_actions))
            or set(actual_actions) != actions
            or row["Resource"] != resource
            or row.get("Condition") != condition
        ):
            fail("ST33_PERMISSION_POLICY", "actions, exact resources or key constraints broadened")


def validate_access_remediation() -> None:
    policy = load("deployment/stage3/ChangeBridgeStage33RoleObserver.proposed.json")
    expected = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "ObserveExactExistingChangeBridgeRoleOnly",
                "Effect": "Allow",
                "Action": [
                    "iam:GetRole",
                    "iam:ListRolePolicies",
                    "iam:ListAttachedRolePolicies",
                    "iam:GetRolePolicy",
                ],
                "Resource": "arn:aws:iam::857229544428:role/ChangeBridgeGitHubOidcRole",
            }
        ],
    }
    if policy != expected:
        fail("ST33_ACCESS_POLICY", "exact existing-role observation policy broadened")
    remediation = load("deployment/stage3/access-remediation.json")
    if (
        remediation["status"] != "PREPARED_NOT_EXECUTED"
        or remediation["execution_connection"] != "NOT_QUALIFIED"
        or remediation["account_id"] != "857229544428"
        or remediation["region"] != "ap-southeast-2"
        or remediation["target_role_arn"] != expected["Statement"][0]["Resource"]
        or remediation["aws_mutations_performed_by_preparation"] != 0
        or remediation["phase1"]["new_resource_count"] != 0
        or any(
            remediation["phase1"][flag] is not False
            for flag in (
                "trust_changes",
                "boundary_changes",
                "managed_policy_attachment_changes",
                "other_project_changes",
                "automatic_overwrite_on_collision",
                "self_grant",
            )
        )
        or remediation["phase2"]["resource_arns"] != []
        or remediation["phase2"]["wildcard_resources_permitted"] is not False
    ):
        fail("ST33_ACCESS_AUTHORITY", "unexecuted remediation or exact scope misrepresented")


def validate() -> dict[str, Any]:
    if git("rev-parse", f"{ENTRY}^{{tree}}") != ENTRY_TREE:
        fail("ST33_ENTRY", "entry tree mismatch")
    if git("merge-base", ENTRY, "HEAD") != ENTRY:
        fail("ST33_ENTRY", "branch does not descend from exact Stage 2 entry")

    contract = load("requirements/part3-stage3-contract.json")
    if contract["entry_commit"] != ENTRY or contract["entry_tree"] != ENTRY_TREE:
        fail("ST33_CONTRACT", "entry authority drifted")
    binding = contract["aws_binding"]
    if binding["account_id"] != "857229544428" or binding["region"] != "ap-southeast-2":
        fail("ST33_BINDING", "account or region drifted")
    if contract["aws_mutation_authorized"]:
        fail("ST33_AUTHORITY", "mutation cannot be authorized by repository artifacts")
    if contract["claim_ceiling"] != "AWS_ADMISSION_OBSERVED":
        fail("ST33_CLAIMS", "claim ceiling drifted")
    cost = contract["cost_boundary"]
    if cost["shared_budget_usd_monthly"] != 20 or cost["maximum_resource_lifetime_hours"] != 48:
        fail("ST33_COST", "cost or lifetime boundary drifted")
    if cost["portfolio_credit_is_stage_allowance"]:
        fail("ST33_COST", "portfolio credit misrepresented as stage allowance")
    if cost["proposed_bootstrap_ceiling_usd"] != 3 or cost["proposed_ceiling_accepted"]:
        fail("ST33_COST", "proposed cost ceiling cannot be represented as accepted")
    if cost["budget_alerts_are_hard_spend_cap"]:
        fail("ST33_COST", "budget notifications do not enforce a hard spending cap")
    if cost["lifecycle_conflict"] != "UNRESOLVED_RETAIN_THROUGH_PART3_AND_KMS_DELETION_WINDOW":
        fail("ST33_LIFECYCLE", "lifecycle contradiction cannot be silently cleared")

    manifest = load("deployment/stage3/bootstrap-manifest.json")
    if manifest["manifest_status"] != "PROPOSED_NOT_AUTHORIZED":
        fail("ST33_BOOTSTRAP", "bootstrap proposal is represented as authorized")
    if (
        manifest["account_id"] != binding["account_id"]
        or manifest["region"] != binding["region"]
        or manifest["maximum_lifetime_hours"] != 48
    ):
        fail("ST33_BOOTSTRAP", "manifest account, region or lifetime drifted")
    expected_resources = {
        ("AWS::KMS::Key", "state-key", "provider-assigned"),
        ("AWS::KMS::Alias", "state-key-alias", "alias/changebridge-p3s3-state"),
        (
            "AWS::S3::Bucket",
            "state-bucket",
            "changebridge-p3s3-tfstate-857229544428-ap-southeast-2",
        ),
        (
            "AWS::S3::Bucket",
            "artifact-bucket",
            "changebridge-p3s3-artifacts-857229544428-ap-southeast-2",
        ),
        ("AWS::DynamoDB::Table", "state-locks", "changebridge-p3s3-tf-locks"),
        ("AWS::SNS::Topic", "alerts", "changebridge-p3s3-alerts"),
        ("AWS::SNS::Subscription", "alert-email", "VERIFIED_REDACTED"),
        ("AWS::IAM::Role", "github-actions-role", "ChangeBridgePart3GitHubActionsRole"),
    }
    actual_resources = {
        (row["type"], row["logical_name"], row["physical_name"]) for row in manifest["resources"]
    }
    if len(manifest["resources"]) != 8 or actual_resources != expected_resources:
        fail("ST33_BOOTSTRAP", "exact resource allowlist drifted")
    required_controls = {
        "S3 versioning",
        "S3 block-public-access",
        "S3 bucket-owner-enforced",
        "S3 artifact immutability through version identity and checksum binding",
        "KMS encryption",
        "TLS-only bucket policy",
        "DynamoDB point-in-time recovery",
        "least-privilege OIDC trust bound to the ChangeBridge repository",
        "owner project stage expiry and cost-center tags",
        "collision check before create",
        "create-or-reconcile without destructive replacement",
    }
    if set(manifest["mandatory_controls"]) != required_controls:
        fail("ST33_CONTROLS", "mandatory controls drifted")
    if not manifest["authorization_required"]:
        fail("ST33_AUTHORITY", "exact-resource authorization gate removed")

    validate_proposed_policies()
    validate_access_remediation()

    protected = git(
        "diff",
        "--name-only",
        ENTRY,
        "--",
        "evidence/part1",
        "evidence/part2",
        "evidence/part3/stage1",
        "evidence/part3/stage2",
    )
    if protected:
        fail("ST33_PROTECTED", f"protected evidence changed: {protected.splitlines()}")

    criteria = load("requirements/part3-stage3-acceptance.json")["criteria"]
    if len(criteria) != 52 or len({row["id"] for row in criteria}) != 52:
        fail("ST33_ACCEPTANCE", "acceptance registry must contain 52 unique criteria")
    if [row["id"] for row in criteria] != [f"ST33-AC-{number:02d}" for number in range(1, 53)]:
        fail("ST33_ACCEPTANCE", "acceptance IDs are not contiguous")
    if any(row["status"] != ("PASS" if row["id"] in PASSED_IDS else "PENDING") for row in criteria):
        fail("ST33_ACCEPTANCE", "unsupported acceptance transition")

    review = load("evidence/part3/stage3/aws-readonly-review.json")
    expected_archives = {
        "ChangeBridge-Stage3-ReadOnly.zip": (
            "a97177eba30a944c83e3d4b152a96a8389b4b92ad15b466ff32ff2c19c3a8ca7"
        ),
        "ChangeBridge-Stage3-Supplemental.zip": (
            "d73803158b44556eab1fb4a4fad4989e35e98d6999cd329729c1e4460775c17e"
        ),
    }
    if (
        len(review["archives"]) != 2
        or {row["name"]: row["sha256"] for row in review["archives"]} != expected_archives
        or any(row["internal_checksums"] != "PASS" for row in review["archives"])
        or review["account_id"] != binding["account_id"]
        or review["region"] != binding["region"]
    ):
        fail("ST33_REVIEW", "review provenance or account binding drifted")
    observed = review["observations"]
    if (
        any(
            observed[key] != "ABSENT"
            for key in (
                "state_bucket_collision",
                "artifact_bucket_collision",
                "kms_alias_collision",
                "sns_topic_collision",
            )
        )
        or observed["lock_table_collision"] != "ABSENT_RESOURCE_NOT_FOUND"
    ):
        fail("ST33_REVIEW", "collision observations do not prove absence")
    if (
        observed["candidate_role"] != "ABSENT_NO_SUCH_ENTITY"
        or observed["candidate_trust_policy"] != "NOT_OBSERVED"
        or observed["candidate_permissions_and_boundary"] != "NOT_OBSERVED"
        or observed["complete_quota_usage_comparison"] != "NOT_PROVEN"
        or set(observed["regional_api_availability"]) != {"DMS", "GLUE", "STEP_FUNCTIONS"}
        or review["collection_time_utc"] != "UNKNOWN_NOT_RECORDED_IN_ARCHIVES"
        or not review["pre_mutation_refresh_required"]
        or review["aws_mutation_authorized"]
        or review["aws_mutations_in_review"] != 0
    ):
        fail("ST33_REVIEW", "review overclaims freshness, capability or authorization")
    receipt = load("evidence/part3/stage3/stage-receipt.json")
    if receipt["criteria_passed"] != 32 or receipt["criteria_pending"] != 20:
        fail("ST33_RECEIPT", "acceptance counts drifted")
    validation = load("evidence/part3/stage3/local-validation.json")
    if (
        validation["result"] != "FOCUSED_PASS_BROADER_QUALITY_NOT_PASSED"
        or validation["broader_run"]["result"] != "FAIL_COVERAGE"
        or validation["broader_run"]["required_coverage_percent"] != 85
        or validation["coverage_threshold_changed"]
        or validation["stage_complete"]
    ):
        fail("ST33_VALIDATION", "failed broader validation cannot be presented as complete")

    public_roots = [
        ROOT / "requirements/part3-stage3-contract.json",
        ROOT / "deployment/stage3",
        ROOT / "docs/part3/stage3",
        ROOT / "evidence/part3/stage3",
        ROOT / "PART3_STAGE3_STATUS.md",
    ]
    email_pattern = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
    for root in public_roots:
        files = sorted(root.rglob("*")) if root.is_dir() else [root]
        for file in files:
            if file.is_file() and email_pattern.search(file.read_text(encoding="utf-8")):
                fail("ST33_PRIVACY", f"email address found in public artifact: {file}")

    artifact_manifest = load("evidence/part3/stage3/artifact-manifest.json")
    roots = [
        "requirements/part3-stage3-contract.json",
        "requirements/part3-stage3-acceptance.json",
        "deployment/stage3",
        "docs/part3/stage3",
        "scripts/collect_stage33_readonly.sh",
        "scripts/build_stage33_evidence.py",
        "scripts/install_stage33_role_observer.sh",
        "scripts/validate_part3_stage3.py",
        "tests/test_part3_stage3_validator.py",
        "tests/test_stage33_oidc_qualification.py",
        "tests/test_stage33_role_observer_installation.py",
        ".github/workflows/aws-oidc-identity.yml",
        ".github/workflows/part3-stage3-aws-admission.yml",
        "PART3_STAGE3_STATUS.md",
        "evidence/part3/stage3",
    ]
    expected_paths = set()
    for item in roots:
        root = ROOT / item
        files = sorted(root.rglob("*")) if root.is_dir() else [root]
        expected_paths.update(
            file.relative_to(ROOT).as_posix()
            for file in files
            if file.is_file() and file.name not in {"artifact-manifest.json", "stage-receipt.json"}
        )
    paths = [row["path"] for row in artifact_manifest["artifacts"]]
    if len(paths) != len(set(paths)) or set(paths) != expected_paths:
        fail("ST33_MANIFEST", "manifest coverage is incomplete or duplicated")
    for row in artifact_manifest["artifacts"]:
        path = ROOT / row["path"]
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
            fail("ST33_MANIFEST", f"artifact mismatch: {row['path']}")

    return {
        "result": "PASS",
        "criteria_passed": 32,
        "criteria_pending": 20,
        "entry_commit": ENTRY,
        "entry_tree": ENTRY_TREE,
        "aws_account": binding["account_id"],
        "aws_region": binding["region"],
        "aws_mutation_authorized": False,
        "claim_ceiling": contract["claim_ceiling"],
    }


if __name__ == "__main__":
    print(json.dumps(validate(), sort_keys=True))
