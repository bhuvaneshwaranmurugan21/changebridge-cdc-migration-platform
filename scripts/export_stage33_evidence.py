"""Export private attempt receipts; local integrity is not AWS proof or durable retention."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.prepare_stage33_bootstrap import canonical, digest, verify_package
from scripts.stage33_mutation_journal import MutationJournal
from scripts.validate_part3_stage3 import ROOT

LIMIT = 32 * 1024 * 1024
LABEL = 'PRIVATE_LOCAL_ATTEMPT_EXPORT_NOT_AWS_OR_DURABILITY_PROOF'


class ExportError(ValueError):
    """An untrusted, incomplete or unsafe export cannot support retention decisions."""


def _parent(path: Path) -> int:
    path = path.absolute()
    if path.resolve() != path or path.is_relative_to(ROOT.resolve()):
        raise ExportError('private export must be outside the worktree without symlinks')
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    info = os.fstat(fd)
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        os.close(fd)
        raise ExportError('private owned export directory required')
    return fd


def _check_parent(path: Path, fd: int) -> None:
    info = path.parent.lstat()
    pinned = os.fstat(fd)
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o700
            or (info.st_dev, info.st_ino) != (pinned.st_dev, pinned.st_ino)):
        raise ExportError('export directory substituted or permissions changed')


def _read(path: Path) -> bytes:
    path = path.absolute()
    parent = _parent(path)
    try:
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
        with os.fdopen(fd, 'rb') as stream:
            before = os.fstat(stream.fileno())
            if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid()
                    or stat.S_IMODE(before.st_mode) != 0o600 or before.st_nlink != 1
                    or before.st_size > LIMIT):
                raise ExportError('bounded private single-link export required')
            raw = stream.read(LIMIT + 1)
            after = os.fstat(stream.fileno())
            named = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
            attributes = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_nlink',
                          'st_size', 'st_mtime_ns', 'st_ctime_ns')
            if (len(raw) > LIMIT
                    or any(getattr(before, a) != getattr(after, a) for a in attributes)
                    or (named.st_dev, named.st_ino) != (before.st_dev, before.st_ino)):
                raise ExportError('export changed while reading')
        _check_parent(path, parent)
        return raw
    finally:
        os.close(parent)


def validate_export(raw: bytes, expected_sha256: str) -> dict[str, Any]:
    """Verify an anchored historic export without its warehouse, DB, credentials or KMS key.

    The expected digest must come from separately retained evidence, not the same untrusted file.
    This authenticates no AWS response and proves no external storage persistence.
    """
    if (not re.fullmatch(r'[0-9a-f]{64}', expected_sha256) or len(raw) > LIMIT
            or hashlib.sha256(raw).hexdigest() != expected_sha256):
        raise ExportError('independent expected export digest mismatch')
    try:
        envelope = json.loads(raw)
        fields = {'schema_version', 'label', 'package', 'execution_id', 'creation_tags',
                  'records', 'last_record_sha256', 'exported_at_utc', 'cleanup_authorized',
                  'aws_proven', 'durable_retention_proven', 'export_sha256'}
        if (set(envelope) != fields or canonical(envelope) != raw
                or envelope['schema_version'] != '1.0.0' or envelope['label'] != LABEL
                or any(envelope[name] is not False for name in
                       ('cleanup_authorized', 'aws_proven', 'durable_retention_proven'))
                or digest({k: v for k, v in envelope.items() if k != 'export_sha256'})
                != envelope['export_sha256']):
            raise ExportError('export envelope or claim boundary mismatch')
        stamp = datetime.fromisoformat(envelope['exported_at_utc'])
        if stamp.tzinfo is None or stamp.utcoffset() != UTC.utcoffset(stamp):
            raise ExportError('UTC export timestamp required')
        package = envelope['package']
        if (package['execution_enabled'] is not False
                or digest({k: v for k, v in package.items() if k != 'package_sha256'})
                != package['package_sha256']):
            raise ExportError('historic package digest mismatch')
        execution_id = envelope['execution_id']
        if not re.fullmatch(r'[a-z0-9-]{8,64}', execution_id):
            raise ExportError('execution identity mismatch')
        records = envelope['records']
        if not isinstance(records, list) or not 1 <= len(records) <= 10000:
            raise ExportError('bounded nonempty record chain required')
        opening = {'package': package, 'execution_id': execution_id}
        tags = envelope['creation_tags']
        if tags is not None:
            opening['creation_tags'] = tags
        previous = None
        pending = None
        ack = False
        for number, row in enumerate(records, 1):
            if (set(row) != {'sequence', 'previous_sha256', 'package_sha256',
                             'execution_id', 'kind', 'payload', 'at_utc', 'sha256'}
                    or type(row['sequence']) is not int or row['sequence'] != number
                    or row['previous_sha256'] != previous
                    or row['execution_id'] != execution_id
                    or row['package_sha256'] != package['package_sha256']
                    or digest({k: v for k, v in row.items() if k != 'sha256'}) != row['sha256']):
                raise ExportError('historic record chain mismatch')
            stamp = datetime.fromisoformat(row['at_utc'])
            if stamp.tzinfo is None or stamp.utcoffset() != UTC.utcoffset(stamp):
                raise ExportError('UTC record timestamp required')
            payload = row['payload']
            if number == 1:
                if row['kind'] != 'OPEN' or payload != opening:
                    raise ExportError('historic opening mismatch')
            elif row['kind'] == 'INTENT':
                # The current journal supports only the unresolved first-key attempt. Do not
                # silently accept a future success/recovery transition or dependent write.
                step = package['steps'][0]
                request = json.loads(canonical(step['request']))
                if tags is not None:
                    request['Tags'] = [{'TagKey': t['TagKey'], 'TagValue': tags[t['TagKey']]}
                                       for t in request['Tags']]
                if (pending is not None or step['id'] != 'bootstrap-01'
                        or step['service'] != 'kms' or step['operation'] != 'create-key'
                        or step['depends_on'] or payload != {'step_id': step['id'],
                            'request': request, 'request_sha256': digest(request)}):
                    raise ExportError('historic intent outside supported attempt semantics')
                pending = payload['step_id']
            elif row['kind'] in {'ACKNOWLEDGEMENT', 'OBSERVATION'}:
                required = {'step_id', 'stdout', 'stderr'}
                if row['kind'] == 'ACKNOWLEDGEMENT':
                    required.add('returncode')
                    if ack or type(payload['returncode']) is not int:
                        raise ExportError('duplicate or invalid acknowledgement')
                    ack = True
                else:
                    required.add('configuration_verified')
                    if payload['configuration_verified'] is not False:
                        raise ExportError('observation cannot certify success')
                if pending is None or payload['step_id'] != pending or set(payload) != required:
                    raise ExportError('historic receipt identity mismatch')
                for name in ('stdout', 'stderr'):
                    receipt = payload[name]
                    if (set(receipt) != {'hex', 'sha256'}
                            or hashlib.sha256(bytes.fromhex(receipt['hex'])).hexdigest()
                            != receipt['sha256']):
                        raise ExportError('historic raw receipt digest mismatch')
            else:
                raise ExportError('unsupported historic success or recovery transition')
            previous = row['sha256']
        if previous != envelope['last_record_sha256']:
            raise ExportError('historic final record mismatch')
        return {'label': LABEL, 'file_sha256': expected_sha256,
                'package_sha256': package['package_sha256'], 'execution_id': execution_id,
                'record_count': len(records), 'last_record_sha256': previous,
                'pending_step': pending, 'cleanup_authorized': False, 'aws_proven': False,
                'durable_retention_proven': False}
    except ExportError:
        raise
    except (ValueError, KeyError, TypeError, IndexError, AttributeError) as error:
        raise ExportError('malformed historic export') from error


def verify_export(path: Path, expected_sha256: str) -> dict[str, Any]:
    return validate_export(_read(path), expected_sha256)


def export_journal(journal: MutationJournal, destination: Path) -> dict[str, Any]:
    """Freeze the durable chain under its writer lock; refuse overwrite or partial success."""
    rows = journal._load()
    if rows != journal.rows or journal._pending() != journal.pending:
        raise ExportError('journal memory differs from durable chain')
    # Export must be separate from the private source journal, not another file in it.
    destination = destination.absolute()
    if destination.parent.resolve().is_relative_to(journal.directory.resolve()):
        raise ExportError('export must be separate from the source journal directory')
    envelope = {'schema_version': '1.0.0', 'label': LABEL, 'package': journal.package,
                'execution_id': journal.bound_execution_id, 'creation_tags': journal.creation_tags,
                'records': rows, 'last_record_sha256': rows[-1]['sha256'],
                'exported_at_utc': datetime.now(UTC).isoformat(), 'cleanup_authorized': False,
                'aws_proven': False, 'durable_retention_proven': False}
    raw = canonical({**envelope, 'export_sha256': digest(envelope)})
    anchor = hashlib.sha256(raw).hexdigest()
    validate_export(raw, anchor)
    parent = _parent(destination)
    try:
        fd = os.open(destination.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=parent)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(parent)
        _check_parent(destination, parent)
        # Do not report export success if its source was altered during the write.
        if journal._load() != rows:
            raise ExportError('source chain changed during export')
        return verify_export(destination, anchor)
    finally:
        os.close(parent)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify', type=Path)
    parser.add_argument('--expected-sha256')
    parser.add_argument('--journal-directory', type=Path)
    parser.add_argument('--package', type=Path)
    parser.add_argument('--execution-id')
    parser.add_argument('--creation-tags', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        if args.verify is not None:
            if (args.expected_sha256 is None or any(x is not None for x in
                    (args.journal_directory, args.package, args.execution_id,
                     args.creation_tags, args.output))):
                parser.error('verify requires only a path and independently retained digest')
            result = verify_export(args.verify, args.expected_sha256)
        else:
            if (args.expected_sha256 is not None or any(x is None for x in
                    (args.journal_directory, args.package, args.execution_id, args.output))):
                parser.error('export requires journal, package, execution ID and output')
            verify_package(args.package)
            package = json.loads(_read(args.package))
            tags = json.loads(_read(args.creation_tags)) if args.creation_tags else None
            with MutationJournal(
                args.journal_directory, package, args.execution_id, tags
            ) as journal:
                result = export_journal(journal, args.output)
        print(json.dumps(result, sort_keys=True))
    except (OSError, ValueError) as error:
        # Receipt bytes, paths, email and AWS session identifiers must not enter terminal errors.
        print(json.dumps({'result': 'BLOCKED', 'error_type': type(error).__name__,
                          'cleanup_authorized': False, 'aws_proven': False}))
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
