from __future__ import annotations

import pytest

from scripts.validate_part3_stage3 import Stage33Error, load, validate


def test_stage33_candidate_passes() -> None:
    result = validate()
    assert result["result"] == "PASS"
    assert result["criteria_passed"] == 32
    assert result["criteria_pending"] == 20
    assert result["aws_mutation_authorized"] is False


def test_stage33_contract_is_fail_closed() -> None:
    contract = load("requirements/part3-stage3-contract.json")
    assert contract["aws_mutation_authorized"] is False
    assert "terraform_apply" in contract["forbidden_until_exact_bootstrap_authorization"]


def test_stage33_validator_rejects_mutation_authority(monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts import validate_part3_stage3 as module

    original = module.load

    def mutated(path: str):  # type: ignore[no-untyped-def]
        payload = original(path)
        if path == "requirements/part3-stage3-contract.json":
            payload["aws_mutation_authorized"] = True
        return payload

    monkeypatch.setattr(module, "load", mutated)
    with pytest.raises(Stage33Error, match="ST33_AUTHORITY"):
        module.validate()


@pytest.mark.parametrize(
    "case,code",
    [
        ("extra_resource", "ST33_BOOTSTRAP"),
        ("wrong_region", "ST33_BOOTSTRAP"),
        ("missing_control", "ST33_CONTROLS"),
        ("unproven_role_pass", "ST33_ACCEPTANCE"),
        ("unaccepted_cost_pass", "ST33_ACCEPTANCE"),
        ("unknown_capture_claimed_fresh", "ST33_REVIEW"),
        ("collision_inaccessible", "ST33_REVIEW"),
        ("missing_manifest_row", "ST33_MANIFEST"),
        ("duplicate_manifest_row", "ST33_MANIFEST"),
        ("budget_claimed_hard_cap", "ST33_COST"),
        ("lifecycle_conflict_hidden", "ST33_LIFECYCLE"),
    ],
)
def test_stage33_rejects_unsupported_success(
    monkeypatch: pytest.MonkeyPatch, case: str, code: str
) -> None:
    from scripts import validate_part3_stage3 as module

    original = module.load

    def mutated(path: str):  # type: ignore[no-untyped-def]
        payload = original(path)
        if path == "deployment/stage3/bootstrap-manifest.json":
            if case == "extra_resource":
                payload["resources"].append(
                    {
                        "type": "AWS::Glue::Job",
                        "logical_name": "unauthorized",
                        "physical_name": "job",
                    }
                )
            elif case == "wrong_region":
                payload["region"] = "us-east-1"
            elif case == "missing_control":
                payload["mandatory_controls"].remove("TLS-only bucket policy")
        elif path == "requirements/part3-stage3-acceptance.json":
            index = {"unproven_role_pass": 31, "unaccepted_cost_pass": 35}.get(case)
            if index is not None:
                payload["criteria"][index]["status"] = "PASS"
        elif path == "evidence/part3/stage3/aws-readonly-review.json":
            if case == "unknown_capture_claimed_fresh":
                payload["collection_time_utc"] = "2026-10-02T00:00:00Z"
            elif case == "collision_inaccessible":
                payload["observations"]["state_bucket_collision"] = "EXISTS_OR_INACCESSIBLE"
        elif path == "evidence/part3/stage3/artifact-manifest.json":
            if case == "missing_manifest_row":
                payload["artifacts"].pop()
            elif case == "duplicate_manifest_row":
                payload["artifacts"].append(payload["artifacts"][0])
        elif path == "requirements/part3-stage3-contract.json":
            if case == "budget_claimed_hard_cap":
                payload["cost_boundary"]["budget_alerts_are_hard_spend_cap"] = True
            elif case == "lifecycle_conflict_hidden":
                payload["cost_boundary"]["lifecycle_conflict"] = "RESOLVED"
        return payload

    monkeypatch.setattr(module, "load", mutated)
    with pytest.raises(Stage33Error, match=code):
        module.validate()


@pytest.mark.parametrize(
    "case,code",
    [
        ("wrong_subject", "ST33_OIDC_POLICY"),
        ("legacy_exact_subject", "ST33_OIDC_POLICY"),
        ("wrong_owner_id", "ST33_OIDC_POLICY"),
        ("wrong_repository_id", "ST33_OIDC_POLICY"),
        ("immutable_main_subject", "ST33_OIDC_POLICY"),
        ("immutable_pull_request_subject", "ST33_OIDC_POLICY"),
        ("immutable_tag_subject", "ST33_OIDC_POLICY"),
        ("immutable_environment_subject", "ST33_OIDC_POLICY"),
        ("immutable_wildcard_subject", "ST33_OIDC_POLICY"),
        ("wrong_audience", "ST33_OIDC_POLICY"),
        ("wrong_provider", "ST33_OIDC_POLICY"),
        ("broadened_permissions", "ST33_PERMISSION_POLICY"),
        ("key_wildcard", "ST33_PERMISSION_POLICY"),
        ("resource_wildcard", "ST33_PERMISSION_POLICY"),
        ("execution_enabled", "ST33_POLICY_AUTHORITY"),
        ("unexpected_boundary", "ST33_PERMISSION_POLICY"),
    ],
)
def test_stage33_rejects_policy_proposal_weakening(
    monkeypatch: pytest.MonkeyPatch, case: str, code: str
) -> None:
    from scripts import validate_part3_stage3 as module

    original = module.load

    def mutated(path: str):  # type: ignore[no-untyped-def]
        payload = original(path)
        if path == "deployment/stage3/oidc-trust-policy.proposed.json":
            statement = payload["policy"]["Statement"][0]
            immutable_prefix = (
                "repo:bhuvaneshwaranmurugan21@276895096/"
                "changebridge-cdc-migration-platform@1332970949:"
            )
            subject_corrections = {
                "legacy_exact_subject": (
                    "repo:bhuvaneshwaranmurugan21/changebridge-cdc-migration-platform:"
                    "ref:refs/heads/part3-stage3-aws-admission"
                ),
                "wrong_owner_id": (
                    immutable_prefix.replace("@276895096/", "@111111111/")
                    + "ref:refs/heads/part3-stage3-aws-admission"
                ),
                "wrong_repository_id": (
                    immutable_prefix.replace("@1332970949:", "@1111111111:")
                    + "ref:refs/heads/part3-stage3-aws-admission"
                ),
                "immutable_main_subject": immutable_prefix + "ref:refs/heads/main",
                "immutable_pull_request_subject": immutable_prefix + "pull_request",
                "immutable_tag_subject": immutable_prefix + "ref:refs/tags/example",
                "immutable_environment_subject": immutable_prefix + "environment:example",
                "immutable_wildcard_subject": immutable_prefix + "ref:refs/heads/*",
            }
            if case == "wrong_subject":
                statement["Condition"]["StringEquals"][
                    "token.actions.githubusercontent.com:sub"
                ] = "repo:bhuvaneshwaranmurugan21/changebridge-cdc-migration-platform:*"
            elif case in subject_corrections:
                statement["Condition"]["StringEquals"][
                    "token.actions.githubusercontent.com:sub"
                ] = subject_corrections[case]
            elif case == "wrong_audience":
                statement["Condition"]["StringEquals"][
                    "token.actions.githubusercontent.com:aud"
                ] = "*"
            elif case == "wrong_provider":
                statement["Principal"]["Federated"] = (
                    "arn:aws:iam::111111111111:oidc-provider/other"
                )
        elif path == "deployment/stage3/role-permissions.proposed.json":
            if case == "broadened_permissions":
                payload["policy"]["Statement"][0]["Action"] = "s3:*"
            elif case == "key_wildcard":
                payload["policy"]["Statement"][-1]["Resource"] = "*"
            elif case == "resource_wildcard":
                payload["policy"]["Statement"][0]["Resource"] = "arn:aws:s3:::*"
            elif case == "execution_enabled":
                payload["execution_enabled"] = True
            elif case == "unexpected_boundary":
                payload["proposed_permissions_boundary"] = "arn:aws:iam::857229544428:policy/new"
        return payload

    monkeypatch.setattr(module, "load", mutated)
    with pytest.raises(Stage33Error, match=code):
        module.validate()
