"""Private, durable bootstrap request journal. Local integrity is not AWS execution proof."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import stat
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.prepare_stage33_bootstrap import canonical

READ_OPERATIONS = frozenset({
    ("sts", "get-caller-identity"),
    ("iam", "get-role"), ("iam", "list-role-policies"),
    ("iam", "list-attached-role-policies"),
    ("iam", "get-open-id-connect-provider"),
    ("s3api", "head-bucket"), ("dynamodb", "describe-table"),
    ("kms", "describe-key"), ("sns", "get-topic-attributes"),
})
ABSENCE_CODES = {
    ("iam", "get-role"): {"NoSuchEntity"},
    ("s3api", "head-bucket"): {"404", "NoSuchBucket"},
    ("dynamodb", "describe-table"): {"ResourceNotFoundException"},
    ("kms", "describe-key"): {"NotFoundException"},
    ("sns", "get-topic-attributes"): {"NotFound"},
}


class JournalError(ValueError):
    """An unsafe or ambiguous journal cannot authorize another operation."""


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class BootstrapJournal:
    """Journal allowlisted qualification reads; mutation/reconciliation execution stays disabled."""

    def __init__(self, directory: Path, package: dict[str, Any]) -> None:
        self.directory = directory
        self.package = package
        self.entries: list[dict[str, Any]] = []
        self.fd: int | None = None
        self.lock_fd: int | None = None
        self.directory_fd: int | None = None
        with suppress(FileExistsError):
            directory.mkdir(mode=0o700)
        info = directory.lstat()
        if (
            not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o700
        ):
            raise JournalError("private journal directory ownership/mode required")
        flags = os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW
        try:
            self.directory_fd = os.open(
                directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            )
            anchored = os.fstat(self.directory_fd)
            if (anchored.st_dev, anchored.st_ino) != (info.st_dev, info.st_ino):
                raise JournalError("journal directory identity changed")
            self.lock_fd = os.open("writer.lock", flags, 0o600, dir_fd=self.directory_fd)
            self._check_fd(self.lock_fd)
            fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            package_path = directory / "package.json"
            try:
                os.stat("package.json", dir_fd=self.directory_fd, follow_symlinks=False)
                package_exists = True
            except FileNotFoundError:
                package_exists = False
            if package_exists:
                if self._read_private(package_path) != canonical(package):
                    raise JournalError("journal belongs to a different package")
            else:
                self._write_private(package_path, canonical(package))
            self.fd = os.open(
                "journal.jsonl", flags | os.O_APPEND, 0o600, dir_fd=self.directory_fd
            )
            self._check_fd(self.fd)
            self._load()
            if not self.entries:
                self.append("OPEN", {"package_sha256": package["package_sha256"]})
        except BaseException:
            self.close()
            raise

    @staticmethod
    def _check_fd(fd: int) -> None:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1
        ):
            raise JournalError("private single-link regular file required")

    def _read_private(self, path: Path) -> bytes:
        if path.parent != self.directory or self.directory_fd is None:
            raise JournalError("receipt outside anchored journal directory")
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=self.directory_fd)
        try:
            self._check_fd(fd)
            with os.fdopen(fd, "rb", closefd=False) as stream:
                return stream.read()
        finally:
            os.close(fd)

    def _write_private(self, path: Path, data: bytes) -> None:
        if path.parent != self.directory or self.directory_fd is None:
            raise JournalError("receipt outside anchored journal directory")
        fd = os.open(
            path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600, dir_fd=self.directory_fd,
        )
        try:
            with os.fdopen(fd, "wb", closefd=False) as stream:
                stream.write(data)
                stream.flush()
                os.fsync(fd)
        finally:
            os.close(fd)
        os.fsync(self.directory_fd)

    def _load(self) -> None:
        if self.fd is None:
            raise JournalError("journal is closed")
        os.lseek(self.fd, 0, os.SEEK_SET)
        with os.fdopen(os.dup(self.fd), "rb") as stream:
            raw = stream.read()
        if raw and not raw.endswith(b"\n"):
            raise JournalError("torn journal tail; preserve and reconcile, never truncate")
        previous: str | None = None
        pending: dict[str, Any] | None = None
        for index, line in enumerate(raw.splitlines(), start=1):
            try:
                row = json.loads(line)
                if not isinstance(row, dict) or canonical(row) != line + b"\n":
                    raise JournalError("journal entry is not exact canonical JSON")
                claimed = row.pop("sha256")
                if (
                    row["sequence"] != index or row["previous_sha256"] != previous
                    or sha(canonical(row)) != claimed
                    or row["package_sha256"] != self.package["package_sha256"]
                ):
                    raise JournalError("journal hash chain or package binding mismatch")
                kind = row["kind"]
                payload = row["payload"]
                if index == 1 and kind != "OPEN":
                    raise JournalError("missing journal opening")
                if kind == "INTENT":
                    if pending is not None:
                        raise JournalError("overlapping unresolved intents")
                    if (payload["service"], payload["operation"]) not in READ_OPERATIONS:
                        raise JournalError("mutation or unqualified read in qualification journal")
                    if payload["request_sha256"] != sha(canonical(payload["request"])):
                        raise JournalError("request digest mismatch")
                    pending = payload
                elif kind == "RESULT":
                    if pending is None or payload["intent_id"] != pending["intent_id"]:
                        raise JournalError("result has no matching intent")
                    for field in ("stdout", "stderr"):
                        filename = payload[field]["file"]
                        if filename != f"{pending['intent_id']}.{field}":
                            raise JournalError("receipt path escaped the exact intent")
                        actual_digest = sha(self._read_private(self.directory / filename))
                        if actual_digest != payload[field]["sha256"]:
                            raise JournalError("receipt digest mismatch")
                    # Failed/missing read acknowledgements are retained, never inferred as absence.
                    if payload["returncode"] == 0:
                        pending = None
                elif kind == "ABSENCE_OBSERVED":
                    if pending is None:
                        raise JournalError("absence has no matching failed read")
                    self._validate_absence(pending, self.entries[-1], payload)
                    pending = None
                elif kind == "READ_OUTCOME_UNRESOLVED":
                    if pending is None or payload != {
                        "intent_id": pending["intent_id"],
                        "absence_proven": False, "configuration_proven": False,
                        "reobserve_read_only": True,
                    }:
                        raise JournalError("unresolved read preservation mismatch")
                    pending = None
                elif kind == "READBACK_RECONCILED":
                    raise JournalError("mutation recovery is not implemented; cannot accept a flag")
                elif kind != "OPEN" or index != 1:
                    raise JournalError("unknown journal state transition")
                row["sha256"] = claimed
                self.entries.append(row)
                previous = claimed
            except (KeyError, TypeError, json.JSONDecodeError) as error:
                raise JournalError("malformed journal entry") from error
        self.pending = pending

    def append(self, kind: str, payload: dict[str, Any]) -> str:
        if self.fd is None:
            raise JournalError("journal closed")
        row = {
            "sequence": len(self.entries) + 1,
            "previous_sha256": self.entries[-1]["sha256"] if self.entries else None,
            "package_sha256": self.package["package_sha256"],
            "at_utc": datetime.now(UTC).isoformat(), "kind": kind, "payload": payload,
        }
        row["sha256"] = sha(canonical(row))
        data = canonical(row)
        written = 0
        while written < len(data):
            count = os.write(self.fd, data[written:])
            if count == 0:
                raise JournalError("journal write made no progress")
            written += count
        os.fsync(self.fd)
        self.entries.append(row)
        return str(row["sha256"])

    def intent(self, service: str, operation: str, request: dict[str, Any]) -> str:
        if (service, operation) not in READ_OPERATIONS:
            raise JournalError("only bounded qualification reads may be journaled")
        if self.pending is not None:
            raise JournalError("unresolved operation; no automatic retry")
        identifier = f"request-{len(self.entries) + 1:06d}"
        payload = {
            "intent_id": identifier, "service": service, "operation": operation,
            "request": request, "request_sha256": sha(canonical(request)),
        }
        self.append("INTENT", payload)
        self.pending = payload
        return identifier

    def result(self, identifier: str, returncode: int, stdout: bytes, stderr: bytes) -> None:
        if self.pending is None or identifier != self.pending["intent_id"]:
            raise JournalError("result identity mismatch")
        payload: dict[str, Any] = {"intent_id": identifier, "returncode": returncode}
        for name, value in (("stdout", stdout), ("stderr", stderr)):
            filename = f"{identifier}.{name}"
            self._write_private(self.directory / filename, value)
            payload[name] = {"file": filename, "sha256": sha(value)}
        self.append("RESULT", payload)
        if returncode == 0:
            self.pending = None

    def _validate_absence(
        self, intent: dict[str, Any], result: dict[str, Any], payload: dict[str, Any]
    ) -> None:
        pair = (intent["service"], intent["operation"])
        if (
            result["kind"] != "RESULT" or result["payload"]["returncode"] == 0
            or result["payload"]["intent_id"] != intent["intent_id"]
            or payload["intent_id"] != intent["intent_id"]
            or payload["error_code"] not in ABSENCE_CODES.get(pair, set())
        ):
            raise JournalError("absence classification is not bound to an eligible failed read")
        stderr = self._read_private(
            self.directory / result["payload"]["stderr"]["file"]
        ).decode("utf-8", errors="strict")
        aws_operation = "".join(part.title() for part in intent["operation"].split("-"))
        match = re.search(
            r"An error occurred \(([^)]+)\) when calling the ([A-Za-z0-9]+) operation:",
            stderr,
        )
        if not match or match.groups() != (payload["error_code"], aws_operation):
            raise JournalError("generic or mismatched failure is not absence proof")

    def observe_absence(self, identifier: str, error_code: str) -> None:
        if self.pending is None:
            raise JournalError("absence requires a failed pending read")
        payload = {"intent_id": identifier, "error_code": error_code}
        self._validate_absence(self.pending, self.entries[-1], payload)
        self.append("ABSENCE_OBSERVED", payload)
        self.pending = None

    def preserve_unknown_read(self) -> None:
        """Explicitly allow new read-only observations while preserving the unknown old result."""
        if self.pending is None:
            raise JournalError("no unknown read to preserve")
        self.append("READ_OUTCOME_UNRESOLVED", {
            "intent_id": self.pending["intent_id"],
            "absence_proven": False, "configuration_proven": False,
            "reobserve_read_only": True,
        })
        self.pending = None

    def close(self) -> None:
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
        if self.lock_fd is not None:
            os.close(self.lock_fd)
            self.lock_fd = None
        if self.directory_fd is not None:
            os.close(self.directory_fd)
            self.directory_fd = None

    def __enter__(self) -> BootstrapJournal:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
