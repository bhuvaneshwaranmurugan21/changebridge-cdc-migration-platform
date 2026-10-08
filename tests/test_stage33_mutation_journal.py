"""Real local durability and rejection tests; no AWS execution is represented."""
import copy
import os
import sqlite3
import subprocess
import sys

import pytest

from scripts.prepare_stage33_bootstrap import canonical, compile_package, digest
from scripts.stage33_mutation_journal import MutationJournal, MutationJournalError


@pytest.fixture
def package():
    return compile_package()


def test_success_ack_is_not_configuration_proof(tmp_path, package):
    directory = tmp_path / 'journal'
    with MutationJournal(directory, package, 'local-run-1234') as journal:
        journal.intent('bootstrap-01')
        journal.acknowledge('bootstrap-01', 0, b'{"synthetic":true}', b'')
        journal.observe('bootstrap-01', b'{"synthetic_readback":true}', b'')
        assert journal.pending is not None
        with pytest.raises(MutationJournalError, match='unresolved'):
            journal.intent('bootstrap-02')
    with MutationJournal(directory, package, 'local-run-1234') as journal:
        assert journal.pending['step_id'] == 'bootstrap-01'
        assert journal.rows[-1]['payload']['configuration_verified'] is False
        with pytest.raises(MutationJournalError, match='already preserved'):
            journal.acknowledge('bootstrap-01', 0, b'overwrite', b'')


@pytest.mark.parametrize('after_ack', [False, True])
def test_actual_process_exit_preserves_unknown_outcome(tmp_path, package, after_ack):
    path = tmp_path / 'package.json'
    path.write_bytes(canonical(package))
    directory = tmp_path / 'crash'
    code = '''
import json,os,sys
from pathlib import Path
from scripts.stage33_mutation_journal import MutationJournal
j=MutationJournal(Path(sys.argv[1]),json.loads(Path(sys.argv[2]).read_bytes()),'local-run-1234')
j.intent('bootstrap-01')
if sys.argv[3]=='True': j.acknowledge('bootstrap-01',0,b'synthetic-success',b'')
os._exit(23)
'''
    result = subprocess.run([sys.executable, '-c', code, str(directory), str(path), str(after_ack)])
    assert result.returncode == 23
    with MutationJournal(directory, package, 'local-run-1234') as journal:
        assert journal.pending['step_id'] == 'bootstrap-01'
        assert len(journal.rows) == (3 if after_ack else 2)
        with pytest.raises(MutationJournalError, match='unresolved'):
            journal.intent('bootstrap-01')


def test_single_writer_and_package_freeze(tmp_path, package):
    directory = tmp_path / 'journal'
    with MutationJournal(directory, package, 'local-run-1234') as journal:
        with pytest.raises(BlockingIOError):
            MutationJournal(directory, package, 'local-run-1234')
        package['steps'][0]['request']['changed'] = True
        journal.intent('bootstrap-01')
        assert 'changed' not in journal.pending['request']


def test_identity_and_package_changes_refused(tmp_path, package):
    directory = tmp_path / 'journal'
    with MutationJournal(directory, package, 'local-run-1234'):
        pass
    with pytest.raises(MutationJournalError, match='identity mismatch'):
        MutationJournal(directory, package, 'another-run-1234')
    changed = copy.deepcopy(package)
    changed['steps'][0]['request']['changed'] = True
    with pytest.raises(MutationJournalError, match='digest mismatch'):
        MutationJournal(directory, changed, 'local-run-1234')
    changed['package_sha256'] = digest({k: v for k, v in changed.items() if k != 'package_sha256'})
    with pytest.raises(MutationJournalError, match='identity mismatch'):
        MutationJournal(directory, changed, 'local-run-1234')


@pytest.mark.parametrize('value', ['', 'short', '../escape', 'UPPERCASE-1234', 'x' * 65])
def test_invalid_execution_identity(tmp_path, package, value):
    with pytest.raises(MutationJournalError):
        MutationJournal(tmp_path / 'journal', package, value)


def test_wrong_step_and_receipt_identity(tmp_path, package):
    with MutationJournal(tmp_path / 'journal', package, 'local-run-1234') as journal:
        with pytest.raises(MutationJournalError, match='outside'):
            journal.intent('foreign-request')
        with pytest.raises(MutationJournalError):
            journal.acknowledge('bootstrap-01', 0, b'', b'')
        journal.intent('bootstrap-01')
        with pytest.raises(MutationJournalError):
            journal.observe('bootstrap-02', b'', b'')
        with pytest.raises(MutationJournalError, match='integer'):
            journal.acknowledge('bootstrap-01', True, b'', b'')


def test_symlink_database_and_directory_rejected(tmp_path, package):
    target = tmp_path / 'target'
    target.mkdir(mode=0o700)
    link = tmp_path / 'link'
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(MutationJournalError):
        MutationJournal(link, package, 'local-run-1234')
    foreign = tmp_path / 'foreign'
    foreign.write_bytes(b'preserve')
    (target / 'attempts.sqlite3').symlink_to(foreign)
    with pytest.raises(OSError):
        MutationJournal(target, package, 'local-run-1234')
    assert foreign.read_bytes() == b'preserve'


def test_hardlink_and_public_database_rejected(tmp_path, package):
    directory = tmp_path / 'journal'
    with MutationJournal(directory, package, 'local-run-1234'):
        pass
    db = directory / 'attempts.sqlite3'
    duplicate = tmp_path / 'duplicate'
    os.link(db, duplicate)
    with pytest.raises(MutationJournalError, match='single-link'):
        MutationJournal(directory, package, 'local-run-1234')
    duplicate.unlink()
    db.chmod(0o644)
    with pytest.raises(MutationJournalError, match='single-link'):
        MutationJournal(directory, package, 'local-run-1234')


def test_changed_receipt_and_fake_verified_observation_rejected(tmp_path, package):
    directory = tmp_path / 'journal'
    with MutationJournal(directory, package, 'local-run-1234') as journal:
        journal.intent('bootstrap-01')
        journal.observe('bootstrap-01', b'synthetic', b'')
        row = copy.deepcopy(journal.rows[-1])
    row['payload']['configuration_verified'] = True
    row['sha256'] = digest({k: v for k, v in row.items() if k != 'sha256'})
    with sqlite3.connect(directory / 'attempts.sqlite3') as connection:
        connection.execute('UPDATE records SET record=? WHERE sequence=3', (canonical(row),))
    with pytest.raises(MutationJournalError, match='cannot certify'):
        MutationJournal(directory, package, 'local-run-1234')


def test_corrupt_record_and_closed_journal_rejected(tmp_path, package):
    directory = tmp_path / 'journal'
    with MutationJournal(directory, package, 'local-run-1234') as journal:
        pass
    with pytest.raises(MutationJournalError, match='closed'):
        journal.intent('bootstrap-01')
    with sqlite3.connect(directory / 'attempts.sqlite3') as connection:
        connection.execute('UPDATE records SET record=? WHERE sequence=1', (b'torn',))
    with pytest.raises(MutationJournalError, match='malformed'):
        MutationJournal(directory, package, 'local-run-1234')


def test_foreign_schema_is_never_adopted_or_modified(tmp_path, package):
    directory = tmp_path / 'journal'
    directory.mkdir(mode=0o700)
    database = directory / 'attempts.sqlite3'
    with sqlite3.connect(database) as connection:
        connection.execute('CREATE TABLE unrelated (value TEXT)')
        connection.execute("INSERT INTO unrelated VALUES ('preserve')")
    database.chmod(0o600)
    before = database.read_bytes()
    with pytest.raises(MutationJournalError, match='do not adopt'):
        MutationJournal(directory, package, 'local-run-1234')
    assert database.read_bytes() == before


def test_sidecar_symlink_is_rejected_before_sqlite_opens(tmp_path, package):
    directory = tmp_path / 'journal'
    with MutationJournal(directory, package, 'local-run-1234'):
        pass
    target = tmp_path / 'preserve'
    target.write_bytes(b'foreign')
    (directory / 'attempts.sqlite3-journal').symlink_to(target)
    with pytest.raises(OSError):
        MutationJournal(directory, package, 'local-run-1234')
    assert target.read_bytes() == b'foreign'


def test_real_uncommitted_transaction_exit_rolls_back(tmp_path, package):
    directory = tmp_path / 'journal'
    with MutationJournal(directory, package, 'local-run-1234'):
        pass
    code = '''
import sqlite3,sys,os
c=sqlite3.connect(sys.argv[1])
c.execute('BEGIN IMMEDIATE')
c.execute('INSERT INTO records VALUES (?,?)',(2,b'uncommitted-not-acknowledged'))
os._exit(29)
'''
    result = subprocess.run([sys.executable, '-c', code, str(directory / 'attempts.sqlite3')])
    assert result.returncode == 29
    with MutationJournal(directory, package, 'local-run-1234') as journal:
        assert len(journal.rows) == 1
        assert journal.pending is None
        journal.intent('bootstrap-01')


def test_directory_or_database_substitution_stops_before_write(tmp_path, package):
    directory = tmp_path / 'journal'
    with MutationJournal(directory, package, 'local-run-1234') as journal:
        directory.rename(tmp_path / 'original')
        directory.mkdir(mode=0o700)
        preserved = directory / 'foreign'
        preserved.write_bytes(b'preserve')
        with pytest.raises(MutationJournalError, match='directory replaced'):
            journal.intent('bootstrap-01')
        assert preserved.read_bytes() == b'preserve'
        assert list(directory.iterdir()) == [preserved]
    directory = tmp_path / 'database-test'
    with MutationJournal(directory, package, 'local-run-1234') as journal:
        database = directory / 'attempts.sqlite3'
        database.rename(directory / 'original.sqlite3')
        database.write_bytes(b'preserve')
        database.chmod(0o600)
        with pytest.raises(MutationJournalError, match='database identity changed'):
            journal.intent('bootstrap-01')
        assert database.read_bytes() == b'preserve'


def test_live_sidecar_and_package_substitution_are_rejected(tmp_path, package):
    directory = tmp_path / 'journal'
    with MutationJournal(directory, package, 'local-run-1234') as journal:
        target = tmp_path / 'foreign'
        target.write_bytes(b'preserve')
        sidecar = directory / 'attempts.sqlite3-journal'
        sidecar.symlink_to(target)
        with pytest.raises(OSError):
            journal.intent('bootstrap-01')
        assert target.read_bytes() == b'preserve'
        sidecar.unlink()
        journal.package['steps'][0]['request']['changed'] = True
        with pytest.raises(MutationJournalError, match='in-memory package'):
            journal.intent('bootstrap-01')


def test_dependent_step_cannot_be_recorded_without_proven_prerequisite(tmp_path, package):
    with MutationJournal(tmp_path / 'journal', package, 'local-run-1234') as journal:
        with pytest.raises(MutationJournalError, match='prerequisite'):
            journal.intent('bootstrap-02')
        assert journal.pending is None
        assert len(journal.rows) == 1


def test_private_receipts_cannot_be_created_inside_git_worktree(package):
    from scripts.validate_part3_stage3 import ROOT

    target = ROOT / 'private-receipts-must-not-exist'
    assert not target.exists()
    with pytest.raises(MutationJournalError, match='outside the Git worktree'):
        MutationJournal(target, package, 'local-run-1234')
    assert not target.exists()
