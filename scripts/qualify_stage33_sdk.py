"""Offline actual SDK model qualification. No AWS API invocation or infrastructure admission."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
from typing import Any

from scripts.prepare_stage33_bootstrap import REGION, canonical
from scripts.stage33_execution_bindings import ExecutionBindings
from scripts.stage33_lifecycle_authority import schedule
from scripts.stage33_lifecycle_store import get_request, put_request, runtime_profile

EXPECTED_WHEELS = {
    "boto3-1.43.108-py3-none-any.whl": (
        "19e9da95ef0c494e27052049a42137550e66730509bb613e76eaa30ddf9a7170"
    ),
    "botocore-1.43.108-py3-none-any.whl": (
        "ab9d16c6b4350aaa54ed28202dfa2998b2d735fdbf3247eb60af469d8d48a5b8"
    ),
    "jmespath-1.1.0-py3-none-any.whl": (
        "a5663118de4908c91729bea0acadca56526eb2698e83de10cd116ae0f4e97c64"
    ),
    "python_dateutil-2.9.0.post0-py2.py3-none-any.whl": (
        "a8b2bc7bffae282281c8140a97d3aa9c14da0b136dfe83f850eea9a5f7470427"
    ),
    "s3transfer-0.19.2-py3-none-any.whl": (
        "d8168eccca828cbb2cd573675333f3bddd254313a9c42494b84c76b539e8ba25"
    ),
    "six-1.17.0-py2.py3-none-any.whl": (
        "4721f391ed90541fddacab5acf947aa0d3dc7d27b2e1e8eda2be8970586c3274"
    ),
    "urllib3-2.8.0-py3-none-any.whl": (
        "0cf3cae568d36aa9576b28dfb35f11328f1cb974ca7647d9475ebb86c75ac6e3"
    ),
}


def verify_wheels(directory: Path) -> None:
    actual = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.glob("*.whl")}
    if actual != EXPECTED_WHEELS:
        raise ValueError("exact primary-PyPI wheel set/hash required")


def probe() -> dict[str, Any]:
    for key in list(os.environ):
        if key.startswith("AWS_"):
            del os.environ[key]
    os.environ.update(
        {
            "AWS_CONFIG_FILE": "/dev/null",
            "AWS_SHARED_CREDENTIALS_FILE": "/dev/null",
            "AWS_EC2_METADATA_DISABLED": "true",
            "BOTO_CONFIG": "/dev/null",
        }
    )
    boto3 = importlib.import_module("boto3")
    configuration = importlib.import_module("botocore.config").Config
    validation = importlib.import_module("botocore.validate").validate_parameters
    validation_error = importlib.import_module("botocore.exceptions").ParamValidationError
    session = boto3.Session(region_name=REGION)
    if session.get_credentials() is not None:
        raise ValueError("credential-free model probe required")
    client = session.client(
        "s3",
        endpoint_url=f"https://s3.{REGION}.amazonaws.com",
        verify=True,
        config=configuration(
            signature_version="s3v4",
            retries={"total_max_attempts": 1, "mode": "standard"},
            connect_timeout=5,
            read_timeout=10,
        ),
    )
    profile = runtime_profile(client)
    expected = "dc2dae37167575b343c9623a7aea7e46b11524402e3d78a536a6bb0cc717037e"
    if hashlib.sha256(canonical(profile)).hexdigest() != expected:
        raise ValueError("actual SDK/version/model drift")
    execution = "sdk-probe-20261007"
    key = f"executions/{execution}/head.json"
    requests = [
        ("GetObject", get_request(execution, key)),
        ("GetObject", get_request(execution, key, "explicit-version")),
        ("PutObject", put_request(execution, key, b"{}", None)),
        ("PutObject", put_request(execution, key, b"{}", "opaque-etag")),
    ]
    for operation, request in requests:
        validation(request, client.meta.service_model.operation_model(operation).input_shape)
    try:
        validation(
            {"UnsupportedField": True},
            client.meta.service_model.operation_model("PutObject").input_shape,
        )
    except validation_error:
        pass
    else:
        raise AssertionError("actual SDK did not reject unsupported input")
    mail = "offline@example.test"
    bindings = ExecutionBindings(
        execution,
        "2026-10-07T00:00:00Z",
        "2026-10-09T00:00:00Z",
        mail,
        hashlib.sha256(mail.encode()).hexdigest(),
    )
    scheduler = session._session.get_service_model("scheduler")
    validation(
        schedule(bindings, "2026-10-07T00:01:00Z"),
        scheduler.operation_model("CreateSchedule").input_shape,
    )
    dynamodb = session._session.get_service_model("dynamodb")
    validation(
        {
            "TableName": "changebridge-p3s3-tf-locks",
            "PointInTimeRecoverySpecification": {"PointInTimeRecoveryEnabled": False},
        },
        dynamodb.operation_model("UpdateContinuousBackups").input_shape,
    )
    return {
        "label": "LOCAL_SDK_MODEL_QUALIFIED_NOT_MANAGED_RUNTIME_ADMISSION",
        "result": "PASS",
        "profile_sha256": expected,
        "request_shapes_validated": 6,
        "unsupported_request_rejected": True,
        "aws_api_calls": 0,
        "aws_mutations": 0,
        "credential_resolution": "NONE",
        "managed_runtime_qualified": False,
        "deployment_authorized": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheels", type=Path, required=True)
    parser.add_argument("--verify-only", action="store_true")
    arguments = parser.parse_args()
    verify_wheels(arguments.wheels)
    if arguments.verify_only:
        print("EXACT_WHEEL_CHECKSUM_SET_VERIFIED_NOT_RUNTIME_ADMISSION")
    else:
        print(json.dumps(probe(), sort_keys=True))


if __name__ == "__main__":
    main()
