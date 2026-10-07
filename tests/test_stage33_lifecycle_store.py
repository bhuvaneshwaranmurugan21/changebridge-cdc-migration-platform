"""Real local durable CAS/concurrency/crash checks; no managed AWS outcome is asserted."""

import json
import os
import signal
import sqlite3
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from scripts.stage33_lifecycle_authority import EVIDENCE, prefix
from scripts.stage33_lifecycle_store import (
    Conflict,
    EvidenceLog,
    SQLiteObjectStore,
    StoreError,
    admitted_s3_store,
    get_request,
    put_request,
)

EXECUTION = "lifecycle-test-1234"
HEAD = prefix(EXECUTION) + "head.json"
PACKAGE = "a" * 64


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_payload_never_writes_evidence(tmp_path, value):
    with SQLiteObjectStore(tmp_path / "store", EXECUTION) as store:
        log = EvidenceLog(store, EXECUTION, PACKAGE)
        with pytest.raises(StoreError, match="finite interoperable"):
            log.append("LOCAL_INTENT", {"nested": [value]}, None)
        assert log.load() == ([], None)


@pytest.mark.parametrize("field,value", [("sequence", True), ("kind", "bad"), ("payload", [])])
def test_even_rehashed_invalid_record_semantics_are_rejected(tmp_path, field, value):
    from scripts.prepare_stage33_bootstrap import canonical
    from scripts.stage33_lifecycle_store import sha

    with SQLiteObjectStore(tmp_path / "store", EXECUTION) as store:
        log = EvidenceLog(store, EXECUTION, PACKAGE)
        log.append("LOCAL_INTENT", {}, None)
        rows, old_head = log.load()
        row = rows[0]
        row[field] = value
        raw = canonical(row)
        digest = sha(raw)
        key = prefix(EXECUTION) + f"events/00000001-{digest}.json"
        store.put(key, raw, None)
        pointer = canonical({"sequence": 1, "record_key": key, "record_sha256": digest,
                             "package_sha256": PACKAGE, "execution_id": EXECUTION})
        store.put(HEAD, pointer, old_head.token)
        with pytest.raises(StoreError):
            log.load()


@pytest.mark.parametrize("lost_key", ["event", "head"])
def test_lost_ack_after_actual_sqlite_commit_reconciles_without_second_put(tmp_path, lost_key):
    with SQLiteObjectStore(tmp_path / "store", EXECUTION) as actual:
        class InterruptedLocalReturn:
            # Actual local writes, with a transport-return failure. This is not an AWS receipt.
            def __init__(self):
                self.calls = []

            def get(self, key):
                return actual.get(key)

            def put(self, key, body, expected):
                self.calls.append(key)
                value = actual.put(key, body, expected)
                if (lost_key == "head" and key == HEAD) or (
                    lost_key == "event" and "/events/" in key
                ):
                    raise OSError("local acknowledgement interrupted after durable commit")
                return value

        interrupted = InterruptedLocalReturn()
        log = EvidenceLog(interrupted, EXECUTION, PACKAGE)
        receipt = log.append("LOCAL_INTENT", {"local": True}, None)
        assert len(log.load()[0]) == 1
        assert len(interrupted.calls) == 2 and len(set(interrupted.calls)) == 2
        assert receipt["target_outcome_proven"] is False
        assert receipt["target_retry_authorized"] is False


def test_denied_local_write_cannot_manufacture_committed_head(tmp_path):
    with SQLiteObjectStore(tmp_path / "store", EXECUTION) as actual:
        class DeniedLocalWrite:
            def get(self, key):
                return actual.get(key)

            def put(self, key, body, expected):
                raise PermissionError("local write denied before dispatch")

        log = EvidenceLog(DeniedLocalWrite(), EXECUTION, PACKAGE)
        with pytest.raises(StoreError):
            log.append("LOCAL_INTENT", {}, None)
        assert log.load() == ([], None)


def test_unqualified_factory_rejects_before_loading_sdk_or_calling_aws():
    with pytest.raises(StoreError):
        admitted_s3_store(EXECUTION, "unqualified", "")


def test_exact_s3_requests_use_owner_sse_and_conditional_tokens():
    immutable = prefix(EXECUTION) + "events/a.json"
    request = put_request(EXECUTION, immutable, b'{"record":"local"}', None)
    assert request["Bucket"] == EVIDENCE
    assert request["IfNoneMatch"] == "*" and "IfMatch" not in request
    assert request["ServerSideEncryption"] == "AES256"
    assert request["ExpectedBucketOwner"]
    assert put_request(EXECUTION, HEAD, b"head", "opaque-etag")["IfMatch"] == "opaque-etag"
    assert get_request(EXECUTION, immutable, "exact-version")["VersionId"] == "exact-version"


@pytest.mark.parametrize(
    "key",
    [
        "foreign/head.json",
        prefix(EXECUTION) + "../head.json",
        prefix(EXECUTION) + "events//a.json",
        prefix(EXECUTION) + "authority/a.json",
        prefix(EXECUTION) + "other/a.json",
    ],
)
def test_writes_cannot_escape_or_forge_authority(key):
    with pytest.raises(StoreError):
        put_request(EXECUTION, key, b"x", None)


def test_immutable_event_cannot_use_cas_or_overwrite(tmp_path):
    key = prefix(EXECUTION) + "events/a.json"
    with SQLiteObjectStore(tmp_path / "store", EXECUTION) as store:
        value = store.put(key, b"first", None)
        with pytest.raises(Conflict):
            store.put(key, b"second", None)
        with pytest.raises(StoreError):
            store.put(key, b"second", value.token)
        assert store.get(key) == value


def test_head_revision_prevents_aba_and_survives_reopen(tmp_path):
    directory = tmp_path / "store"
    with SQLiteObjectStore(directory, EXECUTION) as store:
        first = store.put(HEAD, b"A", None)
        second = store.put(HEAD, b"B", first.token)
        third = store.put(HEAD, b"A", second.token)
        assert first.token != third.token
        with pytest.raises(Conflict):
            store.put(HEAD, b"C", first.token)
    with SQLiteObjectStore(directory, EXECUTION) as store:
        assert store.get(HEAD) == third
        assert store.put(HEAD, b"C", third.token).version_id == "4"


def test_actual_competing_writers_have_one_cas_winner(tmp_path):
    directory = tmp_path / "store"
    with SQLiteObjectStore(directory, EXECUTION) as store:
        token = store.put(HEAD, b"first", None).token

    def compete(i):
        with SQLiteObjectStore(directory, EXECUTION) as store:
            try:
                store.put(HEAD, str(i).encode(), token)
                return "won"
            except Conflict:
                return "lost"

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(compete, range(2))) == ["lost", "won"]


def test_identical_parallel_intents_cannot_adopt_competing_journal_head(tmp_path):
    directory = tmp_path / "store"
    with SQLiteObjectStore(directory, EXECUTION):
        pass
    rendezvous = threading.Barrier(2)

    def compete(_):
        with SQLiteObjectStore(directory, EXECUTION) as actual:
            class ParallelLocalWrites:
                def get(self, key):
                    return actual.get(key)

                def put(self, key, body, expected):
                    if "/events/" in key:
                        rendezvous.wait(timeout=5)
                    return actual.put(key, body, expected)

            try:
                EvidenceLog(ParallelLocalWrites(), EXECUTION, PACKAGE).append(
                    "LOCAL_INTENT", {"identical": True}, None)
                return "committed"
            except StoreError:
                return "blocked"

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(compete, range(2))) == ["blocked", "committed"]
    with SQLiteObjectStore(directory, EXECUTION) as store:
        assert len(EvidenceLog(store, EXECUTION, PACKAGE).load()[0]) == 1


def test_actual_exit_between_immutable_event_and_head_leaves_no_dispatch_authority(tmp_path):
    directory = tmp_path / "store"
    code = """import os,sys
from pathlib import Path
from scripts.stage33_lifecycle_store import SQLiteObjectStore,EvidenceLog
s=SQLiteObjectStore(Path(sys.argv[1]),'lifecycle-test-1234')
class InterruptedLocalStorage:
    def get(self,key):return s.get(key)
    def put(self,key,body,expected):
        result=s.put(key,body,expected)
        if '/events/' in key:os._exit(29)
        return result
EvidenceLog(InterruptedLocalStorage(),'lifecycle-test-1234','a'*64).append('LOCAL_INTENT',{},None)
"""
    result = subprocess.run([sys.executable, "-c", code, str(directory)])
    assert result.returncode == 29
    with SQLiteObjectStore(directory, EXECUTION) as store:
        assert EvidenceLog(store, EXECUTION, PACKAGE).load() == ([], None)
    with sqlite3.connect(directory / "objects.sqlite3") as connection:
        assert connection.execute("SELECT count(*) FROM objects").fetchone()[0] == 1


def test_committed_chain_has_distinct_intents_and_stale_append_is_rejected(tmp_path):
    with SQLiteObjectStore(tmp_path / "store", EXECUTION) as store:
        log = EvidenceLog(store, EXECUTION, PACKAGE)
        receipt = log.append("LOCAL_INTENT", {"test": "local-only"}, None)
        rows, head = log.load()
        assert len(rows) == 1 and head is not None
        assert receipt["target_outcome_proven"] is False
        assert receipt["target_retry_authorized"] is False
        second = log.append("LOCAL_RECEIPT", {"test": "local-only"}, head.token)
        rows, new_head = log.load()
        assert len(rows) == 2 and rows[0]["record_id"] != rows[1]["record_id"]
        assert second["sequence"] == 2 and new_head is not None
        with pytest.raises(Conflict):
            log.append("LOCAL_RECEIPT", {}, head.token)


def test_orphan_event_never_authorizes_dispatch_or_appears_in_committed_chain(tmp_path):
    with SQLiteObjectStore(tmp_path / "store", EXECUTION) as store:
        store.put(prefix(EXECUTION) + "events/00000001-orphan.json", b"orphan", None)
        log = EvidenceLog(store, EXECUTION, PACKAGE)
        assert log.load() == ([], None)
        assert log.append("LOCAL_INTENT", {}, None)["target_outcome_proven"] is False
        assert len(log.load()[0]) == 1


def test_changed_committed_record_and_package_binding_fail_closed(tmp_path):
    directory = tmp_path / "store"
    with SQLiteObjectStore(directory, EXECUTION) as store:
        EvidenceLog(store, EXECUTION, PACKAGE).append("LOCAL_INTENT", {}, None)
        with pytest.raises(StoreError):
            EvidenceLog(store, EXECUTION, "b" * 64).load()
        # Actual direct corruption, not a fabricated managed-service response.
        connection = sqlite3.connect(directory / "objects.sqlite3")
        connection.execute(
            "UPDATE objects SET body=? WHERE key LIKE ?",
            (b"changed", prefix(EXECUTION) + "events/%"),
        )
        connection.commit()
        connection.close()
        with pytest.raises(StoreError):
            EvidenceLog(store, EXECUTION, PACKAGE).load()


def test_actual_process_exit_after_commit_preserves_chain(tmp_path):
    directory = tmp_path / "store"
    code = """import os,sys
from pathlib import Path
from scripts.stage33_lifecycle_store import SQLiteObjectStore,EvidenceLog
s=SQLiteObjectStore(Path(sys.argv[1]),'lifecycle-test-1234')
EvidenceLog(s,'lifecycle-test-1234','a'*64).append('LOCAL_INTENT',{'local':True},None)
os._exit(23)
"""
    r = subprocess.run([sys.executable, "-c", code, str(directory)])
    assert r.returncode == 23
    with SQLiteObjectStore(directory, EXECUTION) as store:
        assert len(EvidenceLog(store, EXECUTION, PACKAGE).load()[0]) == 1


def test_actual_kill_during_sql_transaction_rolls_back_before_visibility(tmp_path):
    directory = tmp_path / "store"
    with SQLiteObjectStore(directory, EXECUTION):
        pass
    ready = tmp_path / "ready"
    code = """import sqlite3,sys,time
from pathlib import Path
c=sqlite3.connect(Path(sys.argv[1])/'objects.sqlite3')
c.execute('BEGIN IMMEDIATE')
c.execute('INSERT INTO objects VALUES (?,?,?)',
          ('executions/lifecycle-test-1234/head.json',1,b'uncommitted'))
Path(sys.argv[2]).write_text('ready')
while True:time.sleep(0.05)
"""
    process = subprocess.Popen([sys.executable, "-c", code, str(directory), str(ready)])
    try:
        import time

        deadline = time.monotonic() + 5
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert ready.exists()
        os.kill(process.pid, signal.SIGKILL)
        assert process.wait(timeout=5) == -signal.SIGKILL
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
    with SQLiteObjectStore(directory, EXECUTION) as store:
        assert store.get(HEAD) is None


@pytest.mark.parametrize("attack", ["mode", "hardlink", "replace"])
def test_private_file_identity_guards(tmp_path, attack):
    directory = tmp_path / "store"
    with SQLiteObjectStore(directory, EXECUTION) as store:
        file = directory / "objects.sqlite3"
        if attack == "mode":
            file.chmod(0o644)
        elif attack == "hardlink":
            os.link(file, tmp_path / "second-link")
        else:
            file.rename(directory / "old")
            file.write_bytes(b"replacement")
            file.chmod(0o600)
        with pytest.raises(StoreError):
            store.get(HEAD)


def test_head_with_duplicate_json_keys_is_rejected(tmp_path):
    with SQLiteObjectStore(tmp_path / "store", EXECUTION) as store:
        EvidenceLog(store, EXECUTION, PACKAGE).append("LOCAL_INTENT", {}, None)
        head = store.get(HEAD)
        value = json.loads(head.body)
        raw = ("{" + '"sequence":999,' + json.dumps(value)[1:]).encode()
        store.put(HEAD, raw, head.token)
        with pytest.raises(StoreError):
            EvidenceLog(store, EXECUTION, PACKAGE).load()
