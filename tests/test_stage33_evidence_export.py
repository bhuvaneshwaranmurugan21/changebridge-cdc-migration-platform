"""Real private-file and process recovery checks; no AWS success fixtures."""
import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys

import pytest

from scripts.export_stage33_evidence import (
    ExportError,
    export_journal,
    validate_export,
    verify_export,
)
from scripts.prepare_stage33_bootstrap import canonical, compile_package, digest
from scripts.stage33_mutation_journal import MutationJournal


@pytest.fixture
def exported(tmp_path):
    package = compile_package()
    destination = tmp_path / 'receipts.json'
    with MutationJournal(tmp_path / 'journal', package, 'export-run-1234') as journal:
        journal.intent('bootstrap-01')
        journal.acknowledge('bootstrap-01', 124, b'', b'LOCAL_NO_AWS_EXECUTION')
        journal.observe('bootstrap-01', b'LOCAL_RECORD_ONLY', b'')
        receipt = export_journal(journal, destination)
    return destination, receipt


def test_export_verifies_after_source_directory_is_removed(exported):
    path, receipt = exported
    shutil.rmtree(path.parent / 'journal')
    actual = verify_export(path, receipt['file_sha256'])
    assert actual == receipt
    assert actual['pending_step'] == 'bootstrap-01'
    assert actual['record_count'] == 4
    assert actual['aws_proven'] is False
    assert actual['cleanup_authorized'] is False
    assert actual['durable_retention_proven'] is False
    assert path.stat().st_mode & 0o777 == 0o600


def test_independent_process_without_source_or_worktree_state(exported):
    path, receipt = exported
    shutil.rmtree(path.parent / 'journal')
    result = subprocess.run([sys.executable, '-m', 'scripts.export_stage33_evidence',
                             '--verify', str(path), '--expected-sha256', receipt['file_sha256']],
                            capture_output=True, check=True)
    assert json.loads(result.stdout) == receipt


@pytest.mark.parametrize('anchor', ['0' * 64, '', 'A' * 64, 'not-a-digest'])
def test_requires_separately_retained_exact_anchor(exported, anchor):
    path, _ = exported
    with pytest.raises(ExportError, match='expected export digest'):
        verify_export(path, anchor)


def test_recomputed_inner_digest_cannot_replace_external_anchor(exported):
    path, receipt = exported
    payload = json.loads(path.read_bytes())
    payload['records'][2]['payload']['stderr']['hex'] = b'changed error'.hex()
    payload['export_sha256'] = digest({k: v for k, v in payload.items() if k != 'export_sha256'})
    path.write_bytes(canonical(payload))
    with pytest.raises(ExportError, match='expected export digest'):
        verify_export(path, receipt['file_sha256'])


@pytest.mark.parametrize('change', [
    'success-claim', 'retention-claim', 'cleanup-claim', 'sequence', 'previous',
    'raw-receipt', 'receipt-state', 'execution', 'last-record', 'timestamp', 'empty',
    'opening', 'unsupported-kind', 'dependent-step', 'duplicate-ack',
])
def test_independent_verifier_rejects_invalid_chain_even_with_new_file_hash(exported, change):
    path, _ = exported
    envelope = json.loads(path.read_bytes())
    rows = envelope['records']
    if change in {'success-claim', 'retention-claim', 'cleanup-claim'}:
        name = {'success-claim': 'aws_proven', 'retention-claim': 'durable_retention_proven',
                'cleanup-claim': 'cleanup_authorized'}[change]
        envelope[name] = True
    elif change == 'sequence':
        rows[1]['sequence'] = True
    elif change == 'previous':
        rows[1]['previous_sha256'] = 'wrong'
    elif change == 'raw-receipt':
        rows[2]['payload']['stdout']['hex'] = '00'
    elif change == 'receipt-state':
        rows[3]['payload']['configuration_verified'] = True
    elif change == 'execution':
        rows[2]['execution_id'] = 'another-run-1234'
    elif change == 'last-record':
        envelope['last_record_sha256'] = 'wrong'
    elif change == 'timestamp':
        rows[2]['at_utc'] = '2026-10-07T00:00:00'
    elif change == 'empty':
        envelope['records'] = []
    elif change == 'opening':
        rows[0]['payload']['execution_id'] = 'another-run-1234'
    elif change == 'unsupported-kind':
        rows[3]['kind'] = 'SUCCESS'
    elif change == 'dependent-step':
        rows[1]['payload']['step_id'] = 'bootstrap-02'
    elif change == 'duplicate-ack':
        rows.append(copy.deepcopy(rows[2]))
    # Restore hashes to test semantic validation rather than merely corrupted file detection.
    for n, row in enumerate(rows, 1):
        if change != 'sequence':
            row['sequence'] = n
        if change != 'previous':
            row['previous_sha256'] = rows[n - 2]['sha256'] if n > 1 else None
        row['sha256'] = digest({k: v for k, v in row.items() if k != 'sha256'})
    if change != 'last-record' and rows:
        envelope['last_record_sha256'] = rows[-1]['sha256']
    envelope['export_sha256'] = digest({k: v for k, v in envelope.items()
                                       if k != 'export_sha256'})
    raw = canonical(envelope)
    with pytest.raises(ExportError):
        validate_export(raw, hashlib.sha256(raw).hexdigest())


@pytest.mark.parametrize('unsafe', ['public-file', 'public-directory', 'hardlink', 'symlink'])
def test_private_export_paths_are_enforced(exported, unsafe):
    path, receipt = exported
    if unsafe == 'public-file':
        path.chmod(0o644)
    elif unsafe == 'public-directory':
        path.parent.chmod(0o755)
    elif unsafe == 'hardlink':
        os.link(path, path.parent / 'linked.json')
    else:
        alias = path.parent / 'alias.json'
        alias.symlink_to(path)
        path = alias
    with pytest.raises(ExportError):
        verify_export(path, receipt['file_sha256'])


def test_no_overwrite_no_source_directory_export_no_cache_adoption(tmp_path):
    with MutationJournal(tmp_path / 'journal', compile_package(), 'export-run-1234') as journal:
        with pytest.raises(ExportError, match='separate'):
            export_journal(journal, journal.directory / 'export.json')
        path = tmp_path / 'once.json'
        export_journal(journal, path)
        original = path.read_bytes()
        with pytest.raises(FileExistsError):
            export_journal(journal, path)
        assert path.read_bytes() == original
        journal.rows[0]['payload']['execution_id'] = 'tampered-run'
        with pytest.raises(ExportError, match='memory'):
            export_journal(journal, tmp_path / 'tampered.json')
        assert not (tmp_path / 'tampered.json').exists()


def test_cli_failure_does_not_print_private_receipts(exported):
    path, _ = exported
    result = subprocess.run([sys.executable, '-m', 'scripts.export_stage33_evidence',
                             '--verify', str(path), '--expected-sha256', '0' * 64],
                            capture_output=True)
    assert result.returncode == 1
    assert b'LOCAL_NO_AWS_EXECUTION' not in result.stdout
    assert str(path).encode() not in result.stdout
    assert json.loads(result.stdout)['aws_proven'] is False


def test_actual_process_exit_export_stays_verifiable(tmp_path):
    package_file = tmp_path / 'package.json'
    package_file.write_bytes(canonical(compile_package()))
    code = '''import json,os,sys
from pathlib import Path
from scripts.stage33_mutation_journal import MutationJournal
from scripts.export_stage33_evidence import export_journal
p=Path(sys.argv[1])
j=MutationJournal(p/'journal',json.loads((p/'package.json').read_bytes()),'export-run-1234')
j.intent('bootstrap-01')
r=export_journal(j,p/'receipts.json')
(p/'anchor').write_text(r['file_sha256'])
os._exit(23)
'''
    result = subprocess.run([sys.executable, '-c', code, str(tmp_path)])
    assert result.returncode == 23
    shutil.rmtree(tmp_path / 'journal')
    receipt = verify_export(tmp_path / 'receipts.json', (tmp_path / 'anchor').read_text())
    assert receipt['pending_step'] == 'bootstrap-01'


def test_nested_source_export_is_not_an_independent_copy(tmp_path):
    with MutationJournal(tmp_path / 'journal', compile_package(), 'export-run-1234') as journal:
        nested = journal.directory / 'nested'
        nested.mkdir(mode=0o700)
        with pytest.raises(ExportError, match='separate'):
            export_journal(journal, nested / 'receipts.json')


def test_export_binds_concrete_creation_tags(tmp_path):
    tags = {'Project': 'ChangeBridge', 'Owner': 'bhuvaneshwaranmurugan21',
            'Stage': 'part3-stage3', 'CostCenter': 'changebridge-p3s3',
            'ExpiresAt': '2026-10-08T00:00:00Z', 'ExecutionId': 'export-run-1234'}
    path = tmp_path / 'receipts.json'
    with MutationJournal(tmp_path / 'journal', compile_package(), 'export-run-1234', tags) as j:
        j.intent('bootstrap-01')
        receipt = export_journal(j, path)
    envelope = json.loads(path.read_bytes())
    assert envelope['creation_tags'] == tags
    request = envelope['records'][1]['payload']['request']
    assert {r['TagKey']: r['TagValue'] for r in request['Tags']} == tags
    assert verify_export(path, receipt['file_sha256'])['pending_step'] == 'bootstrap-01'


def test_cli_exports_then_verifies_real_local_journal(tmp_path):
    package_file = tmp_path / 'package.json'
    package_file.write_bytes(canonical(compile_package()))
    package_file.chmod(0o600)
    with MutationJournal(tmp_path / 'journal', compile_package(), 'export-run-1234') as journal:
        journal.intent('bootstrap-01')
    output = tmp_path / 'receipts.json'
    result = subprocess.run([sys.executable, '-m', 'scripts.export_stage33_evidence',
                             '--journal-directory', str(tmp_path / 'journal'),
                             '--package', str(package_file), '--execution-id', 'export-run-1234',
                             '--output', str(output)], capture_output=True, check=True)
    receipt = json.loads(result.stdout)
    assert receipt == verify_export(output, receipt['file_sha256'])
    assert receipt['pending_step'] == 'bootstrap-01'


def test_truncated_or_noncanonical_export_cannot_be_accepted(exported):
    path, _ = exported
    for raw in (path.read_bytes()[:-12], path.read_bytes() + b'\n', b'null', b'[]'):
        with pytest.raises(ExportError):
            validate_export(raw, hashlib.sha256(raw).hexdigest())


def test_bounded_input_is_enforced_before_parsing(tmp_path):
    from scripts.export_stage33_evidence import LIMIT

    path = tmp_path / 'oversized.json'
    with path.open('wb') as stream:
        stream.truncate(LIMIT + 1)
    path.chmod(0o600)
    with pytest.raises(ExportError, match='bounded'):
        verify_export(path, '0' * 64)
