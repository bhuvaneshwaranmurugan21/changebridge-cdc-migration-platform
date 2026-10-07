"""Approval/policy request correctness, never managed role effectiveness or admission proof."""

import copy
import hashlib
import json

import pytest

import scripts.stage33_lifecycle_authority as authority
from scripts.prepare_stage33_bootstrap import ACCOUNT, REGION
from scripts.stage33_execution_bindings import ExecutionBindings
from scripts.stage33_lifecycle_authority import (
    LifecycleAuthorityError,
    approval,
    policies,
    schedule,
)


def bindings(key=None):
    endpoint = "local@example.test"
    return ExecutionBindings(
        "lifecycle-test-1234",
        "2026-10-07T00:00:00Z",
        "2026-10-09T00:00:00Z",
        endpoint,
        hashlib.sha256(endpoint.encode()).hexdigest(),
        key,
    )


def test_scope_approval_is_not_resource_creation_or_cost_acceptance():
    approved = approval()
    assert len(approved["approved_resources"]) == 7
    assert approved["approved_preparation"] is True
    assert approved["aws_resource_creation_authorized"] is False
    assert approved["controller_retention_maximum_days"] == 10
    assert approved["original_operational_deadline_hours"] == 48
    assert approved["cost_limit_accepted"] is False


def test_initial_controller_has_no_cleanup_or_bootstrap_permissions():
    result = policies(bindings())
    assert result["physical_key_bound_cleanup_permissions"] is None
    assert result["execution_enabled"] is False
    assert result["policy_effectiveness_proven"] is False
    initial = result["initial_lifecycle_permissions"]
    actions = {a for s in initial["Statement"] if s["Effect"] == "Allow" for a in s["Action"]}
    assert all(a.startswith(("s3:", "logs:")) for a in actions)
    assert "s3:DeleteObject" not in actions
    assert not any(
        "authority" in r
        for s in initial["Statement"]
        if s["Effect"] == "Allow" and "s3:PutObject" in s["Action"]
        for r in s["Resource"]
    )


def test_scheduler_trust_uses_supported_group_and_exact_target_not_wrong_schedule_arn():
    result = policies(bindings())
    trust = result["scheduler_trust"]["Statement"][0]
    conditions = trust["Condition"]["StringEquals"]
    assert conditions["aws:SourceAccount"] == ACCOUNT
    assert conditions["aws:SourceArn"] == authority.GROUP_ARN
    assert ":schedule-group/default" in conditions["aws:SourceArn"]
    assert result["scheduler_permissions"]["Statement"][0]["Resource"] == [authority.FUNCTION_ARN]
    assert result["scheduler_permissions"]["Statement"][1]["Resource"] == [authority.QUEUE_ARN]


def test_bound_cleanup_has_exact_key_and_both_required_decrypt_paths():
    key = f"arn:aws:kms:{REGION}:{ACCOUNT}:key/01234567-89ab-cdef-0123-456789abcdef"
    result = policies(bindings(key))
    statements = result["physical_key_bound_cleanup_permissions"]["Statement"]
    kms = [
        s
        for s in statements
        if s["Effect"] == "Allow" and any(a.startswith("kms:") for a in s["Action"])
    ]
    assert all(s["Resource"] == [key] or s["Sid"] == "RemoveExactAlias" for s in kms)
    decrypt = [s for s in kms if "kms:Decrypt" in s["Action"]]
    assert len(decrypt) == 2
    assert {s["Condition"]["StringEquals"]["kms:ViaService"] for s in decrypt} == {
        f"s3.{REGION}.amazonaws.com",
        f"dynamodb.{REGION}.amazonaws.com",
    }
    assert all("kms:GenerateDataKey" not in s["Action"] for s in kms)
    assert not any(
        a.startswith(("iam:Create", "lambda:Create", "dynamodb:Create"))
        for s in statements
        if s["Effect"] == "Allow"
        for a in s["Action"]
    )


def test_immutable_prefix_requires_create_if_absent_head_requires_conditional_write():
    result = policies(bindings())
    by_sid = {s["Sid"]: s for s in result["evidence_bucket_policy"]["Statement"]}
    assert by_sid["DenyImmutableRecordOverwrite"]["Condition"] == {
        "Null": {"s3:if-none-match": "true"}
    }
    assert by_sid["DenyHeadWithoutConditionalWrite"]["Condition"] == {
        "Null": {"s3:if-none-match": "true", "s3:if-match": "true"}
    }


def test_subscription_cleanup_uses_supported_exact_topic_resource_without_wildcard():
    key = f"arn:aws:kms:{REGION}:{ACCOUNT}:key/01234567-89ab-cdef-0123-456789abcdef"
    statements = policies(bindings(key))["physical_key_bound_cleanup_permissions"]["Statement"]
    statement = next(s for s in statements if s["Sid"] == "InspectAndRetireOwnAlertTopic")
    assert statement["Resource"] == [authority.TOPIC]
    assert {"sns:GetSubscriptionAttributes", "sns:Unsubscribe"} <= set(statement["Action"])


def test_alias_deletion_requires_both_exact_alias_and_associated_physical_key():
    key = f"arn:aws:kms:{REGION}:{ACCOUNT}:key/01234567-89ab-cdef-0123-456789abcdef"
    statements = policies(bindings(key))["physical_key_bound_cleanup_permissions"]["Statement"]
    resources = {r for s in statements if s["Effect"] == "Allow"
                 and "kms:DeleteAlias" in s["Action"] for r in s["Resource"]}
    assert resources == {key, f"arn:aws:kms:{REGION}:{ACCOUNT}:alias/changebridge-p3s3-state"}


def test_schedule_has_bounded_retention_delivery_and_no_extra_group():
    result = schedule(bindings(), "2026-10-07T00:01:00Z")
    assert result["EndDate"] == "2026-10-17T00:01:00+00:00"
    assert result["FlexibleTimeWindow"] == {"Mode": "OFF"}
    assert result["GroupName"] == "default"
    assert result["Target"]["RetryPolicy"] == {
        "MaximumEventAgeInSeconds": 900,
        "MaximumRetryAttempts": 2,
    }
    assert result["Target"]["DeadLetterConfig"]["Arn"] == authority.QUEUE_ARN
    for stamp in ["2026-10-06T23:59:00Z", "2026-10-09T00:00:00Z"]:
        with pytest.raises(LifecycleAuthorityError):
            schedule(bindings(), stamp)


@pytest.mark.parametrize(
    "field,value",
    [
        ("aws_resource_creation_authorized", True),
        ("controller_retention_maximum_days", 11),
        ("original_operational_deadline_hours", 49),
        ("cost_limit_accepted", True),
        ("runtime_dependencies_qualified", True),
        ("proposal_source_commit", "foreign"),
        ("pending_execution_gates", []),
        ("execution_enabled", True),
        ("approval_received_at_utc", "2026-10-06T00:00:00Z"),
    ],
)
def test_approval_cannot_be_reinterpreted_or_enlarged(tmp_path, monkeypatch, field, value):
    destination = tmp_path / "deployment/stage3"
    destination.mkdir(parents=True)
    for name in ["lifecycle-authority.json", "lifecycle-scope-correction.proposed.json"]:
        (destination / name).write_bytes((authority.ROOT / "deployment/stage3" / name).read_bytes())
    record = json.loads((destination / "lifecycle-authority.json").read_bytes())
    record[field] = value
    (destination / "lifecycle-authority.json").write_text(json.dumps(record))
    monkeypatch.setattr(authority, "ROOT", tmp_path)
    with pytest.raises(LifecycleAuthorityError):
        approval()


def test_recomputed_internal_proposal_hash_does_not_replace_approved_anchor(tmp_path, monkeypatch):
    destination = tmp_path / "deployment/stage3"
    destination.mkdir(parents=True)
    proposal = json.loads(
        (authority.ROOT / "deployment/stage3/lifecycle-scope-correction.proposed.json").read_bytes()
    )
    record = copy.deepcopy(approval())
    proposal["proposed_additional_resources"][0]["name"] = "foreign"
    raw = json.dumps(proposal).encode()
    record["proposal_sha256"] = hashlib.sha256(raw).hexdigest()
    record["approved_resources"] = proposal["proposed_additional_resources"]
    (destination / "lifecycle-scope-correction.proposed.json").write_bytes(raw)
    (destination / "lifecycle-authority.json").write_text(json.dumps(record))
    monkeypatch.setattr(authority, "ROOT", tmp_path)
    with pytest.raises(LifecycleAuthorityError):
        approval()
