from copy import deepcopy

import pytest

from scripts.validate_part3_stage1 import Stage31Error, load_bundle, validate, validate_authority


def test_stage31_candidate_validates() -> None:
    assert validate()["result"] == "PASS"


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ("assigned_aws", "ST31_AWS_NOT_UNASSIGNED"),
        ("missing_stage", "ST31_STAGE_SEQUENCE"),
        ("criterion_gap", "ST31_ACCEPTANCE_SEQUENCE"),
        ("managed_claim", "ST31_CLAIM_PROMOTION"),
        ("overlay_gap", "ST31_REQUIREMENT_OVERLAY"),
    ],
)
def test_stage31_mutations_fail_closed(mutation: str, code: str) -> None:
    bundle = deepcopy(load_bundle())
    if mutation == "assigned_aws":
        bundle["aws"]["account_id"] = "123456789012"
    elif mutation == "missing_stage":
        bundle["stages"]["stages"].pop()
    elif mutation == "criterion_gap":
        bundle["acceptance"]["criteria"][10]["id"] = "ST31-AC-99"
    elif mutation == "managed_claim":
        bundle["claims"]["claim_ceiling_after"] = "AWS_VERIFIED"
    elif mutation == "overlay_gap":
        bundle["corrections"]["corrections"].pop()
    with pytest.raises(Stage31Error, match=code):
        validate_authority(bundle)
