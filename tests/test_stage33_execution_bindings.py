"""Request construction only: no synthetic success substitutes for managed proof."""

import copy
import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from scripts.prepare_stage33_bootstrap import ACCOUNT, REGION, compile_package
from scripts.stage33_execution_bindings import (
    BindingError,
    ExecutionBindings,
    materialize_request,
    request_plan,
)

EMAIL = "operator@example.test"
KEY = f"arn:aws:kms:{REGION}:{ACCOUNT}:key/01234567-89ab-cdef-0123-456789abcdef"


def bindings(key=KEY):
    return ExecutionBindings(
        "binding-run-1234",
        "2026-10-07T00:00:00Z",
        "2026-10-08T00:00:00Z",
        EMAIL,
        hashlib.sha256(EMAIL.encode()).hexdigest(),
        key,
    )


@pytest.mark.parametrize("number", range(1, 21))
def test_all_requests_are_concrete_and_keep_execution_disabled(number):
    result = request_plan(compile_package(), f"bootstrap-{number:02d}", bindings())
    assert "__" not in json.dumps(result["request"])
    assert result["execution_enabled"] is False
    assert result["prerequisites_verified"] is False
    assert result["label"] == "CONCRETE_REQUEST_NOT_EXECUTION_AUTHORITY"


def test_first_request_does_not_require_a_key_that_has_not_been_created():
    request = materialize_request(compile_package(), "bootstrap-01", bindings(None))
    assert {t["TagKey"]: t["TagValue"] for t in request["Tags"]} == bindings().tags()
    with pytest.raises(BindingError, match="unresolved"):
        materialize_request(compile_package(), "bootstrap-02", bindings(None))


def test_role_policy_binds_both_key_service_paths_and_keeps_exact_policy():
    package = compile_package()
    result = materialize_request(package, "bootstrap-20", bindings())
    actual = json.loads(result["PolicyDocument"])
    old = json.loads(package["steps"][-1]["request"]["PolicyDocument"])
    for statement in old["Statement"]:
        if statement["Resource"] == "__VERIFIED_NEW_KMS_KEY_ARN__":
            statement["Resource"] = KEY
    assert actual == old
    assert sum(s["Resource"] == KEY for s in actual["Statement"]) == 2


@pytest.mark.parametrize(
    "field,value",
    [
        ("execution_id", "wrong"),
        ("execution_id", "../foreign"),
        ("key_arn", "alias/changebridge"),
        ("key_arn", KEY.replace(REGION, "us-east-1")),
        ("key_arn", KEY.replace(ACCOUNT, "000000000000")),
        ("alert_email", "different@example.test"),
        ("alert_email", "name <operator@example.test>"),
        ("alert_email", EMAIL + "\n"),
        ("approved_email_sha256", "0" * 64),
        ("prepared_at_utc", "2026-10-07T00:00:00"),
        ("expires_at_utc", "2026-10-09T00:00:01Z"),
        ("expires_at_utc", "2026-10-07T00:00:00Z"),
        ("expires_at_utc", "2026-10-07T00:00:00+05:30"),
    ],
)
def test_changed_or_unsafe_bindings_rejected(field, value):
    with pytest.raises(BindingError):
        materialize_request(
            compile_package(), "bootstrap-01", replace(bindings(), **{field: value})
        )


def test_request_is_detached_and_drifted_package_is_rejected():
    package = compile_package()
    request = materialize_request(package, "bootstrap-01", bindings())
    request["Tags"][0]["TagValue"] = "foreign"
    assert package == compile_package()
    assert (
        materialize_request(package, "bootstrap-01", bindings())["Tags"][0]["TagValue"]
        == "ChangeBridge"
    )
    changed = copy.deepcopy(package)
    changed["steps"][0]["request"]["MultiRegion"] = True
    with pytest.raises(BindingError, match="authority"):
        materialize_request(changed, "bootstrap-01", bindings())
    with pytest.raises(BindingError):
        materialize_request(package, "bootstrap-99", bindings())


def test_expiry_and_creation_are_rechecked_without_inferring_creation_from_preparation():
    b = bindings()
    b.validate_time(datetime(2026, 10, 7, 1, tzinfo=UTC), "2026-10-07T00:01:00Z")
    for stamp in [
        datetime(2026, 10, 6, tzinfo=UTC),
        datetime(2026, 10, 8, tzinfo=UTC),
        datetime(2026, 10, 7, 1),
    ]:
        with pytest.raises(BindingError):
            b.validate_time(stamp)
    for created in [
        "2026-10-07T02:00:00Z",
        "2026-10-05T00:00:00Z",
        "2026-10-06T23:59:00Z",
    ]:
        with pytest.raises(BindingError):
            b.validate_time(datetime(2026, 10, 7, 1, tzinfo=UTC), created)


def test_private_endpoint_and_digest_are_not_in_dataclass_repr():
    assert EMAIL not in repr(bindings())
    assert bindings().approved_email_sha256 not in repr(bindings())
