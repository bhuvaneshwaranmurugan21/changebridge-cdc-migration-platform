"""Fresh bounded administrator/collision qualification. Never create or modify AWS resources."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.prepare_stage33_bootstrap import (
    ACCOUNT,
    ARTIFACT,
    LOCKS,
    REGION,
    ROLE,
    STATE,
    TOPIC,
    canonical,
    compile_package,
)
from scripts.stage33_bootstrap_journal import ABSENCE_CODES, BootstrapJournal, JournalError
from scripts.validate_part3_stage3 import ROOT
from scripts.validate_stage33_access_evidence import validate_diagnostic

PROVIDER = f"arn:aws:iam::{ACCOUNT}:oidc-provider/token.actions.githubusercontent.com"
OLD_ROLE = "ChangeBridgeGitHubOidcRole"
ENDPOINTS = {
    "sts": f"https://sts.{REGION}.amazonaws.com",
    "iam": "https://iam.amazonaws.com",
    "s3api": f"https://s3.{REGION}.amazonaws.com",
    "dynamodb": f"https://dynamodb.{REGION}.amazonaws.com",
    "kms": f"https://kms.{REGION}.amazonaws.com",
    "sns": f"https://sns.{REGION}.amazonaws.com",
}


class QualificationError(ValueError):
    """Fresh actual evidence did not qualify the bounded bootstrap."""


def allowed_request(service: str, operation: str, request: dict[str, Any]) -> bool:
    """Permit only exact own-identity, provider and named-bootstrap collision reads."""
    pair = service, operation
    if pair == ("sts", "get-caller-identity"):
        return request == {}
    if service == "iam" and operation in {
        "get-role", "list-role-policies", "list-attached-role-policies"
    }:
        return request in [{"RoleName": OLD_ROLE}, {"RoleName": ROLE}]
    if pair == ("iam", "get-role-policy"):
        return request == {"RoleName": ROLE, "PolicyName": "ChangeBridgeStage33Backend"}
    if pair == ("iam", "get-open-id-connect-provider"):
        return request == {"OpenIDConnectProviderArn": PROVIDER}
    if pair == ("s3api", "head-bucket"):
        return request in [
            {"Bucket": bucket, "ExpectedBucketOwner": ACCOUNT} for bucket in (STATE, ARTIFACT)
        ]
    if pair == ("dynamodb", "describe-table"):
        return request == {"TableName": LOCKS}
    if pair == ("kms", "describe-key"):
        return request == {"KeyId": f"arn:aws:kms:{REGION}:{ACCOUNT}:alias/changebridge-p3s3-state"}
    if pair == ("sns", "get-topic-attributes"):
        return request == {"TopicArn": TOPIC}
    return False


def command_for(
    executable: str, service: str, operation: str, request: dict[str, Any]
) -> list[str]:
    if not allowed_request(service, operation, request):
        raise QualificationError("read outside exact ChangeBridge qualification scope")
    command = [
        executable, service, operation, "--cli-input-json", "file:///dev/stdin",
        "--region", REGION, "--endpoint-url", ENDPOINTS[service],
        "--output", "json", "--no-cli-pager", "--no-cli-auto-prompt",
        "--cli-connect-timeout", "10", "--cli-read-timeout", "30",
    ]
    if service == "iam" and operation in {"list-role-policies", "list-attached-role-policies"}:
        command.append("--no-paginate")
    return command


def complete_empty_inventory(response: dict[str, Any] | None, field: str) -> None:
    if (response is None or response.get(field) != []
            or response.get("IsTruncated") is not False
            or "Marker" in response or "NextToken" in response):
        raise QualificationError("existing role policy inventory is incomplete or drifted")


def decode_response(raw: bytes) -> dict[str, Any]:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise QualificationError("duplicate JSON response key")
            result[key] = value
        return result

    def invalid_constant(value: str) -> Any:
        raise QualificationError("non-JSON numeric constant: " + value)

    payload = json.loads(raw, object_pairs_hook=unique, parse_constant=invalid_constant)
    if not isinstance(payload, dict):
        raise QualificationError("AWS read did not return a JSON object")
    return payload


class AwsReader:
    """Use AWS CLI with exact endpoints, no shell, no retries and private durable receipts."""

    def __init__(self, journal: BootstrapJournal) -> None:
        self.journal = journal
        self.aws = shutil.which("aws")
        if self.aws is None:
            raise QualificationError("AWS CLI is unavailable; no AWS operation attempted")

    def read(self, service: str, operation: str, request: dict[str, Any]) -> dict[str, Any] | None:
        command = command_for(str(self.aws), service, operation, request)
        identifier = self.journal.intent(service, operation, request)
        environment = {
            key: value for key, value in os.environ.items()
            if not key.startswith("AWS_ENDPOINT_URL")
        }
        environment.update({
            "AWS_REGION": REGION, "AWS_DEFAULT_REGION": REGION,
            "AWS_EC2_METADATA_DISABLED": "true", "AWS_MAX_ATTEMPTS": "1",
            "AWS_RETRY_MODE": "standard", "AWS_PAGER": "",
        })
        try:
            result = subprocess.run(
                command,
                input=canonical(request), capture_output=True, env=environment,
                timeout=60, check=False,
            )
        except subprocess.TimeoutExpired as error:
            self.journal.result(identifier, 124, error.stdout or b"", error.stderr or b"timeout")
            raise QualificationError("read timed out; receipt preserved, no retry") from error
        except OSError as error:
            self.journal.result(identifier, 127, b"", str(error).encode())
            raise QualificationError("read could not start; intent preserved") from error
        self.journal.result(identifier, result.returncode, result.stdout, result.stderr)
        if result.returncode != 0:
            match = re.search(rb"An error occurred \(([^)]+)\) when calling", result.stderr)
            code = match.group(1).decode() if match else "UNCLASSIFIED"
            if code in ABSENCE_CODES.get((service, operation), set()):
                self.journal.observe_absence(identifier, code)
                return None
            raise QualificationError("AWS read failed; denial/unknown error is not absence")
        return decode_response(result.stdout or b"{}")


def validate_identity(payload: dict[str, Any] | None) -> None:
    if (
        payload is None or payload.get("Account") != ACCOUNT
        or not re.fullmatch(
            rf"arn:aws:sts::{ACCOUNT}:assumed-role/AccountFullAccessRole/[^/\s]+",
            str(payload.get("Arn", "")),
        )
    ):
        raise QualificationError(
            "unexpected administrator identity; stop before other reads"
        )


def _tags(value: Any) -> dict[str, str]:
    if not isinstance(value, list):
        raise QualificationError("provider tags are malformed")
    result: dict[str, str] = {}
    for row in value:
        if (
            not isinstance(row, dict) or set(row) != {"Key", "Value"}
            or not isinstance(row["Key"], str) or not isinstance(row["Value"], str)
            or row["Key"] in result
        ):
            raise QualificationError("provider tags are malformed or duplicated")
        result[row["Key"]] = row["Value"]
    return result


def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise QualificationError("provider creation timestamp is malformed")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise QualificationError("provider creation timestamp is malformed") from error
    if parsed.tzinfo is None:
        raise QualificationError("provider creation timestamp has no timezone")
    return parsed.astimezone(UTC)


def validate_provider(payload: dict[str, Any] | None, accepted: dict[str, Any]) -> None:
    if payload is None:
        raise QualificationError("exact provider controls drifted from accepted diagnostic")
    try:
        matches = (
            all(payload.get(field) == accepted.get(field)
                for field in ("Url", "ClientIDList", "ThumbprintList"))
            and _timestamp(payload.get("CreateDate")) == _timestamp(accepted.get("CreateDate"))
            and _tags(payload.get("Tags")) == _tags(accepted.get("Tags"))
        )
    except QualificationError as error:
        raise QualificationError("exact provider controls drifted or malformed") from error
    if not matches:
        raise QualificationError("exact provider controls drifted from accepted diagnostic")


def validate_old_role(payload: dict[str, Any] | None, accepted: dict[str, Any]) -> None:
    if payload is None or not isinstance(payload.get("Role"), dict) or any(
        payload["Role"].get(field) != accepted.get(field)
        for field in ("Arn", "RoleId", "MaxSessionDuration",
                      "PermissionsBoundary", "AssumeRolePolicyDocument")
    ):
        raise QualificationError("existing ChangeBridge role identity or controls drifted")


def qualify(journal: BootstrapJournal) -> dict[str, Any]:
    """Repeat exact security reads before/after collisions; no quota or cleanup claim."""
    accepted = json.loads((ROOT / "evidence/part3/stage3/administrator-access-diagnostic.json")
                          .read_text())
    validate_diagnostic(accepted)
    reader = AwsReader(journal)
    start_index = len(journal.entries)
    validate_identity(reader.read("sts", "get-caller-identity", {}))
    validate_provider(reader.read("iam", "get-open-id-connect-provider", {
        "OpenIDConnectProviderArn": PROVIDER,
    }), accepted["oidc_provider"])
    validate_old_role(reader.read("iam", "get-role", {"RoleName": OLD_ROLE}), accepted["role"])
    for operation, field in (("list-role-policies", "PolicyNames"),
                             ("list-attached-role-policies", "AttachedPolicies")):
        response = reader.read("iam", operation, {"RoleName": OLD_ROLE})
        complete_empty_inventory(response, field)
    collisions = [
        ("iam", "get-role", {"RoleName": ROLE}),
        *( ("s3api", "head-bucket", {"Bucket": bucket, "ExpectedBucketOwner": ACCOUNT})
           for bucket in (STATE, ARTIFACT)),
        ("dynamodb", "describe-table", {"TableName": LOCKS}),
        ("kms", "describe-key", {
            "KeyId": f"arn:aws:kms:{REGION}:{ACCOUNT}:alias/changebridge-p3s3-state",
        }),
        ("sns", "get-topic-attributes", {"TopicArn": TOPIC}),
    ]
    for service, operation, request in collisions:
        if reader.read(service, operation, request) is not None:
            raise QualificationError("named resource exists; no automatic adoption or overwrite")
    validate_old_role(reader.read("iam", "get-role", {"RoleName": OLD_ROLE}), accepted["role"])
    for operation, field in (("list-role-policies", "PolicyNames"),
                             ("list-attached-role-policies", "AttachedPolicies")):
        response = reader.read("iam", operation, {"RoleName": OLD_ROLE})
        complete_empty_inventory(response, field)
    validate_provider(reader.read("iam", "get-open-id-connect-provider", {
        "OpenIDConnectProviderArn": PROVIDER,
    }), accepted["oidc_provider"])
    validate_identity(reader.read("sts", "get-caller-identity", {}))
    return {
        "label": "FRESH_SECURITY_AND_COLLISION_OBSERVATION_NOT_BOOTSTRAP_ADMISSION",
        "result": "OBSERVED", "aws_writes": 0, "bootstrap_ready": False,
        "quota_headroom_proven": False, "cleanup_executor_proven": False,
        "observation_started_at_utc": journal.entries[start_index]["at_utc"],
        "observation_finished_at_utc": journal.entries[-1]["at_utc"],
        "journal_head_sha256": journal.entries[-1]["sha256"],
        "limitation": "matching before/after reads do not form an atomic IAM snapshot",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--journal-directory", type=Path, required=True)
    parser.add_argument("--resume-read-only", action="store_true")
    args = parser.parse_args()
    os.umask(0o077)
    try:
        package = compile_package()
        if package["working_tree_dirty"]:
            raise QualificationError(
                "publish/verify clean source before AWS qualification"
            )
        with BootstrapJournal(args.journal_directory, package) as journal:
            if journal.pending is not None and args.resume_read_only:
                journal.preserve_unknown_read()
            result = qualify(journal)
        print(json.dumps(result, sort_keys=True))
    except (QualificationError, JournalError, ValueError, OSError) as error:
        print(json.dumps({"result": "BLOCKED", "aws_writes": 0, "reason": str(error)}))
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
