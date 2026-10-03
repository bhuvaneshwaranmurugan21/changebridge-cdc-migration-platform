"""Local installer guard tests; these make no AWS calls or installation claims."""

from __future__ import annotations

import copy
import json
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/install_stage33_role_observer.sh"
POLICY = ROOT / "deployment/stage3/ChangeBridgeStage33RoleObserver.proposed.json"
ROLE_ARN = "arn:aws:iam::857229544428:role/ChangeBridgeGitHubOidcRole"


def installer_text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def jq_guard(argument: str, variable: str) -> str:
    match = re.search(
        rf"jq -e --arg {argument} \"\${variable}\" '(.+?)'\s+\"\$",
        installer_text(),
        re.DOTALL,
    )
    assert match is not None, "the actual installer guard must remain present"
    return match.group(1)


@pytest.mark.parametrize(
    "case",
    [
        "valid",
        "other_account",
        "other_project_role",
        "wildcard_resource",
        "extra_action",
        "write_action",
        "extra_statement",
        "duplicate_action",
        "unexpected_policy_element",
    ],
)
def test_actual_policy_guard_rejects_scope_expansion(case: str) -> None:
    payload: dict[str, Any] = json.loads(POLICY.read_text(encoding="utf-8"))
    statement = payload["Statement"][0]
    if case == "other_account":
        statement["Resource"] = ROLE_ARN.replace("857229544428", "111111111111")
    elif case == "other_project_role":
        statement["Resource"] = "arn:aws:iam::857229544428:role/UnrelatedProjectRole"
    elif case == "wildcard_resource":
        statement["Resource"] = "*"
    elif case == "extra_action":
        statement["Action"].append("iam:GetPolicyVersion")
    elif case == "write_action":
        statement["Action"][0] = "iam:PutRolePolicy"
    elif case == "extra_statement":
        payload["Statement"].append(copy.deepcopy(statement))
    elif case == "duplicate_action":
        statement["Action"][0] = statement["Action"][1]
    elif case == "unexpected_policy_element":
        statement["Principal"] = "*"
    result = subprocess.run(
        ["jq", "-e", "--arg", "arn", ROLE_ARN, jq_guard("arn", "ROLE_ARN")],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
    )
    assert (result.returncode == 0) is (case == "valid")


@pytest.mark.parametrize(
    "account,arn,accepted",
    [
        ("857229544428", "arn:aws:sts::857229544428:assumed-role/AccountFullAccessRole/test", True),
        (
            "111111111111",
            "arn:aws:sts::111111111111:assumed-role/AccountFullAccessRole/test",
            False,
        ),
        (
            "857229544428",
            "arn:aws:sts::111111111111:assumed-role/AccountFullAccessRole/test",
            False,
        ),
        (
            "857229544428",
            "arn:aws:sts::857229544428:assumed-role/ChangeBridgeGitHubOidcRole/test",
            False,
        ),
        (
            "857229544428",
            "arn:aws:sts::857229544428:assumed-role/AccountFullAccessRoleOther/test",
            False,
        ),
        ("857229544428", "arn:aws:iam::857229544428:user/AccountFullAccessRole", False),
    ],
)
def test_actual_administrator_identity_guard(account: str, arn: str, accepted: bool) -> None:
    result = subprocess.run(
        ["jq", "-e", "--arg", "account", "857229544428", jq_guard("account", "ACCOUNT")],
        input=json.dumps({"Account": account, "Arn": arn}),
        capture_output=True,
        text=True,
    )
    assert (result.returncode == 0) is accepted


@pytest.mark.parametrize(
    "arguments",
    [
        [],
        ["--apply"],
        ["--expected-policy-sha256"],
        ["--expected-policy-sha256", "not-a-digest"],
        ["--expected-policy-sha256", "f" * 64, "--force"],
        ["--expected-role-id"],
        ["--expected-trust-sha256"],
        ["--apply", "--expected-policy-sha256", "f" * 64],
        [
            "--apply",
            "--expected-policy-sha256",
            "f" * 64,
            "--expected-role-id",
            "AROAEXACTROLE",
            "--expected-trust-sha256",
            "invalid",
        ],
        [
            "--apply",
            "--expected-policy-sha256",
            "f" * 64,
            "--expected-role-id",
            "wrong-role",
            "--expected-trust-sha256",
            "a" * 64,
        ],
    ],
)
def test_invalid_invocation_stops_before_tool_or_aws_access(arguments: list[str]) -> None:
    result = subprocess.run(["bash", str(SCRIPT), *arguments], capture_output=True, text=True)
    assert result.returncode == 10
    assert "FAIL:" in result.stderr
    assert "AWS_EXIT=" not in result.stderr


def test_write_inventory_and_order_remain_bounded() -> None:
    script = installer_text()
    assert re.findall(r"aws iam ([a-z-]+)", script) == ["get-role-policy", "put-role-policy"]
    assert script.count("aws iam put-role-policy") == 1
    write_position = script.index("aws iam put-role-policy")
    for guard in (
        "policy differs from reviewed exact digest",
        "administrator execution environment must explicitly bind ap-southeast-2",
        "self-grant prohibited",
        "existing same-name policy differs; overwrite prohibited",
        'if [[ "$mode" == "CHECK_ONLY" ]]',
        'if [[ "$prior_state" == "ABSENT" ]]',
    ):
        assert script.index(guard) < write_position
    assert script.index("read_api policy-after") > write_position
    assert "role trust changed during execution" in script
    assert "role identity changed during execution" in script
    assert "permissions boundary changed during execution" in script
    assert 'exit "$api_exit"' in script
    assert "stage3_complete:false" in script
    assert "no create-only/CAS operation" in script


def test_reviewed_private_policy_bytes_and_role_identity_gate_the_write() -> None:
    script = installer_text()
    write_position = script.index("aws iam put-role-policy")
    copy_position = script.index('cp -- "$policy_file" "$frozen_policy_file"')
    hash_position = script.index('sha256sum "$frozen_policy_file"')
    assert copy_position < hash_position < write_position
    assert '--policy-document "file://$frozen_policy_file"' in script
    assert '--policy-document "file://$policy_file"' not in script
    assert (
        script.index("apply requires independently reviewed RoleId and trust SHA256")
        < write_position
    )
    assert script.index("role identity or trust differs from reviewed preflight") < write_position
    assert '"$role_id" == "$expected_role_id"' in script
    assert '"$trust_digest" == "$expected_trust_digest"' in script
    assert "role_id:$role_id,trust_sha256:$trust_sha256" in script
    assert "permissions_boundary_unchanged:true" in script


def test_remediation_remains_unexecuted_and_managed_policy_reads_unbound() -> None:
    payload = json.loads((ROOT / "deployment/stage3/access-remediation.json").read_text())
    assert payload["status"] == "PREPARED_NOT_EXECUTED"
    assert payload["execution_connection"] == "NOT_QUALIFIED"
    assert payload["aws_mutations_performed_by_preparation"] == 0
    assert payload["phase2"]["resource_arns"] == []
    assert payload["phase2"]["wildcard_resources_permitted"] is False
    for flag in (
        "trust_changes",
        "boundary_changes",
        "managed_policy_attachment_changes",
        "other_project_changes",
        "automatic_overwrite_on_collision",
        "self_grant",
    ):
        assert payload["phase1"][flag] is False


def test_access_remediation_validator_accepts_only_preparation() -> None:
    from scripts.validate_part3_stage3 import validate_access_remediation

    validate_access_remediation()


@pytest.mark.parametrize(
    "case,code",
    [
        ("wildcard_resource", "ST33_ACCESS_POLICY"),
        ("extra_write_action", "ST33_ACCESS_POLICY"),
        ("other_project_role", "ST33_ACCESS_POLICY"),
        ("false_qualified_connection", "ST33_ACCESS_AUTHORITY"),
        ("premature_managed_policy_arn", "ST33_ACCESS_AUTHORITY"),
        ("trust_change", "ST33_ACCESS_AUTHORITY"),
        ("automatic_collision_overwrite", "ST33_ACCESS_AUTHORITY"),
        ("self_grant", "ST33_ACCESS_AUTHORITY"),
        ("false_execution_receipt", "ST33_ACCESS_AUTHORITY"),
    ],
)
def test_access_remediation_validator_rejects_unproven_or_broadened_scope(
    monkeypatch: pytest.MonkeyPatch, case: str, code: str
) -> None:
    from scripts import validate_part3_stage3 as module

    original = module.load

    def mutated(path: str) -> dict[str, Any]:
        payload = copy.deepcopy(original(path))
        if path == "deployment/stage3/ChangeBridgeStage33RoleObserver.proposed.json":
            statement = payload["Statement"][0]
            if case == "wildcard_resource":
                statement["Resource"] = "*"
            elif case == "extra_write_action":
                statement["Action"].append("iam:PutRolePolicy")
            elif case == "other_project_role":
                statement["Resource"] = "arn:aws:iam::857229544428:role/UnrelatedProjectRole"
        elif path == "deployment/stage3/access-remediation.json":
            if case == "false_qualified_connection":
                payload["execution_connection"] = "QUALIFIED"
            elif case == "premature_managed_policy_arn":
                payload["phase2"]["resource_arns"] = [
                    "arn:aws:iam::857229544428:policy/NotActuallyObserved"
                ]
            elif case in {"trust_change", "automatic_collision_overwrite", "self_grant"}:
                flag = {
                    "trust_change": "trust_changes",
                    "automatic_collision_overwrite": "automatic_overwrite_on_collision",
                    "self_grant": "self_grant",
                }[case]
                payload["phase1"][flag] = True
            elif case == "false_execution_receipt":
                payload["aws_mutations_performed_by_preparation"] = 1
        return payload

    monkeypatch.setattr(module, "load", mutated)
    with pytest.raises(module.Stage33Error, match=code):
        module.validate_access_remediation()


def test_manifest_refresh_preserves_observation_and_run_evidence() -> None:
    import hashlib
    import sys

    evidence = ROOT / "evidence/part3/stage3"
    before = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in evidence.glob("*.json")
        if p.name != "artifact-manifest.json"
    }
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/build_stage33_evidence.py"), "--manifest-only"],
        check=True,
        capture_output=True,
        text=True,
    )
    after = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in evidence.glob("*.json")
        if p.name != "artifact-manifest.json"
    }
    assert before == after
