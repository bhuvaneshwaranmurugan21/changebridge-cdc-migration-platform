"""Scoped read construction and real local failure/crash checks; no AWS success is claimed."""

import json
import os
import shutil
import signal
import subprocess
import sys

import pytest

from scripts.prepare_stage33_bootstrap import canonical, compile_package
from scripts.stage33_key_coordinator import (
    LABEL,
    CoordinatorError,
    KeyReadbackCoordinator,
    bound_key,
    command_for,
)
from scripts.stage33_mutation_journal import MutationJournal, MutationJournalError
from tests.test_stage33_key_controls import TAGS, observations


@pytest.fixture
def journal(tmp_path):
    with MutationJournal(tmp_path / "journal", compile_package(), TAGS["ExecutionId"], TAGS) as j:
        j.intent("bootstrap-01")
        # Explicitly synthetic original ACK supplies selector bytes for local protocol tests only.
        j.acknowledge(
            "bootstrap-01", 0, canonical(observations()["before"]["metadata"]), b"SYNTHETIC"
        )
        yield j


def fake_cli(tmp_path, monkeypatch, code):
    directory = tmp_path / "bin"
    directory.mkdir(mode=0o700)
    executable = directory / "aws"
    executable.write_text("#!/usr/bin/python3\n" + code + "\n")
    executable.chmod(0o700)
    monkeypatch.setenv("PATH", str(directory) + os.pathsep + os.environ.get("PATH", ""))
    return executable


def test_exact_creation_selector_and_scoped_read_commands(journal):
    arn, metadata = bound_key(journal)
    assert arn == metadata["Arn"]
    for service, operation, request in [
        ("sts", "get-caller-identity", {}),
        ("kms", "describe-key", {"KeyId": arn}),
        ("kms", "get-key-policy", {"KeyId": arn, "PolicyName": "default"}),
        ("kms", "list-resource-tags", {"KeyId": arn, "Limit": 50}),
    ]:
        command = command_for("/qualified/aws", arn, service, operation, request)
        assert "--no-paginate" in command
        assert command[command.index("--endpoint-url") + 1].startswith("https://")
    assert journal.pending is not None


@pytest.mark.parametrize(
    "service,operation,parameters",
    [
        ("kms", "create-key", {}),
        ("kms", "schedule-key-deletion", {}),
        ("kms", "list-keys", {}),
        ("iam", "get-role", {}),
        ("s3api", "delete-bucket", {}),
        ("kms", "get-key-policy", {"KeyId": "foreign", "PolicyName": "default"}),
        ("kms", "list-resource-tags", {"KeyId": "foreign", "Limit": 50}),
        ("sts", "get-caller-identity", {"changed": True}),
    ],
)
def test_out_of_scope_reads_and_every_write_are_rejected(journal, service, operation, parameters):
    arn, _ = bound_key(journal)
    with pytest.raises(CoordinatorError):
        command_for("aws", arn, service, operation, parameters)


def test_missing_ack_is_never_resolved_by_tags_or_a_caller_supplied_key(tmp_path):
    with MutationJournal(tmp_path / "missing", compile_package(), TAGS["ExecutionId"], TAGS) as j:
        j.intent("bootstrap-01")
        with pytest.raises(CoordinatorError, match="acknowledgement"):
            bound_key(j)
        assert j.pending is not None


def test_cached_state_tampering_stops_before_transport(journal):
    journal.pending = {"step_id": "bootstrap-01"}
    with pytest.raises(CoordinatorError, match="cached"):
        bound_key(journal)


def test_missing_cli_preserves_attempt_without_any_read_intent(journal, monkeypatch, tmp_path):
    git = shutil.which("git")
    assert git is not None
    directory = tmp_path / "git-only"
    directory.mkdir()
    (directory / "git").symlink_to(git)
    monkeypatch.setenv("PATH", str(directory))
    count = len(journal.rows)
    with pytest.raises(CoordinatorError, match="CLI unavailable"):
        KeyReadbackCoordinator(journal)
    assert len(journal.rows) == count


def test_actual_denied_process_is_preserved_and_cannot_trigger_auto_retry(
    journal, tmp_path, monkeypatch
):
    fake_cli(
        tmp_path, monkeypatch, "import sys;sys.stderr.write('LOCAL_DENIAL_NOT_AWS');sys.exit(9)"
    )
    c = KeyReadbackCoordinator(journal)
    with pytest.raises(CoordinatorError, match="actual read failed"):
        c.read("sts", "get-caller-identity", {})
    receipt = json.loads(bytes.fromhex(journal.rows[-1]["payload"]["stdout"]["hex"]))
    assert receipt["returncode"] == 9
    assert bytes.fromhex(receipt["stderr"]["hex"]) == b"LOCAL_DENIAL_NOT_AWS"
    assert receipt["configuration_verified"] is False
    before = len(journal.rows)
    with pytest.raises(CoordinatorError, match="explicit"):
        c.read("sts", "get-caller-identity", {})
    assert len(journal.rows) == before
    with pytest.raises(CoordinatorError, match="explicit"):
        KeyReadbackCoordinator(journal)
    KeyReadbackCoordinator(journal, resume_unknown_reads=True)
    preserved = json.loads(bytes.fromhex(journal.rows[-1]["payload"]["stdout"]["hex"]))
    assert preserved["label"] == "EXPLICIT_UNKNOWN_READ_PRESERVED"
    assert preserved["mutation_retry_authorized"] is False
    with pytest.raises(MutationJournalError):
        journal.intent("bootstrap-01")


def test_foreign_identity_stops_before_any_key_read(journal, tmp_path, monkeypatch):
    fake_cli(tmp_path, monkeypatch, 'print(\'{"Account":"foreign","Arn":"foreign"}\')')
    c = KeyReadbackCoordinator(journal)
    with pytest.raises(ValueError):
        c.reconcile()
    intents = [
        json.loads(bytes.fromhex(r["payload"]["stdout"]["hex"]))
        for r in journal.rows
        if r["kind"] == "OBSERVATION"
    ]
    assert sum(r.get("label") == LABEL for r in intents) == 1
    assert c.identity_qualified is False
    with pytest.raises(CoordinatorError, match="identity"):
        c.read("kms", "describe-key", {"KeyId": c.key_arn})


def test_real_process_kill_preserves_unknown_read_and_requires_explicit_resume(tmp_path):
    package_file = tmp_path / "package.json"
    package_file.write_bytes(canonical(compile_package()))
    directory = tmp_path / "journal"
    with MutationJournal(directory, compile_package(), TAGS["ExecutionId"], TAGS) as j:
        j.intent("bootstrap-01")
        j.acknowledge(
            "bootstrap-01", 0, canonical(observations()["before"]["metadata"]), b"SYNTHETIC"
        )
    tags_file = tmp_path / "tags.json"
    tags_file.write_bytes(canonical(TAGS))
    cli_directory = tmp_path / "bin"
    cli_directory.mkdir(mode=0o700)
    aws = cli_directory / "aws"
    aws.write_text("#!/usr/bin/python3\nimport os,signal\nos.kill(os.getppid(),signal.SIGKILL)\n")
    aws.chmod(0o700)
    code = """import json,sys
from pathlib import Path
from scripts.stage33_mutation_journal import MutationJournal
from scripts.stage33_key_coordinator import KeyReadbackCoordinator
p=Path(sys.argv[1])
j=MutationJournal(p/'journal',json.loads((p/'package.json').read_bytes()),
                 'bootstrap-run-1234',json.loads((p/'tags.json').read_bytes()))
c=KeyReadbackCoordinator(j)
c.read('sts','get-caller-identity',{})
"""
    # Use the fixture's actual execution identifier rather than changing its immutable opening.
    code = code.replace("'bootstrap-run-1234'", repr(TAGS["ExecutionId"]))
    env = {**os.environ, "PATH": str(cli_directory) + os.pathsep + os.environ.get("PATH", "")}
    r = subprocess.run([sys.executable, "-c", code, str(tmp_path)], env=env)
    assert r.returncode == -signal.SIGKILL
    with MutationJournal(directory, compile_package(), TAGS["ExecutionId"], TAGS) as j:
        last = json.loads(bytes.fromhex(j.rows[-1]["payload"]["stdout"]["hex"]))
        assert last["label"] == LABEL
        with pytest.raises(CoordinatorError, match="explicit"):
            KeyReadbackCoordinator(j)
        old = len(j.rows)
        # Missing CLI after explicit preservation still performs zero API calls.
        try:
            KeyReadbackCoordinator(j, resume_unknown_reads=True)
        except CoordinatorError as error:
            assert "CLI unavailable" in str(error)
        assert len(j.rows) == old + 1
        assert j.pending is not None


def test_forged_read_result_without_intent_is_rejected(journal):
    journal.observe(
        "bootstrap-01",
        canonical(
            {"label": "SCOPED_READ_RESULT_NOT_CONFIGURATION_PROOF", "intent_record_sha256": "wrong"}
        ),
        b"",
    )
    with pytest.raises(CoordinatorError, match="matching"):
        KeyReadbackCoordinator(journal)


@pytest.mark.parametrize(
    "service,operation,parameters",
    [([], "get-caller-identity", {}), ("kms", [], {}), ("kms", "describe-key", [])],
)
def test_malformed_durable_read_scope_stops_without_transport(
    journal, service, operation, parameters
):
    from scripts.prepare_stage33_bootstrap import digest

    journal.observe(
        "bootstrap-01",
        canonical(
            {
                "label": LABEL,
                "service": service,
                "operation": operation,
                "request": parameters,
                "request_sha256": digest(parameters),
                "mutation_retry_authorized": False,
            }
        ),
        b"",
    )
    with pytest.raises(CoordinatorError):
        KeyReadbackCoordinator(journal)
    assert journal.pending is not None
