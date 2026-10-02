from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


def guard_script() -> str:
    workflow = (
        Path(__file__).resolve().parents[1] / ".github/workflows/aws-oidc-identity.yml"
    ).read_text()
    guard, _ = workflow.split("      - name: Assume repository-specific AWS role", 1)
    block = guard.split("        run: |\n", 1)[1]
    return "\n".join(line[10:] for line in block.splitlines())


@pytest.mark.parametrize(
    "key,value",
    [
        ("CB_REPOSITORY", "owner/other-project"),
        ("CB_REF", "refs/heads/part3-stage3-aws-admission"),
        ("CB_EVENT", "push"),
        ("CB_QUALIFY", "false"),
        ("CB_ROLE_ARN", "arn:aws:iam::111111111111:role/OtherRole"),
        ("CB_REGION", "us-east-1"),
        ("CB_QUALIFY", "true"),
    ],
)
def test_iam_qualification_scope_guard(key: str, value: str) -> None:
    environment = {
        **os.environ,
        "CB_REPOSITORY": "bhuvaneshwaranmurugan21/changebridge-cdc-migration-platform",
        "CB_REF": "refs/heads/main",
        "CB_EVENT": "workflow_dispatch",
        "CB_QUALIFY": "true",
        "CB_ROLE_ARN": "arn:aws:iam::857229544428:role/ChangeBridgeGitHubOidcRole",
        "CB_REGION": "ap-southeast-2",
    }
    environment[key] = value
    result = subprocess.run(
        ["bash", "-c", guard_script()], env=environment, capture_output=True, text=True
    )
    assert (result.returncode == 0) is (key == "CB_QUALIFY" and value == "true")


def test_iam_qualification_guard_precedes_credentials_and_is_read_only() -> None:
    workflow = (
        Path(__file__).resolve().parents[1] / ".github/workflows/aws-oidc-identity.yml"
    ).read_text()
    assert workflow.index("Guard Stage 3 qualification") < workflow.index(
        "Assume repository-specific AWS role"
    )
    for api in (
        "get-role",
        "list-role-policies",
        "list-attached-role-policies",
        "get-role-policy",
        "get-policy-version",
    ):
        assert f"iam {api}" in workflow
    for forbidden in ("iam create-", "iam update-", "iam put-", "iam attach-", "iam delete-"):
        assert forbidden not in workflow
    assert 'exit "$api_exit"' in workflow
    assert "TRUST_AND_PERMISSION_ACCEPTANCE=REQUIRES_INDEPENDENT_REVIEW" in workflow
