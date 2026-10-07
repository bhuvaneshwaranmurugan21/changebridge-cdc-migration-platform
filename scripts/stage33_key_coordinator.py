"""Durable, exact-identity KMS readback coordination; no writes, adoption or retry authority."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from scripts.prepare_stage33_bootstrap import ACCOUNT, REGION, canonical, compile_package, digest
from scripts.qualify_stage33_bootstrap import decode_response, validate_identity
from scripts.reconcile_stage33_key_attempt import inspect_key_attempt
from scripts.stage33_mutation_journal import MutationJournal

LABEL = "SCOPED_READ_INTENT_NOT_API_RESULT"
RESULT = "SCOPED_READ_RESULT_NOT_CONFIGURATION_PROOF"


class CoordinatorError(ValueError):
    """Unknown identity, transport outcome or control drift stops coordination."""


def bound_key(journal: MutationJournal) -> tuple[str, dict[str, Any]]:
    """Derive one physical key exclusively from the original durable acknowledgement.

    This is an identity selector, not API provenance certification. A missing acknowledgement
    cannot be repaired by searching for names/tags or by accepting caller-provided key IDs.
    """
    if journal.package != compile_package() or journal._load() != journal.rows:
        raise CoordinatorError("source authority or durable journal changed")
    if journal._pending() != journal.pending:
        raise CoordinatorError("cached pending attempt differs from durable state")
    if journal.pending is None or journal.pending["step_id"] != "bootstrap-01":
        raise CoordinatorError("one unresolved first-key attempt required")
    if journal.creation_tags is None:
        raise CoordinatorError("original concrete creation tags required")
    acks = [row for row in journal.rows if row["kind"] == "ACKNOWLEDGEMENT"]
    if len(acks) != 1 or acks[0]["payload"]["returncode"] != 0:
        raise CoordinatorError("missing/nonzero creation acknowledgement; no identity inference")
    try:
        response = decode_response(bytes.fromhex(acks[0]["payload"]["stdout"]["hex"]))
        metadata = response["KeyMetadata"]
        key_id = metadata["KeyId"]
        arn = metadata["Arn"]
        if (
            not isinstance(key_id, str)
            or not re.fullmatch(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}", key_id)
            or arn != f"arn:aws:kms:{REGION}:{ACCOUNT}:key/{key_id}"
            or metadata.get("AWSAccountId") != ACCOUNT
        ):
            raise CoordinatorError("creation acknowledgement lacks exact physical identity")
    except (KeyError, TypeError, ValueError) as error:
        raise CoordinatorError("ambiguous creation identity; preserve without retry") from error
    return arn, metadata


def command_for(
    executable: str, key_arn: str, service: str, operation: str, request: dict[str, Any]
) -> list[str]:
    pattern = (
        rf"arn:aws:kms:{REGION}:{ACCOUNT}:key/"
        r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}"
    )
    if not re.fullmatch(pattern, key_arn):
        raise CoordinatorError("physical key selector outside exact account/region")
    allowed = {
        ("sts", "get-caller-identity"): {},
        ("kms", "describe-key"): {"KeyId": key_arn},
        ("kms", "get-key-policy"): {"KeyId": key_arn, "PolicyName": "default"},
        ("kms", "list-resource-tags"): {"KeyId": key_arn, "Limit": 50},
    }
    if (service, operation) not in allowed or request != allowed[service, operation]:
        raise CoordinatorError("request outside exact acknowledged-key readback scope")
    endpoint = f"https://{service}.{REGION}.amazonaws.com"
    return [
        executable,
        service,
        operation,
        "--cli-input-json",
        "file:///dev/stdin",
        "--region",
        REGION,
        "--endpoint-url",
        endpoint,
        "--output",
        "json",
        "--no-cli-pager",
        "--no-cli-auto-prompt",
        "--no-paginate",
        "--cli-connect-timeout",
        "10",
        "--cli-read-timeout",
        "30",
    ]


class KeyReadbackCoordinator:
    """Journal every scoped read before invocation; an interrupted read requires explicit resume.

    The local journal does not authenticate AWS response bytes cryptographically. Execution
    requires a trusted administrator environment/CLI and actual AWS identity and controls.
    This read-only coordinator cannot clear the mutation or authorize a dependent request.
    """

    def __init__(self, journal: MutationJournal, resume_unknown_reads: bool = False) -> None:
        self.journal = journal
        self.key_arn, _ = bound_key(journal)
        self.identity_qualified = False
        self.source_head = journal.rows[-1]["sha256"]
        self._check_read_history(resume_unknown_reads)
        self.aws = shutil.which("aws")
        if self.aws is None:
            raise CoordinatorError("AWS CLI unavailable; no AWS operation attempted")

    def _check_read_history(self, resume: bool) -> None:
        try:
            self._inspect_read_history(resume)
        except CoordinatorError:
            raise
        except (KeyError, TypeError, ValueError) as error:
            raise CoordinatorError(
                "malformed scoped read history; no transport or retry"
            ) from error

    def _inspect_read_history(self, resume: bool) -> None:
        pending = None
        failed = None
        for row in self.journal.rows:
            if row["kind"] != "OBSERVATION":
                continue
            try:
                observation = decode_response(bytes.fromhex(row["payload"]["stdout"]["hex"]))
            except ValueError:
                continue  # Older raw observations remain preserved; never infer read completion.
            label = observation.get("label")
            if label == LABEL:
                if pending is not None or failed is not None:
                    raise CoordinatorError("overlapping scoped reads")
                if (
                    set(observation)
                    != {
                        "label",
                        "service",
                        "operation",
                        "request",
                        "request_sha256",
                        "mutation_retry_authorized",
                    }
                    or observation["mutation_retry_authorized"] is not False
                    or observation["request_sha256"] != digest(observation["request"])
                ):
                    raise CoordinatorError("malformed scoped read intent")
                command_for(
                    "aws",
                    self.key_arn,
                    observation["service"],
                    observation["operation"],
                    observation["request"],
                )
                pending = row["sha256"]
            elif label == RESULT:
                if pending is None or observation.get("intent_record_sha256") != pending:
                    raise CoordinatorError("scoped read result lacks matching durable intent")
                if (
                    set(observation)
                    != {
                        "label",
                        "intent_record_sha256",
                        "returncode",
                        "stdout",
                        "stderr",
                        "configuration_verified",
                    }
                    or type(observation["returncode"]) is not int
                    or observation["configuration_verified"] is not False
                ):
                    raise CoordinatorError("malformed scoped read result")
                for name in ("stdout", "stderr"):
                    value = observation[name]
                    if (
                        not isinstance(value, dict)
                        or set(value) != {"hex", "sha256"}
                        or hashlib.sha256(bytes.fromhex(value["hex"])).hexdigest()
                        != value["sha256"]
                    ):
                        raise CoordinatorError("scoped raw receipt mismatch")
                if observation["returncode"] != 0:
                    failed = pending
                else:
                    try:
                        decode_response(bytes.fromhex(observation["stdout"]["hex"]))
                    except ValueError:
                        failed = pending
                pending = None
            elif label == "EXPLICIT_UNKNOWN_READ_PRESERVED":
                unknown = pending or failed
                if (
                    unknown is None
                    or observation.get("intent_record_sha256") != unknown
                    or set(observation)
                    != {"label", "intent_record_sha256", "mutation_retry_authorized"}
                    or observation["mutation_retry_authorized"] is not False
                ):
                    raise CoordinatorError("unknown-read preservation identity mismatch")
                pending = None
                failed = None
        unknown = pending or failed
        if unknown is not None:
            if not resume:
                raise CoordinatorError(
                    "interrupted/failed read; explicit read-only resume required"
                )
            self.journal.observe(
                "bootstrap-01",
                canonical(
                    {
                        "label": "EXPLICIT_UNKNOWN_READ_PRESERVED",
                        "intent_record_sha256": unknown,
                        "mutation_retry_authorized": False,
                    }
                ),
                b"",
            )

    def read(self, service: str, operation: str, request: dict[str, Any]) -> dict[str, Any]:
        # Recheck source and exact creation identity before every API call, not only startup.
        arn, _ = bound_key(self.journal)
        if arn != self.key_arn:
            raise CoordinatorError("physical key identity changed")
        self._check_read_history(False)
        command = command_for(str(self.aws), arn, service, operation, request)
        if service != "sts" and not self.identity_qualified:
            raise CoordinatorError(
                "fresh qualified administrator identity required before key reads"
            )
        self.journal.observe(
            "bootstrap-01",
            canonical(
                {
                    "label": LABEL,
                    "service": service,
                    "operation": operation,
                    "request": request,
                    "request_sha256": digest(request),
                    "mutation_retry_authorized": False,
                }
            ),
            b"",
        )
        intent = self.journal.rows[-1]["sha256"]
        environment = {k: v for k, v in os.environ.items() if not k.startswith("AWS_ENDPOINT_URL")}
        environment.update(
            {
                "AWS_REGION": REGION,
                "AWS_DEFAULT_REGION": REGION,
                "AWS_EC2_METADATA_DISABLED": "true",
                "AWS_MAX_ATTEMPTS": "1",
                "AWS_RETRY_MODE": "standard",
                "AWS_PAGER": "",
            }
        )
        try:
            result = subprocess.run(
                command,
                input=canonical(request),
                capture_output=True,
                env=environment,
                timeout=60,
                check=False,
            )
            code, stdout, stderr = result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired as error:
            code, stdout, stderr = 124, error.stdout or b"", error.stderr or b"timeout"
        except OSError as error:
            code, stdout, stderr = 127, b"", str(error).encode()
        self.journal.observe(
            "bootstrap-01",
            canonical(
                {
                    "label": RESULT,
                    "intent_record_sha256": intent,
                    "returncode": code,
                    "stdout": MutationJournal._raw(stdout),
                    "stderr": MutationJournal._raw(stderr),
                    "configuration_verified": False,
                }
            ),
            b"",
        )
        if code != 0:
            raise CoordinatorError("actual read failed; raw error preserved, no automatic retry")
        try:
            response = decode_response(stdout)
            if service == "sts":
                self.identity_qualified = False
                validate_identity(response)
                self.identity_qualified = True
            return response
        except ValueError as error:
            raise CoordinatorError("ambiguous actual read response; preserve and stop") from error

    def reconcile(self) -> dict[str, Any]:
        validate_identity(self.read("sts", "get-caller-identity", {}))
        snapshots = {}
        for phase in ("before", "after"):
            snapshots[phase] = {
                "metadata": self.read("kms", "describe-key", {"KeyId": self.key_arn}),
                "policy": self.read(
                    "kms", "get-key-policy", {"KeyId": self.key_arn, "PolicyName": "default"}
                ),
                "tags": self.read(
                    "kms", "list-resource-tags", {"KeyId": self.key_arn, "Limit": 50}
                ),
            }
        validate_identity(self.read("sts", "get-caller-identity", {}))
        result = inspect_key_attempt(self.journal, snapshots, self.journal.creation_tags or {})
        return {
            "label": "SCOPED_KMS_READBACK_NOT_COMPLETE_BOOTSTRAP_ADMISSION",
            "package_sha256": self.journal.bound_package_sha256,
            "execution_id": self.journal.bound_execution_id,
            "starting_record_sha256": self.source_head,
            "ending_record_sha256": self.journal.rows[-1]["sha256"],
            "comparison_sha256": result["comparison_sha256"],
            "aws_writes": 0,
            "mutation_pending": True,
            "key_use_authorized": False,
            "retry_authorized": False,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--journal-directory", required=True, type=Path)
    parser.add_argument("--execution-id", required=True)
    parser.add_argument("--creation-tags", required=True, type=Path)
    parser.add_argument("--resume-unknown-reads", action="store_true")
    args = parser.parse_args()
    os.umask(0o077)
    try:
        package = compile_package()
        if package["working_tree_dirty"]:
            raise CoordinatorError("clean published source required before actual readback")
        # Reuse the exporter's strict private-file reader; no raw file content enters the terminal.
        from scripts.export_stage33_evidence import _read

        tags = decode_response(_read(args.creation_tags))
        with MutationJournal(args.journal_directory, package, args.execution_id, tags) as journal:
            result = KeyReadbackCoordinator(journal, args.resume_unknown_reads).reconcile()
        print(json.dumps(result, sort_keys=True))
    except (OSError, ValueError) as error:
        print(
            json.dumps(
                {
                    "result": "BLOCKED",
                    "error_type": type(error).__name__,
                    "aws_writes": 0,
                    "mutation_retry_authorized": False,
                }
            )
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
