"""Real local filesystem/crash tests, never AWS bootstrap or managed acceptance proof."""

import json
import os
import stat
import subprocess
import sys

import pytest

from scripts.prepare_stage33_bootstrap import canonical
from scripts.stage33_bootstrap_journal import BootstrapJournal, JournalError

PACKAGE = {"package_sha256": "1" * 64, "label": "LOCAL_JOURNAL_TEST_NOT_AWS_PROOF"}


def test_private_durable_roundtrip_and_receipt_hashes(tmp_path):
    directory = tmp_path / "journal"
    with BootstrapJournal(directory, PACKAGE) as journal:
        identifier = journal.intent("sts", "get-caller-identity", {})
        journal.result(identifier, 0, b'{"label":"LOCAL_TEST_NOT_AWS_PROOF"}', b"")
        head = journal.entries[-1]["sha256"]
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    for path in directory.iterdir():
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    with BootstrapJournal(directory, PACKAGE) as journal:
        assert journal.entries[-1]["sha256"] == head
        assert journal.pending is None
    (directory / f"{identifier}.stdout").write_bytes(b"tampered")
    with pytest.raises(JournalError, match="receipt digest mismatch"):
        BootstrapJournal(directory, PACKAGE)


def test_only_one_writer_and_exact_package(tmp_path):
    directory = tmp_path / "journal"
    with BootstrapJournal(directory, PACKAGE), pytest.raises(BlockingIOError):
        BootstrapJournal(directory, PACKAGE)
    with pytest.raises(JournalError, match="different package"):
        BootstrapJournal(directory, {"package_sha256": "2" * 64})


@pytest.mark.parametrize("service,operation", [
    ("kms", "create-key"), ("iam", "put-role-policy"), ("s3api", "delete-bucket"),
    ("glue", "get-job"), ("iam", "list-roles"),
])
def test_mutation_and_unbounded_reads_never_enter_journal(tmp_path, service, operation):
    with BootstrapJournal(tmp_path / "journal", PACKAGE) as journal:
        with pytest.raises(JournalError, match="only bounded"):
            journal.intent(service, operation, {})
        assert len(journal.entries) == 1


def test_real_crash_after_fsynced_intent_retains_unknown_read(tmp_path):
    directory = tmp_path / "journal"
    code = (
        "import os; from pathlib import Path; "
        "from scripts.stage33_bootstrap_journal import BootstrapJournal; "
        f"journal=BootstrapJournal(Path({str(directory)!r}), {PACKAGE!r}); "
        "journal.intent('sts','get-caller-identity',{}); os._exit(17)"
    )
    result = subprocess.run([sys.executable, "-c", code], check=False)
    assert result.returncode == 17
    with BootstrapJournal(directory, PACKAGE) as journal:
        assert journal.pending is not None
        with pytest.raises(JournalError, match="unresolved operation"):
            journal.intent("sts", "get-caller-identity", {})
        journal.preserve_unknown_read()
        identifier = journal.intent("sts", "get-caller-identity", {})
        journal.result(identifier, 0, b"{}", b"")
    with BootstrapJournal(directory, PACKAGE) as journal:
        marker = next(row for row in journal.entries if row["kind"] == "READ_OUTCOME_UNRESOLVED")
        assert marker["payload"]["absence_proven"] is False
        assert marker["payload"]["configuration_proven"] is False
        assert journal.pending is None


@pytest.mark.parametrize("failure", [
    "An error occurred (AccessDenied) when calling the GetRole operation: denied",
    "An error occurred (NoSuchEntity) when calling the DeleteRole operation: absent",
    "Connection refused; NoSuchEntity",
])
def test_unknown_or_denied_failures_cannot_be_classified_as_absence(tmp_path, failure):
    with BootstrapJournal(tmp_path / "journal", PACKAGE) as journal:
        identifier = journal.intent("iam", "get-role", {"RoleName": "LOCAL_TEST"})
        journal.result(identifier, 254, b"", failure.encode())
        with pytest.raises(JournalError):
            journal.observe_absence(identifier, "NoSuchEntity")
        assert journal.pending is not None


def test_exact_failed_read_classification_retains_original_error(tmp_path):
    directory = tmp_path / "journal"
    error = b"An error occurred (NoSuchEntity) when calling the GetRole operation: absent"
    with BootstrapJournal(directory, PACKAGE) as journal:
        identifier = journal.intent("iam", "get-role", {"RoleName": "LOCAL_TEST"})
        journal.result(identifier, 254, b"", error)
        journal.observe_absence(identifier, "NoSuchEntity")
    with BootstrapJournal(directory, PACKAGE) as journal:
        assert journal.pending is None
        result = next(row for row in journal.entries if row["kind"] == "RESULT")
        assert result["payload"]["returncode"] == 254
        assert (directory / f"{identifier}.stderr").read_bytes() == error


@pytest.mark.parametrize("filename", ["writer.lock", "package.json", "journal.jsonl"])
def test_symlink_files_rejected_without_touching_target(tmp_path, filename):
    directory = tmp_path / "journal"
    directory.mkdir(mode=0o700)
    target = tmp_path / "untouched"
    target.write_bytes(b"untouched")
    (directory / filename).symlink_to(target)
    with pytest.raises((JournalError, OSError)):
        BootstrapJournal(directory, PACKAGE)
    assert target.read_bytes() == b"untouched"


def test_public_directory_and_symlink_directory_rejected(tmp_path):
    directory = tmp_path / "journal"
    directory.mkdir(mode=0o755)
    with pytest.raises(JournalError, match="ownership/mode"):
        BootstrapJournal(directory, PACKAGE)
    directory.chmod(0o700)
    link = tmp_path / "link"
    link.symlink_to(directory)
    with pytest.raises(JournalError, match="ownership/mode"):
        BootstrapJournal(link, PACKAGE)


def test_hardlinked_file_rejected(tmp_path):
    directory = tmp_path / "journal"
    directory.mkdir(mode=0o700)
    target = tmp_path / "target"
    target.write_bytes(b"untouched")
    target.chmod(0o600)
    os.link(target, directory / "writer.lock")
    with pytest.raises(JournalError, match="single-link"):
        BootstrapJournal(directory, PACKAGE)
    assert target.read_bytes() == b"untouched"


@pytest.mark.parametrize("kind", ["torn", "changed", "noncanonical", "mutation-recovery"])
def test_invalid_journal_is_preserved_and_rejected(tmp_path, kind):
    directory = tmp_path / "journal"
    with BootstrapJournal(directory, PACKAGE) as journal:
        if kind == "mutation-recovery":
            journal.append("READBACK_RECONCILED", {"passed": True})
    path = directory / "journal.jsonl"
    raw = path.read_bytes()
    if kind == "torn":
        path.write_bytes(raw[:-1])
    elif kind == "changed":
        path.write_bytes(raw.replace(b'"kind":"OPEN"', b'"kind":"FAKE"'))
    elif kind == "noncanonical":
        path.write_bytes(json.dumps(json.loads(raw), indent=2).encode() + b"\n")
    broken = path.read_bytes()
    with pytest.raises(JournalError):
        BootstrapJournal(directory, PACKAGE)
    assert path.read_bytes() == broken


def test_anchored_directory_survives_path_replacement(tmp_path):
    directory = tmp_path / "journal"
    renamed = tmp_path / "retained"
    with BootstrapJournal(directory, PACKAGE) as journal:
        directory.rename(renamed)
        directory.mkdir(mode=0o700)
        identifier = journal.intent("sts", "get-caller-identity", {})
        journal.result(identifier, 0, b"{}", b"")
    assert not list(directory.iterdir())
    assert (renamed / f"{identifier}.stdout").read_bytes() == b"{}"
    with BootstrapJournal(renamed, PACKAGE) as journal:
        assert journal.pending is None


def test_mismatched_result_cannot_write_receipts(tmp_path):
    directory = tmp_path / "journal"
    with BootstrapJournal(directory, PACKAGE) as journal:
        journal.intent("sts", "get-caller-identity", {})
        with pytest.raises(JournalError, match="identity mismatch"):
            journal.result("../escape", 0, b"{}", b"")
    assert not (tmp_path / "escape.stdout").exists()
    assert all(path.suffix not in {".stdout", ".stderr"} for path in directory.iterdir())


def test_non_object_journal_is_rejected(tmp_path):
    directory = tmp_path / "journal"
    with BootstrapJournal(directory, PACKAGE):
        pass
    (directory / "journal.jsonl").write_bytes(canonical(["not an entry"]))
    with pytest.raises(JournalError):
        BootstrapJournal(directory, PACKAGE)
