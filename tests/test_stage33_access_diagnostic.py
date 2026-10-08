"""Exercise actual local diagnostic guards, without AWS calls or capability mocks."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/collect_stage33_access_diagnostic.sh"


def script_text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def function_jq_filter(name: str) -> str:
    match = re.search(
        rf"{name}\(\)\s*\{{\s*jq\s+"
        r"(?:(?:-e|--arg\s+\w+\s+\"[^\"]+\")\s+)*'(.+?)'",
        script_text(),
        re.DOTALL,
    )
    assert match is not None, "the actual diagnostic filter must remain present"
    return match.group(1)


def jq_result(
    name: str, payload: Any, arguments: list[str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["jq", "-e", *(arguments or []), function_jq_filter(name)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
    )


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
        ("857229544428", "arn:aws:sts::857229544428:assumed-role/OtherProjectRole/test", False),
        (
            "857229544428",
            "arn:aws:sts::857229544428:assumed-role/AccountFullAccessRoleOther/test",
            False,
        ),
        ("857229544428", "arn:aws:iam::857229544428:user/AccountFullAccessRole", False),
    ],
)
def test_actual_identity_guard_rejects_unqualified_execution(
    account: str, arn: str, accepted: bool
) -> None:
    result = jq_result("cb_identity_guard", {"Account": account, "Arn": arn})
    assert (result.returncode == 0) is accepted


@pytest.mark.parametrize(
    "actual_arn,role_id,accepted",
    [
        ("arn:aws:iam::857229544428:role/ChangeBridgeGitHubOidcRole", "AROATEST", True),
        ("arn:aws:iam::857229544428:role/OtherProjectRole", "AROATEST", False),
        ("arn:aws:iam::111111111111:role/ChangeBridgeGitHubOidcRole", "AROATEST", False),
        ("arn:aws:iam::857229544428:role/ChangeBridgePart3GitHubActionsRole", "AROATEST", False),
        ("arn:aws:iam::857229544428:role/ChangeBridgeGitHubOidcRole", "", False),
    ],
)
def test_actual_role_guard_rejects_other_project_or_account_response(
    actual_arn: str, role_id: str, accepted: bool
) -> None:
    result = jq_result(
        "cb_role_guard",
        {"Role": {"Arn": actual_arn, "RoleId": role_id}},
        ["--arg", "arn", "arn:aws:iam::857229544428:role/ChangeBridgeGitHubOidcRole"],
    )
    assert (result.returncode == 0) is accepted


@pytest.mark.parametrize("region", ["ap-southeast-2", "us-east-1", "", "ap-southeast-1"])
def test_actual_region_guard(region: str) -> None:
    match = re.search(r"cb_region_guard\(\)\s*\{(.+?)^\}", script_text(), re.DOTALL | re.MULTILINE)
    assert match is not None
    result = subprocess.run(
        ["bash", "-c", match.group(0) + '\ncb_region_guard "$1"', "region-test", region],
        capture_output=True,
        text=True,
    )
    assert (result.returncode == 0) is (region == "ap-southeast-2")


def test_actual_redactor_preserves_evidence_but_removes_email_and_session_identity() -> None:
    payload = {
        "Account": "857229544428",
        "Arn": "arn:aws:sts::857229544428:assumed-role/AccountFullAccessRole/private-session",
        "UserId": "AROATESTROLE:private-session",
        "nested": {
            "userId": "AROANESTED:nested-session",
            "email": "private@example.com",
            "message": (
                "Alert private@example.com for "
                "arn:aws:sts::857229544428:assumed-role/AccountFullAccessRole/another-session"
            ),
        },
        "role_arn": "arn:aws:iam::857229544428:role/ChangeBridgeGitHubOidcRole",
        "status": "DIAGNOSTIC_ONLY",
        "aws_mutations": 0,
    }
    result = jq_result("cb_sanitize", payload)
    assert result.returncode == 0, result.stderr
    redacted = json.loads(result.stdout)
    assert redacted["Account"] == payload["Account"]
    assert redacted["role_arn"] == payload["role_arn"]
    assert redacted["status"] == "DIAGNOSTIC_ONLY"
    assert redacted["aws_mutations"] == 0
    assert "UserId" not in redacted
    assert "userId" not in redacted["nested"]
    assert "email" not in redacted["nested"]
    assert "REDACTED_SESSION" in redacted["Arn"]
    assert "REDACTED_EMAIL" in redacted["nested"]["message"]
    for sensitive in (
        "private@example.com",
        "private-session",
        "nested-session",
        "another-session",
    ):
        assert sensitive not in result.stdout


def test_access_diagnostic_is_valid_bash() -> None:
    result = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_access_diagnostic_has_no_aws_mutation_command() -> None:
    script = script_text()
    forbidden = re.findall(
        r"\b(?:iam|sts|s3api|dynamodb|kms|sns|dms|glue|stepfunctions)\s+"
        r"(?:create|put|update|delete|attach|detach|add|remove|start|stop|schedule|"
        r"cancel|enable|disable|subscribe|unsubscribe|assume)[a-z-]*\b",
        script,
    )
    assert forbidden == []
    assert "get-caller-identity" in script
    assert "get-role" in script
    assert 'cb_role_guard "$CB_DIR/old-role.json" "$CB_OLD_ARN"' in script
    assert 'cb_role_guard "$CB_DIR/candidate-role.json" "$CB_CANDIDATE_ARN"' in script
    assert script.index('cb_region_guard "$CB_OBSERVED_REGION"') < script.index(
        "cb_read caller sts get-caller-identity"
    )
    assert 'label:"DIAGNOSTIC_NOT_ADMISSION_COMPLETE"' in script
    assert "aws_writes:0" in script
