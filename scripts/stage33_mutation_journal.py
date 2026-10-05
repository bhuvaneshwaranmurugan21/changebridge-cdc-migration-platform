"""Durable mutation-attempt records. Recording is not permission, execution or AWS proof."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import sqlite3
import stat
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.prepare_stage33_bootstrap import canonical, compile_package, digest
from scripts.validate_part3_stage3 import ROOT


class MutationJournalError(ValueError):
    """Unsafe, ambiguous or mismatched attempts remain blocked."""


class MutationJournal:
    """Freeze requests and receipts; never execute writes or turn observations into success.

    A single global unresolved attempt prevents recording another mutation. Even a zero-return
    acknowledgement requires operation-specific authoritative verification outside this component.
    Observations preserve raw bytes; they certify neither origin nor configuration.
    """

    def __init__(self, directory: Path, package: dict[str, Any], execution_id: str) -> None:
        alphabet = 'abcdefghijklmnopqrstuvwxyz0123456789-'
        if not execution_id or any(c not in alphabet for c in execution_id):
            raise MutationJournalError('invalid execution identity')
        if len(execution_id) < 8 or len(execution_id) > 64:
            raise MutationJournalError('invalid execution identity length')
        directory = directory.absolute()
        if directory.resolve().is_relative_to(ROOT.resolve()):
            raise MutationJournalError('private journal must remain outside the Git worktree')
        self.directory = directory
        self.directory_fd: int | None = None
        self.lock_fd: int | None = None
        self.connection: sqlite3.Connection | None = None
        frozen = json.loads(canonical(package))
        payload = {k: v for k, v in frozen.items() if k != 'package_sha256'}
        if frozen.get('package_sha256') != digest(payload):
            raise MutationJournalError('package digest mismatch')
        if frozen.get('execution_enabled') is not False:
            raise MutationJournalError('offline packages only; no execution approval')
        if frozen != compile_package():
            message = 'immutable package or execution identity mismatch: stale scope'
            raise MutationJournalError(message)
        self.package = frozen
        self.bound_package_sha256 = frozen['package_sha256']
        self.bound_execution_id = execution_id
        self.execution_id = execution_id
        with suppress(FileExistsError):
            directory.mkdir(mode=0o700)
        info = directory.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
                or info.st_mode & 0o777 != 0o700):
            raise MutationJournalError('private owned directory required')
        try:
            self.directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            pinned = os.fstat(self.directory_fd)
            self.directory_identity = (pinned.st_dev, pinned.st_ino)
            if (info.st_dev, info.st_ino) != (pinned.st_dev, pinned.st_ino):
                raise MutationJournalError('directory substituted')
            self.lock_fd = os.open('writer.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
                                   0o600, dir_fd=self.directory_fd)
            self._check_private(self.lock_fd)
            fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            # Anchor SQLite to the held directory, not a pathname that can be renamed/substituted.
            db_name = 'attempts.sqlite3'
            created = True
            try:
                fd = os.open(db_name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=self.directory_fd)
            except FileExistsError:
                created = False
                fd = os.open(db_name, os.O_RDWR | os.O_NOFOLLOW, dir_fd=self.directory_fd)
            try:
                self._check_private(fd)
                db_info = os.fstat(fd)
                self.database_identity = (db_info.st_dev, db_info.st_ino)
            finally:
                os.close(fd)
            for suffix in ('-journal', '-wal', '-shm'):
                try:
                    sidecar = os.open(db_name + suffix, os.O_RDONLY | os.O_NOFOLLOW,
                                      dir_fd=self.directory_fd)
                except FileNotFoundError:
                    continue
                try:
                    self._check_private(sidecar)
                    if suffix != '-journal':
                        raise MutationJournalError('unexpected WAL sidecar; preserve and stop')
                finally:
                    os.close(sidecar)
            db_path = f'/proc/self/fd/{self.directory_fd}/{db_name}'
            self.connection = sqlite3.connect(db_path, timeout=0, isolation_level=None)
            actual = os.stat(db_name, dir_fd=self.directory_fd, follow_symlinks=False)
            if (actual.st_dev, actual.st_ino) != (db_info.st_dev, db_info.st_ino):
                raise MutationJournalError('database substituted')
            schema = ('CREATE TABLE records '
                      '(sequence INTEGER PRIMARY KEY, record BLOB NOT NULL)')
            if not created:
                actual_schema = self.connection.execute(
                    'SELECT type,name,sql FROM sqlite_master ORDER BY name'
                ).fetchall()
                if actual_schema != [('table', 'records', schema)]:
                    raise MutationJournalError('unknown journal schema; do not adopt')
            self.connection.execute('PRAGMA journal_mode=DELETE')
            self.connection.execute('PRAGMA synchronous=FULL')
            self.connection.execute('PRAGMA foreign_keys=ON')
            if created:
                self.connection.execute(schema)
            os.fsync(self.directory_fd)
            if self.connection.execute('PRAGMA integrity_check').fetchone() != ('ok',):
                raise MutationJournalError('SQLite integrity failure')
            self.rows = self._load()
            if not self.rows and not created:
                raise MutationJournalError('missing durable opening; preserve incomplete database')
            if not self.rows:
                self._append('OPEN', {'package': frozen, 'execution_id': execution_id})
            elif self.rows[0]['payload'] != {'package': frozen, 'execution_id': execution_id}:
                raise MutationJournalError('immutable package or execution identity mismatch')
            self.pending = self._pending()
        except BaseException:
            self.close()
            raise

    @staticmethod
    def _check_private(fd: int) -> None:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_mode & 0o777 != 0o600 or info.st_nlink != 1):
            raise MutationJournalError('private single-link regular file required')

    def _db(self) -> sqlite3.Connection:
        if self.connection is None or self.directory_fd is None:
            raise MutationJournalError('closed journal')
        named = self.directory.lstat()
        if (not stat.S_ISDIR(named.st_mode)
                or (named.st_dev, named.st_ino) != self.directory_identity):
            raise MutationJournalError('journal directory replaced or renamed; stop before SQL')
        fd = os.open('attempts.sqlite3', os.O_RDONLY | os.O_NOFOLLOW,
                     dir_fd=self.directory_fd)
        try:
            self._check_private(fd)
            named_database = os.fstat(fd)
            if (named_database.st_dev, named_database.st_ino) != self.database_identity:
                raise MutationJournalError('journal database identity changed')
        finally:
            os.close(fd)
        if (digest({k: v for k, v in self.package.items() if k != 'package_sha256'})
                != self.bound_package_sha256 or self.execution_id != self.bound_execution_id):
            raise MutationJournalError('in-memory package or execution binding changed')
        for suffix in ('-journal', '-wal', '-shm'):
            try:
                sidecar = os.open('attempts.sqlite3' + suffix, os.O_RDONLY | os.O_NOFOLLOW,
                                  dir_fd=self.directory_fd)
            except FileNotFoundError:
                continue
            try:
                self._check_private(sidecar)
                if suffix != '-journal':
                    raise MutationJournalError('unexpected WAL sidecar; preserve and stop')
            finally:
                os.close(sidecar)
        return self.connection

    def _load(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        previous = None
        query = 'SELECT sequence,record FROM records ORDER BY sequence'
        for number, raw in self._db().execute(query):
            try:
                row = json.loads(raw)
                if set(row) != {'sequence', 'previous_sha256', 'package_sha256',
                                'execution_id', 'kind', 'payload', 'at_utc', 'sha256'}:
                    raise MutationJournalError('unexpected record fields')
                stamp = datetime.fromisoformat(row['at_utc'])
                if stamp.tzinfo is None or stamp.utcoffset() != UTC.utcoffset(stamp):
                    raise MutationJournalError('UTC receipt timestamp required')
                claimed = row['sha256']
                inner = {k: v for k, v in row.items() if k != 'sha256'}
                if (row['package_sha256'] != self.package['package_sha256']
                        or row['execution_id'] != self.execution_id):
                    raise MutationJournalError('immutable package or execution identity mismatch')
                if (canonical(row) != raw or number != len(rows) + 1
                        or row['sequence'] != number or row['previous_sha256'] != previous
                        or row['package_sha256'] != self.package['package_sha256']
                        or row['execution_id'] != self.execution_id or digest(inner) != claimed):
                    raise MutationJournalError('record chain/binding mismatch')
                if number == 1 and row['kind'] != 'OPEN':
                    raise MutationJournalError('opening missing')
                if row['kind'] not in {'OPEN', 'INTENT', 'ACKNOWLEDGEMENT', 'OBSERVATION'}:
                    raise MutationJournalError('unsupported success/recovery state')
                rows.append(row)
                previous = claimed
            except MutationJournalError:
                raise
            except (KeyError, TypeError, ValueError) as error:
                raise MutationJournalError('malformed record') from error
        return rows

    def _pending(self) -> dict[str, Any] | None:
        pending = None
        acknowledged = False
        for row in self.rows[1:]:
            payload = row['payload']
            if row['kind'] == 'INTENT':
                if pending is not None:
                    raise MutationJournalError('overlapping mutation attempts')
                step = next(
                    (s for s in self.package['steps'] if s['id'] == payload['step_id']), None
                )
                if step is None or payload != {'step_id': step['id'], 'request': step['request'],
                                              'request_sha256': digest(step['request'])}:
                    raise MutationJournalError('intent outside frozen package')
                pending = payload
            elif row['kind'] in {'ACKNOWLEDGEMENT', 'OBSERVATION'}:
                if pending is None or payload.get('step_id') != pending['step_id']:
                    raise MutationJournalError('receipt without matching intent')
                expected_fields = {'step_id', 'stdout', 'stderr'}
                if row['kind'] == 'ACKNOWLEDGEMENT':
                    expected_fields.add('returncode')
                    if acknowledged or type(payload.get('returncode')) is not int:
                        raise MutationJournalError('duplicate or malformed acknowledgement')
                    acknowledged = True
                else:
                    expected_fields.add('configuration_verified')
                    if payload.get('configuration_verified') is not False:
                        raise MutationJournalError('observation cannot certify configuration')
                if set(payload) != expected_fields:
                    raise MutationJournalError('unexpected receipt fields')
                for field in ('stdout', 'stderr'):
                    encoded = payload[field]
                    raw = bytes.fromhex(encoded['hex'])
                    if hashlib.sha256(raw).hexdigest() != encoded['sha256']:
                        raise MutationJournalError('raw receipt digest mismatch')
            else:
                raise MutationJournalError('unexpected state transition')
        return pending

    def _append(self, kind: str, payload: dict[str, Any]) -> None:
        row = {'sequence': len(self.rows) + 1,
               'previous_sha256': self.rows[-1]['sha256'] if self.rows else None,
               'package_sha256': self.package['package_sha256'],
               'execution_id': self.execution_id, 'kind': kind, 'payload': payload,
               'at_utc': datetime.now(UTC).isoformat()}
        row['sha256'] = digest(row)
        connection = self._db()
        connection.execute('BEGIN IMMEDIATE')
        try:
            connection.execute('INSERT INTO records VALUES (?,?)',
                               (row['sequence'], canonical(row)))
            connection.execute('COMMIT')
        except BaseException:
            if connection.in_transaction:
                connection.execute('ROLLBACK')
            raise
        self.rows.append(json.loads(canonical(row)))

    def intent(self, step_id: str) -> None:
        """Record exact unresolved request durably; this method sends no AWS operation."""
        if self.pending is not None:
            raise MutationJournalError('unresolved mutation; execution/retry remains blocked')
        step = next((s for s in self.package['steps'] if s['id'] == step_id), None)
        if step is None:
            raise MutationJournalError('step outside immutable package')
        if step['depends_on']:
            raise MutationJournalError('prerequisite readbacks are not verified; recording blocked')
        self._append('INTENT', {'step_id': step_id, 'request': step['request'],
                                'request_sha256': digest(step['request'])})
        self.pending = self._pending()

    @staticmethod
    def _raw(raw: bytes) -> dict[str, str]:
        return {'hex': raw.hex(), 'sha256': hashlib.sha256(raw).hexdigest()}

    def acknowledge(self, step_id: str, returncode: int, stdout: bytes, stderr: bytes) -> None:
        if self.pending is None or step_id != self.pending['step_id']:
            raise MutationJournalError('acknowledgement identity mismatch')
        if type(returncode) is not int:
            raise MutationJournalError('integer returncode required')
        if any(row['kind'] == 'ACKNOWLEDGEMENT' for row in self.rows):
            raise MutationJournalError('acknowledgement already preserved; never overwrite')
        self._append('ACKNOWLEDGEMENT', {'step_id': step_id, 'returncode': returncode,
                                       'stdout': self._raw(stdout), 'stderr': self._raw(stderr)})
        # Zero returncode is not configuration proof and must not clear pending.

    def observe(self, step_id: str, stdout: bytes, stderr: bytes) -> None:
        if self.pending is None or step_id != self.pending['step_id']:
            raise MutationJournalError('observation identity mismatch')
        self._append('OBSERVATION', {'step_id': step_id, 'stdout': self._raw(stdout),
                                   'stderr': self._raw(stderr), 'configuration_verified': False})

    def close(self) -> None:
        if self.connection is not None:
            self.connection.close()
            self.connection = None
        for name in ('lock_fd', 'directory_fd'):
            fd = getattr(self, name)
            if fd is not None:
                os.close(fd)
                setattr(self, name, None)

    def __enter__(self) -> MutationJournal:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
