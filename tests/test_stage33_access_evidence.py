"""Negative controls for operator-provided observations; no AWS service mocks."""

from __future__ import annotations

import copy
import json

import pytest

from scripts.validate_stage33_access_evidence import ROOT, validate_diagnostic


def observation() -> dict:
    return json.loads(
        (ROOT / "evidence/part3/stage3/administrator-access-diagnostic.json").read_text()
    )


def test_received_diagnostic_is_an_observation_only() -> None:
    assert validate_diagnostic(observation()) == {
        "result": "OBSERVATION_REVIEWED", "bootstrap_proven": False, "aws_calls": 0,
    }


@pytest.mark.parametrize("case", [
    "account", "region", "writes", "completion_claim", "candidate", "role_id",
    "trust", "boundary", "permissions", "control_digest", "script_digest",
])
def test_received_diagnostic_rejects_altered_controls(case: str) -> None:
    payload = copy.deepcopy(observation())
    if case == "account":
        payload["account_id"] = "111111111111"
    elif case == "region":
        payload["region"] = "us-east-1"
    elif case == "writes":
        payload["aws_writes"] = 1
    elif case == "completion_claim":
        payload["label"] = "AWS_ADMISSION_VERIFIED"
    elif case == "candidate":
        payload["candidate_role"] = {"Arn": "invented"}
    elif case == "role_id":
        payload["role"]["RoleId"] = "changed"
    elif case == "trust":
        payload["role"]["AssumeRolePolicyDocument"]["Statement"][0]["Condition"][
            "StringEquals"
        ]["token.actions.githubusercontent.com:sub"] = "repo:any/*"
    elif case == "boundary":
        payload["role"]["PermissionsBoundary"] = {"PermissionsBoundaryArn": "invented"}
    elif case == "permissions":
        payload["inline_policies"] = [{"PolicyName": "invented"}]
    elif case == "control_digest":
        payload["identity_controls_digest"] = "0" * 64
    elif case == "script_digest":
        payload["source_script_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        validate_diagnostic(payload)
