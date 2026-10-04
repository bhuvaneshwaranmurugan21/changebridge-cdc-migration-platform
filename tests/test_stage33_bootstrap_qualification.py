"""Offline scope and archived-control tests. No simulated AWS success satisfies admission."""

import copy
import json

import pytest

from scripts.qualify_stage33_bootstrap import (
    ACCOUNT,
    ARTIFACT,
    LOCKS,
    OLD_ROLE,
    PROVIDER,
    REGION,
    ROLE,
    ROOT,
    STATE,
    TOPIC,
    QualificationError,
    allowed_request,
    validate_identity,
    validate_old_role,
    validate_provider,
)


@pytest.mark.parametrize("service,operation,payload", [
    ("sts", "get-caller-identity", {}),
    ("iam", "get-role", {"RoleName": OLD_ROLE}),
    ("iam", "get-role", {"RoleName": ROLE}),
    ("iam", "list-role-policies", {"RoleName": OLD_ROLE}),
    ("iam", "list-attached-role-policies", {"RoleName": ROLE}),
    ("iam", "get-open-id-connect-provider", {"OpenIDConnectProviderArn": PROVIDER}),
    ("s3api", "head-bucket", {"Bucket": STATE, "ExpectedBucketOwner": ACCOUNT}),
    ("s3api", "head-bucket", {"Bucket": ARTIFACT, "ExpectedBucketOwner": ACCOUNT}),
    ("dynamodb", "describe-table", {"TableName": LOCKS}),
    ("kms", "describe-key", {
        "KeyId": f"arn:aws:kms:{REGION}:{ACCOUNT}:alias/changebridge-p3s3-state",
    }),
    ("sns", "get-topic-attributes", {"TopicArn": TOPIC}),
])
def test_only_exact_reviewed_requests_are_constructible(service, operation, payload):
    assert allowed_request(service, operation, payload)
    assert not allowed_request(service, operation, {**payload, "UnexpectedParameter": True})


@pytest.mark.parametrize("service,operation,payload", [
    ("iam", "put-role-policy", {"RoleName": ROLE}),
    ("iam", "get-role", {"RoleName": "another-project-role"}),
    ("iam", "list-roles", {}),
    ("s3api", "head-bucket", {"Bucket": STATE}),
    ("s3api", "head-bucket", {"Bucket": "another-project-bucket", "ExpectedBucketOwner": ACCOUNT}),
    ("kms", "describe-key", {"KeyId": "alias/aws/s3"}),
    ("dynamodb", "describe-table", {"TableName": "another-project-table"}),
    ("sns", "list-topics", {}),
    ("glue", "get-jobs", {}),
])
def test_other_project_global_inventory_and_mutation_requests_are_rejected(
    service, operation, payload
):
    assert not allowed_request(service, operation, payload)


def test_identity_guard_is_exact_and_does_not_echo_sessions():
    # Structural fixture only: never emitted as an observed identity or admission result.
    good = {"Account": ACCOUNT,
            "Arn": f"arn:aws:sts::{ACCOUNT}:assumed-role/AccountFullAccessRole/LOCAL_TEST"}
    validate_identity(good)
    for payload in (None, {}, {**good, "Account": "000000000000"},
                    {**good, "Arn": good["Arn"].replace("AccountFullAccessRole", ROLE)}):
        with pytest.raises(QualificationError, match="unexpected administrator"):
            validate_identity(payload)


def diagnostic():
    return json.loads((ROOT / "evidence/part3/stage3/administrator-access-diagnostic.json")
                      .read_text())


def test_archived_provider_and_role_controls_are_reviewed_without_promoting_to_live_proof():
    accepted = diagnostic()
    validate_provider(accepted["oidc_provider"], accepted["oidc_provider"])
    validate_old_role({"Role": accepted["role"]}, accepted["role"])
    with pytest.raises(QualificationError):
        validate_old_role(None, accepted["role"])
    with pytest.raises(QualificationError):
        validate_provider(None, accepted["oidc_provider"])


@pytest.mark.parametrize("field", ["RoleId", "Arn", "MaxSessionDuration", "PermissionsBoundary"])
def test_archived_role_identity_and_security_drift_is_rejected(field):
    accepted = diagnostic()["role"]
    changed = copy.deepcopy(accepted)
    changed[field] = "DRIFT"
    with pytest.raises(QualificationError, match="drifted"):
        validate_old_role({"Role": changed}, accepted)


@pytest.mark.parametrize("field", ["Url", "ClientIDList", "ThumbprintList", "CreateDate", "Tags"])
def test_archived_provider_drift_is_rejected(field):
    accepted = diagnostic()["oidc_provider"]
    changed = copy.deepcopy(accepted)
    changed[field] = "DRIFT"
    with pytest.raises(QualificationError, match="drifted"):
        validate_provider(changed, accepted)


def test_provider_tag_order_and_equivalent_timestamp_preserve_exact_semantics():
    accepted = diagnostic()["oidc_provider"]
    observed = copy.deepcopy(accepted)
    observed["Tags"] = list(reversed(observed["Tags"]))
    observed["CreateDate"] = observed["CreateDate"].replace("+00:00", "Z")
    validate_provider(observed, accepted)
    observed["Tags"].append(observed["Tags"][0])
    with pytest.raises(QualificationError, match="malformed"):
        validate_provider(observed, accepted)


def test_missing_aws_cli_is_a_real_guard_not_a_bootstrap_success(tmp_path, monkeypatch):
    from scripts.qualify_stage33_bootstrap import AwsReader
    from scripts.stage33_bootstrap_journal import BootstrapJournal

    # Model absence of the executable only; never synthesize an AWS response or PASS receipt.
    monkeypatch.setattr("scripts.qualify_stage33_bootstrap.shutil.which", lambda _: None)
    with BootstrapJournal(tmp_path / "journal", {"package_sha256": "1" * 64}) as journal:
        with pytest.raises(QualificationError, match="AWS CLI is unavailable"):
            AwsReader(journal)
        assert len(journal.entries) == 1
        assert journal.pending is None


def test_command_uses_exact_tls_endpoint_and_private_stdin():
    from scripts.qualify_stage33_bootstrap import command_for

    payload = {"RoleName": ROLE}
    command = command_for("/usr/bin/aws", "iam", "get-role", payload)
    assert command[:3] == ["/usr/bin/aws", "iam", "get-role"]
    assert command[command.index("--endpoint-url") + 1] == "https://iam.amazonaws.com"
    assert command[command.index("--cli-input-json") + 1] == "file:///dev/stdin"
    assert "--no-verify-ssl" not in command
    assert ROLE not in command
    with pytest.raises(QualificationError, match="outside exact"):
        command_for("/usr/bin/aws", "iam", "delete-role", payload)


def test_malformed_role_cannot_be_accepted():
    with pytest.raises(QualificationError, match="drifted"):
        validate_old_role({"Role": "invalid"}, diagnostic()["role"])
