#!/usr/bin/env python3
"""Validate received diagnostic provenance and exact controls without AWS calls."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SUBJECT_PREFIX = (
    "repo:bhuvaneshwaranmurugan21@276895096/"
    "changebridge-cdc-migration-platform@1332970949:ref:refs/heads/"
)


def validate_diagnostic(payload: dict[str, Any]) -> dict[str, Any]:
    """Check this immutable observation; do not promote it into bootstrap proof."""
    if (
        payload.get("repository")
        != "bhuvaneshwaranmurugan21/changebridge-cdc-migration-platform"
        or payload.get("account_id") != "857229544428"
        or payload.get("region") != "ap-southeast-2"
        or payload.get("label") != "DIAGNOSTIC_NOT_ADMISSION_COMPLETE"
        or payload.get("result") != "PASS"
        or payload.get("aws_writes") != 0
        or payload.get("operator_role") != "AccountFullAccessRole"
    ):
        raise ValueError("ST33_DIAGNOSTIC_SCOPE")
    role = payload["role"]
    provider = "arn:aws:iam::857229544428:oidc-provider/token.actions.githubusercontent.com"
    expected_trust = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Federated": provider},
            "Action": "sts:AssumeRoleWithWebIdentity",
            "Condition": {"StringEquals": {
                "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
                "token.actions.githubusercontent.com:sub": SUBJECT_PREFIX + "main",
            }},
        }],
    }
    if (
        role.get("Arn") != "arn:aws:iam::857229544428:role/ChangeBridgeGitHubOidcRole"
        or role.get("RoleId") != "AROA4PFW4ZPWEB3YXXLX3"
        or role.get("AssumeRolePolicyDocument") != expected_trust
        or role.get("PermissionsBoundary") is not None
        or payload.get("inline_policies") != []
        or payload.get("observed_managed_and_boundary_policies") != []
        or payload.get("candidate_status") != "ABSENT_NO_SUCH_ENTITY"
        or payload.get("candidate_role") is not None
        or payload.get("oidc_provider_arn") != provider
        or payload["oidc_provider"].get("Url") != "token.actions.githubusercontent.com"
        or payload["oidc_provider"].get("ClientIDList") != ["sts.amazonaws.com"]
    ):
        raise ValueError("ST33_DIAGNOSTIC_CONTROLS")
    selected = {
        key: role[key]
        for key in ("Arn", "RoleId", "AssumeRolePolicyDocument", "PermissionsBoundary")
    }
    canonical = (json.dumps(selected, sort_keys=True, separators=(",", ":")) + "\n").encode()
    if hashlib.sha256(canonical).hexdigest() != payload["identity_controls_digest"]:
        raise ValueError("ST33_DIAGNOSTIC_DIGEST")
    actual_script = ROOT / "scripts/collect_stage33_access_diagnostic.sh"
    if hashlib.sha256(actual_script.read_bytes()).hexdigest() != payload["source_script_sha256"]:
        raise ValueError("ST33_DIAGNOSTIC_SCRIPT")
    return {"result": "OBSERVATION_REVIEWED", "bootstrap_proven": False, "aws_calls": 0}


if __name__ == "__main__":
    source = ROOT / "evidence/part3/stage3/administrator-access-diagnostic.json"
    print(json.dumps(validate_diagnostic(json.loads(source.read_text())), sort_keys=True))
