"""Conditional evidence objects and durable local reference storage; not AWS admission proof."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import sqlite3
import stat
import uuid
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from scripts.prepare_stage33_bootstrap import ACCOUNT, canonical
from scripts.stage33_lifecycle_authority import EVIDENCE, prefix
from scripts.validate_part3_stage3 import ROOT

MAX_BYTES = 16 * 1024 * 1024


class StoreError(ValueError):
    """Unknown, changed or unsafe evidence objects remain blocked."""


class Conflict(StoreError):
    """A conditional write did not own the expected version."""


def record_bytes(value: Any) -> bytes:
    try:
        json.dumps(value, allow_nan=False)
        return canonical(value)
    except (ValueError, TypeError) as error:
        raise StoreError("finite interoperable JSON evidence required") from error


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class Object:
    body: bytes
    token: str
    version_id: str

    def validate(self) -> None:
        if not isinstance(self.body, bytes) or len(self.body) > MAX_BYTES:
            raise StoreError("bounded exact object bytes required")
        if (
            not isinstance(self.token, str)
            or not self.token
            or not isinstance(self.version_id, str)
            or not self.version_id
            or self.version_id == "null"
        ):
            raise StoreError("immutable version identity and opaque conditional token required")


class ObjectStore(Protocol):
    def get(self, key: str) -> Object | None: ...
    def put(self, key: str, body: bytes, expected: str | None) -> Object: ...


def check_key(execution_id: str, key: str, write: bool = False) -> None:
    root = prefix(execution_id)
    if (
        not isinstance(key, str)
        or not key.startswith(root)
        or len(key) > 1024
        or not re.fullmatch(r"[a-z0-9][a-z0-9._/-]*", key)
        or any(x in {"", ".", ".."} for x in key.split("/"))
    ):
        raise StoreError("object outside exact execution prefix")
    suffix = key[len(root) :]
    if suffix != "head.json" and not any(
        suffix.startswith(x) for x in ("authority/", "events/", "exports/")
    ):
        raise StoreError("unknown evidence class")
    if write and suffix.startswith("authority/"):
        raise StoreError("controller cannot write its own authority")


def put_request(execution_id: str, key: str, body: bytes, expected: str | None) -> dict[str, Any]:
    check_key(execution_id, key, True)
    if not isinstance(body, bytes) or not body or len(body) > MAX_BYTES:
        raise StoreError("bounded nonempty evidence required")
    if expected is not None and (
        not isinstance(expected, str) or not expected or key != prefix(execution_id) + "head.json"
    ):
        raise StoreError("only exact mutable head may use compare-and-set")
    request = {
        "Bucket": EVIDENCE,
        "ExpectedBucketOwner": ACCOUNT,
        "Key": key,
        "Body": body,
        "ServerSideEncryption": "AES256",
        "ContentType": "application/json",
        "ChecksumSHA256": base64.b64encode(hashlib.sha256(body).digest()).decode(),
    }
    request["IfNoneMatch" if expected is None else "IfMatch"] = (
        "*" if expected is None else expected
    )
    return request


def get_request(execution_id: str, key: str, version_id: str | None = None) -> dict[str, Any]:
    check_key(execution_id, key)
    result = {
        "Bucket": EVIDENCE,
        "ExpectedBucketOwner": ACCOUNT,
        "Key": key,
        "ChecksumMode": "ENABLED",
    }
    if version_id is not None:
        if not isinstance(version_id, str) or not version_id or version_id == "null":
            raise StoreError("exact version required")
        result["VersionId"] = version_id
    return result


class SQLiteObjectStore:
    """Real private transactional local reference, never a substitute for S3 qualification.

    Every successful CAS increments a stored revision, even if its payload returns to old bytes.
    Actual SQLite transactions exercise competing writers, restart and committed-byte recovery.
    The reference contains no target AWS resources or credentials.
    """

    schema = (
        "CREATE TABLE objects (key TEXT PRIMARY KEY, revision INTEGER NOT NULL, body BLOB NOT NULL)"
    )

    def __init__(self, directory: Path, execution_id: str) -> None:
        prefix(execution_id)
        self.execution_id = execution_id
        self.directory = directory.absolute()
        if self.directory.resolve().is_relative_to(ROOT.resolve()):
            raise StoreError("private evidence reference outside worktree required")
        self.directory.mkdir(mode=0o700, exist_ok=True)
        info = self.directory.lstat()
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o700
        ):
            raise StoreError("private owned directory required")
        self.fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        self.directory_identity = (info.st_dev, info.st_ino)
        if self.directory_identity != (os.fstat(self.fd).st_dev, os.fstat(self.fd).st_ino):
            self.close()
            raise StoreError("directory substitution")
        try:
            created = True
            try:
                db = os.open(
                    "objects.sqlite3",
                    os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=self.fd,
                )
            except FileExistsError:
                created = False
                db = os.open("objects.sqlite3", os.O_RDWR | os.O_NOFOLLOW, dir_fd=self.fd)
            try:
                checked = os.fstat(db)
                self._private(checked)
                self.database_identity = (checked.st_dev, checked.st_ino)
            finally:
                os.close(db)
            with closing(self._connection()) as connection:
                if created:
                    connection.execute(self.schema)
                else:
                    actual = connection.execute(
                        "SELECT type,name,sql FROM sqlite_master ORDER BY name"
                    ).fetchall()
                    expected = [
                        ("table", "objects", self.schema),
                        ("index", "sqlite_autoindex_objects_1", None),
                    ]
                    if actual != expected:
                        raise StoreError("unknown database schema")
                if connection.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                    raise StoreError("database integrity failed")
            os.fsync(self.fd)
        except BaseException:
            self.close()
            raise

    @staticmethod
    def _private(info: os.stat_result) -> None:
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_nlink != 1
        ):
            raise StoreError("private single-link regular file required")

    def _connection(self) -> sqlite3.Connection:
        if self.fd < 0:
            raise StoreError("closed storage")
        named = self.directory.lstat()
        if (
            not stat.S_ISDIR(named.st_mode)
            or (named.st_dev, named.st_ino) != self.directory_identity
        ):
            raise StoreError("directory changed")
        db = os.open("objects.sqlite3", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=self.fd)
        try:
            info = os.fstat(db)
            self._private(info)
            if (info.st_dev, info.st_ino) != self.database_identity:
                raise StoreError("database substituted")
        finally:
            os.close(db)
        for suffix in ("-journal", "-wal", "-shm"):
            try:
                sidecar = os.open(
                    "objects.sqlite3" + suffix, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=self.fd
                )
            except FileNotFoundError:
                continue
            try:
                self._private(os.fstat(sidecar))
                if suffix != "-journal":
                    raise StoreError("unexpected WAL sidecar")
            finally:
                os.close(sidecar)
        connection = sqlite3.connect(
            f"/proc/self/fd/{self.fd}/objects.sqlite3", timeout=1, isolation_level=None
        )
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    @staticmethod
    def _object(row: tuple[int, bytes]) -> Object:
        revision, body = row
        if type(revision) is not int or revision < 1 or not isinstance(body, bytes):
            raise StoreError("malformed stored object")
        value = Object(body, f"sqlite-revision-{revision}-{sha(body)}", str(revision))
        value.validate()
        return value

    def get(self, key: str) -> Object | None:
        check_key(self.execution_id, key)
        connection = self._connection()
        try:
            row = connection.execute(
                "SELECT revision,body FROM objects WHERE key=?", (key,)
            ).fetchone()
            return None if row is None else self._object(row)
        finally:
            connection.close()

    def put(self, key: str, body: bytes, expected: str | None) -> Object:
        put_request(self.execution_id, key, body, expected)  # Same supported conditional contract.
        connection = self._connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT revision,body FROM objects WHERE key=?", (key,)
            ).fetchone()
            if (row is None) != (expected is None) or (
                row is not None and self._object(row).token != expected
            ):
                raise Conflict("conditional object version changed")
            revision = 1 if row is None else row[0] + 1
            if row is None:
                connection.execute("INSERT INTO objects VALUES (?,?,?)", (key, revision, body))
            else:
                connection.execute(
                    "UPDATE objects SET revision=?,body=? WHERE key=?", (revision, body, key)
                )
            connection.execute("COMMIT")
            os.fsync(self.fd)
            return self._object((revision, body))
        except BaseException:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def close(self) -> None:
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1

    def __enter__(self) -> SQLiteObjectStore:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()


class EvidenceLog:
    """Immutable records then conditional head; commitment precedes any target dispatch.

    A head may commit despite a lost transport acknowledgement. Reconciliation reads the exact
    intended bytes, never retries a target operation. Unreferenced orphan records cannot authorize
    target dispatch. This class records evidence, not mutation permission or successful cleanup.
    """

    def __init__(self, store: ObjectStore, execution_id: str, package_sha256: str) -> None:
        self.store = store
        self.root = prefix(execution_id)
        self.execution_id = execution_id
        if not re.fullmatch(r"[0-9a-f]{64}", package_sha256):
            raise StoreError("exact package digest required")
        self.package_sha256 = package_sha256

    def load(self) -> tuple[list[dict[str, Any]], Object | None]:
        head = self.store.get(self.root + "head.json")
        if head is None:
            return [], None
        head.validate()
        try:
            value = json.loads(head.body)
            if (
                set(value)
                != {"sequence", "record_key", "record_sha256", "package_sha256", "execution_id"}
                or value["execution_id"] != self.execution_id
                or value["package_sha256"] != self.package_sha256
                or record_bytes(value) != head.body
            ):
                raise StoreError("head binding changed")
            rows = []
            total_bytes = 0
            sequence = value["sequence"]
            if type(sequence) is not int or not 1 <= sequence <= 512:
                raise StoreError("bounded exact journal sequence required")
            key = value["record_key"]
            expected = value["record_sha256"]
            while sequence:
                if key != self.root + f"events/{sequence:08d}-{expected}.json":
                    raise StoreError("record selector changed")
                saved = self.store.get(key)
                if saved is None:
                    raise StoreError("committed record missing")
                saved.validate()
                total_bytes += len(saved.body)
                if total_bytes > 32 * 1024 * 1024:
                    raise StoreError("bounded committed journal byte allowance exceeded")
                if sha(saved.body) != expected:
                    raise StoreError("committed record digest changed")
                row = json.loads(saved.body)
                if (
                    set(row)
                    != {
                        "sequence",
                        "previous_sha256",
                        "execution_id",
                        "package_sha256",
                        "kind",
                        "payload",
                        "record_id",
                        "at_utc",
                    }
                    or record_bytes(row) != saved.body
                    or type(row["sequence"]) is not int
                    or row["sequence"] != sequence
                    or row["execution_id"] != self.execution_id
                    or row["package_sha256"] != self.package_sha256
                    or not isinstance(row["kind"], str)
                    or not re.fullmatch(r"[A-Z][A-Z_]{1,63}", row["kind"])
                    or not isinstance(row["payload"], dict)
                ):
                    raise StoreError("record binding changed")
                if (
                    not isinstance(row["record_id"], str)
                    or not re.fullmatch(r"[0-9a-f]{32}", row["record_id"])
                    or not isinstance(row["at_utc"], str)
                ):
                    raise StoreError("record identity or timestamp missing")
                stamp = datetime.fromisoformat(row["at_utc"])
                if stamp.tzinfo is None or stamp.utcoffset() != UTC.utcoffset(stamp):
                    raise StoreError("UTC record timestamp required")
                rows.append(row)
                expected = row["previous_sha256"]
                sequence -= 1
                if sequence:
                    if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
                        raise StoreError("record predecessor changed")
                    key = self.root + f"events/{sequence:08d}-{expected}.json"
                elif expected is not None:
                    raise StoreError("opening predecessor changed")
            return list(reversed(rows)), head
        except (KeyError, TypeError, ValueError) as error:
            raise StoreError("malformed or changed committed journal") from error

    def append(
        self, kind: str, payload: dict[str, Any], expected_head: str | None
    ) -> dict[str, Any]:
        if not re.fullmatch(r"[A-Z][A-Z_]{1,63}", kind) or not isinstance(payload, dict):
            raise StoreError("exact record kind and payload required")
        rows, head = self.load()
        if (head is None) != (expected_head is None) or (
            head is not None and head.token != expected_head
        ):
            raise Conflict("journal head changed before append")
        row = {
            "sequence": len(rows) + 1,
            "previous_sha256": None if not rows else sha(record_bytes(rows[-1])),
            "package_sha256": self.package_sha256,
            "execution_id": self.execution_id,
            "kind": kind,
            "payload": payload,
            "record_id": uuid.uuid4().hex,
            "at_utc": datetime.now(UTC).isoformat(),
        }
        raw = record_bytes(row)
        if (
            len(rows) >= 512
            or sum(len(record_bytes(r)) for r in rows) + len(raw) > 32 * 1024 * 1024
        ):
            raise StoreError("bounded record/byte allowance exceeded")
        anchor = sha(raw)
        key = self.root + f"events/{row['sequence']:08d}-{anchor}.json"
        self._commit(key, raw, None)
        pointer = canonical(
            {
                "sequence": row["sequence"],
                "record_key": key,
                "record_sha256": anchor,
                "package_sha256": self.package_sha256,
                "execution_id": self.execution_id,
            }
        )
        self._commit(self.root + "head.json", pointer, expected_head)
        return {
            "label": "JOURNAL_COMMIT_NOT_TARGET_OUTCOME_PROOF",
            "record_sha256": anchor,
            "sequence": row["sequence"],
            "target_retry_authorized": False,
            "target_outcome_proven": False,
        }

    def _commit(self, key: str, body: bytes, expected: str | None) -> None:
        try:
            self.store.put(key, body, expected)
        except Exception as error:
            # The conditional storage write can have taken effect. Read exact content once;
            # access errors, foreign content and missing objects remain unknown/blocked.
            try:
                actual = self.store.get(key)
            except Exception as read_error:
                raise StoreError(
                    "unknown conditional write; preserve without target retry"
                ) from read_error
            if actual is None or actual.body != body:
                raise StoreError("conditional write not authoritatively reconciled") from error
        observed = self.store.get(key)
        if observed is None or observed.body != body:
            raise StoreError("conditional write readback mismatch")
        observed.validate()


class S3Client(Protocol):
    meta: Any

    def get_object(self, **request: Any) -> dict[str, Any]: ...
    def put_object(self, **request: Any) -> dict[str, Any]: ...


class IdentityClient(Protocol):
    meta: Any

    def get_caller_identity(self) -> dict[str, Any]: ...


def runtime_profile(client: S3Client) -> dict[str, Any]:
    """Fingerprint installed SDK versions and actual conditional-write API model; no AWS call."""
    from importlib.metadata import version

    operations = {}
    required = {
        "GetObject": set(
            get_request("profile-test-1234", "executions/profile-test-1234/head.json")
        ),
        "PutObject": set(
            put_request(
                "profile-test-1234", "executions/profile-test-1234/head.json", b"profile", None
            )
        )
        | {"IfMatch"},
    }
    for operation, names in required.items():
        shape = client.meta.service_model.operation_model(operation).input_shape
        if shape is None or not names.issubset(shape.members):
            raise StoreError(
                "SDK lacks required owner, checksum or conditional-write request fields"
            )
        operations[operation] = {
            "members": {k: v.type_name for k, v in sorted(shape.members.items())},
            "required": sorted(shape.required_members),
        }
    result = {
        "boto3": version("boto3"),
        "botocore": version("botocore"),
        "api_version": client.meta.service_model.api_version,
        "operations": operations,
    }
    frozen: dict[str, Any] = json.loads(canonical(result))
    return frozen


class S3ObjectStore:
    """Effectful SDK adapter, only for the independently admitted lifecycle deployment.

    Unit tests do not replace this with a managed-success simulator. Its actual role/model,
    conditional writes, version readbacks and external durability remain live qualification gates.
    Deployment pins (role ID and SDK-model digest) must come from trusted immutable authority,
    never Scheduler event input. No method deletes evidence or creates infrastructure.
    """

    def __init__(
        self,
        client: S3Client,
        identity: IdentityClient,
        execution_id: str,
        expected_role_id: str,
        qualified_model_sha256: str,
    ) -> None:
        from scripts.prepare_stage33_bootstrap import REGION
        from scripts.stage33_lifecycle_authority import LIFECYCLE_ROLE

        prefix(execution_id)
        if not re.fullmatch(r"AROA[A-Z0-9]{17}", expected_role_id) or not re.fullmatch(
            r"[0-9a-f]{64}", qualified_model_sha256
        ):
            raise StoreError("immutable admitted role/model pins required before API use")
        if (
            client.meta.endpoint_url != f"https://s3.{REGION}.amazonaws.com"
            or identity.meta.endpoint_url != f"https://sts.{REGION}.amazonaws.com"
            or identity.meta.region_name != REGION
            or identity.meta.config.retries != {"total_max_attempts": 1, "mode": "standard"}
        ):
            raise StoreError("explicit regional endpoints and bounded identity SDK required")
        configuration = client.meta.config
        if (
            client.meta.region_name != REGION
            or configuration.signature_version != "s3v4"
            or configuration.retries != {"total_max_attempts": 1, "mode": "standard"}
        ):
            raise StoreError("explicit regional SigV4 single-attempt SDK configuration required")
        if sha(canonical(runtime_profile(client))) != qualified_model_sha256:
            raise StoreError("SDK model/version drift before identity or object API use")
        observed = identity.get_caller_identity()
        if (
            observed.get("Account") != ACCOUNT
            or not isinstance(observed.get("UserId"), str)
            or observed["UserId"].split(":", 1)[0] != expected_role_id
            or not isinstance(observed.get("Arn"), str)
            or not observed["Arn"].startswith(
                f"arn:aws:sts::{ACCOUNT}:assumed-role/{LIFECYCLE_ROLE}/"
            )
        ):
            raise StoreError("actual lifecycle execution identity mismatch")
        self.client = client
        self.execution_id = execution_id

    def get(self, key: str) -> Object | None:
        request = get_request(self.execution_id, key)
        try:
            response = self.client.get_object(**request)
        except Exception as error:
            document = getattr(error, "response", None)
            if isinstance(document, dict) and document.get("Error", {}).get("Code") == "NoSuchKey":
                return None
            raise StoreError("actual evidence read denied or ambiguous; not absence") from error
        return self._read_response(response)

    def _read_response(self, response: dict[str, Any]) -> Object:
        try:
            if (
                response["ResponseMetadata"]["HTTPStatusCode"] != 200
                or not response["ResponseMetadata"]["RequestId"]
                or response["ServerSideEncryption"] != "AES256"
            ):
                raise StoreError("actual response, encryption or request identity missing")
            stream = response["Body"]
            try:
                raw = stream.read(MAX_BYTES + 1)
            finally:
                stream.close()
            if (
                type(response["ContentLength"]) is not int
                or len(raw) != response["ContentLength"]
                or len(raw) > MAX_BYTES
                or response["ChecksumSHA256"]
                != base64.b64encode(hashlib.sha256(raw).digest()).decode()
            ):
                raise StoreError("bounded full-object checksum/length readback mismatch")
            value = Object(raw, response["ETag"], response["VersionId"])
            value.validate()
            return value
        except (KeyError, TypeError, ValueError) as error:
            raise StoreError("incomplete actual immutable evidence readback") from error

    def put(self, key: str, body: bytes, expected: str | None) -> Object:
        request = put_request(self.execution_id, key, body, expected)
        # Never retry SDK writes here. EvidenceLog must reconcile a lost acknowledgement.
        response = self.client.put_object(**request)
        try:
            if (
                response["ResponseMetadata"]["HTTPStatusCode"] != 200
                or not response["ResponseMetadata"]["RequestId"]
                or response["ServerSideEncryption"] != "AES256"
                or response["ChecksumSHA256"] != request["ChecksumSHA256"]
            ):
                raise StoreError("write acknowledgement lacks exact actual checksum binding")
            version = response["VersionId"]
            immutable = self.client.get_object(**get_request(self.execution_id, key, version))
            value = self._read_response(immutable)
            if value.body != body or value.version_id != version or value.token != response["ETag"]:
                raise StoreError("original acknowledged version differs from exact bytes")
            return value
        except (KeyError, TypeError, ValueError) as error:
            raise StoreError("actual write acknowledgement unresolved; no blind retry") from error


def admitted_s3_store(execution_id: str, role_id: str, model_sha256: str) -> S3ObjectStore:
    """Create actual clients with explicit TLS/endpoints/retry settings after runtime admission.

    No package is installed by this function. Absent or changed runtime packages fail closed.
    Immutable deployment pins must not be populated from untrusted invocation-event fields.
    """
    import importlib

    from scripts.prepare_stage33_bootstrap import REGION

    prefix(execution_id)
    if not re.fullmatch(r"AROA[A-Z0-9]{17}", role_id) or not re.fullmatch(
        r"[0-9a-f]{64}", model_sha256
    ):
        raise StoreError("exact immutable deployment pins required before SDK loading")
    sdk = importlib.import_module("boto3")
    config = importlib.import_module("botocore.config").Config
    retry = {"total_max_attempts": 1, "mode": "standard"}
    s3 = sdk.client(
        "s3",
        region_name=REGION,
        endpoint_url=f"https://s3.{REGION}.amazonaws.com",
        verify=True,
        config=config(signature_version="s3v4", retries=retry, connect_timeout=5, read_timeout=10),
    )
    sts = sdk.client(
        "sts",
        region_name=REGION,
        endpoint_url=f"https://sts.{REGION}.amazonaws.com",
        verify=True,
        config=config(signature_version="v4", retries=retry, connect_timeout=5, read_timeout=10),
    )
    return S3ObjectStore(s3, sts, execution_id, role_id, model_sha256)
