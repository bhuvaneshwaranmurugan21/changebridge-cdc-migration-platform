"""Compare exact lock-table readbacks without certifying creation, recovery or AWS origin."""
from __future__ import annotations

import json
import re
from typing import Any

from scripts.prepare_stage33_bootstrap import (
    ACCOUNT,
    LOCKS,
    REGION,
    canonical,
    compile_package,
    digest,
)
from scripts.verify_stage33_key_controls import _utc


class LockControlsError(ValueError):
    """Table identity, encryption, backups or ownership drift blocks use."""


def verify_lock_controls(observations: dict[str, Any], table_id: str, key_arn: str,
                         execution_tags: dict[str, str], creation_date: str) -> dict[str, Any]:
    """TableId plus creation time prevents structural name-only adoption; origin is external."""
    uuid = r'[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}'
    if (not isinstance(table_id, str) or not re.fullmatch(uuid, table_id)
            or not isinstance(key_arn, str)
            or not re.fullmatch(rf'arn:aws:kms:{REGION}:{ACCOUNT}:key/{uuid}', key_arn)):
        raise LockControlsError('independently bound physical table and key required')
    tags = execution_tags
    names = {'Project', 'Owner', 'Stage', 'CostCenter', 'ExpiresAt', 'ExecutionId'}
    if (set(tags) != names or tags['Project'] != 'ChangeBridge'
            or tags['Owner'] != 'bhuvaneshwaranmurugan21' or tags['Stage'] != 'part3-stage3'
            or tags['CostCenter'] != 'changebridge-p3s3'
            or not all(isinstance(v, str) and v and '__' not in v for v in tags.values())
            or not re.fullmatch(r'[a-z0-9-]{8,64}', tags['ExecutionId'])):
        raise LockControlsError('exact execution ownership tags required')
    created = _utc(creation_date)
    if not 0 < (_utc(tags['ExpiresAt']) - created).total_seconds() <= 48 * 3600:
        raise LockControlsError('creation-bound 48-hour expiry required')
    package = compile_package()
    create = next(s['request'] for s in package['steps']
                  if s['resource'] == 'state-locks' and s['operation'] == 'create-table')
    arn = f'arn:aws:dynamodb:{REGION}:{ACCOUNT}:table/{LOCKS}'
    expected = {'TableArn': arn, 'TableName': LOCKS, 'TableId': table_id,
                'TableStatus': 'ACTIVE', 'KeySchema': create['KeySchema'],
                'AttributeDefinitions': create['AttributeDefinitions']}
    if set(observations) != {'before', 'after'}:
        raise LockControlsError('before and after readbacks required')
    for phase in ('before', 'after'):
        row = observations[phase]
        if not isinstance(row, dict) or set(row) != {'table', 'backups', 'tags'}:
            raise LockControlsError('complete table/backups/tags readbacks required')
        for name in row:
            request = {'ResourceArn': arn} if name == 'tags' else {'TableName': LOCKS}
            if (not isinstance(row[name], dict) or set(row[name]) != {'request', 'response'}
                    or row[name]['request'] != request
                    or not isinstance(row[name]['response'], dict)):
                raise LockControlsError('exact table-bound request required')
        table = row['table']['response'].get('Table')
        if (not isinstance(table, dict) or any(table.get(k) != v for k, v in expected.items())
                or _utc(table.get('CreationDateTime')) != created
                or not isinstance(table.get('BillingModeSummary'), dict)
                or table['BillingModeSummary'].get('BillingMode') != 'PAY_PER_REQUEST'
                or table.get('DeletionProtectionEnabled') is not False
                or table.get('SSEDescription') != {
                    'Status': 'ENABLED', 'SSEType': 'KMS', 'KMSMasterKeyArn': key_arn}
                or any(table.get(k) for k in ('GlobalSecondaryIndexes', 'LocalSecondaryIndexes',
                                              'Replicas', 'GlobalTableVersion', 'RestoreSummary',
                                              'LatestStreamArn', 'VectorIndexes'))
                or not isinstance(table.get('StreamSpecification', {}), dict)
                or table.get('StreamSpecification', {}).get('StreamEnabled', False) is not False):
            raise LockControlsError('table identity/schema/billing/encryption/lifecycle mismatch')
        backups = row['backups']['response'].get('ContinuousBackupsDescription')
        if (not isinstance(backups, dict) or backups.get('ContinuousBackupsStatus') != 'ENABLED'
                or not isinstance(backups.get('PointInTimeRecoveryDescription'), dict)
                or backups['PointInTimeRecoveryDescription'].get(
                    'PointInTimeRecoveryStatus') != 'ENABLED'):
            raise LockControlsError('enabled PITR readback required')
        inventory = row['tags']['response']
        if 'NextToken' in inventory or not isinstance(inventory.get('Tags'), list):
            raise LockControlsError('complete unpaginated tag inventory required')
        actual: dict[str, str] = {}
        for tag in inventory['Tags']:
            if (not isinstance(tag, dict) or set(tag) != {'Key', 'Value'}
                    or not isinstance(tag['Key'], str) or not isinstance(tag['Value'], str)
                    or tag['Key'] in actual):
                raise LockControlsError('malformed or duplicate tags')
            actual[tag['Key']] = tag['Value']
        if actual != tags:
            raise LockControlsError('execution ownership mismatch')
    controls = json.loads(canonical({'table': expected, 'key_arn': key_arn,
                                     'creation_date': creation_date, 'tags': tags,
                                     'billing': 'PAY_PER_REQUEST', 'pitr': 'ENABLED'}))
    return {'label': 'STRUCTURAL_LOCK_MATCH_NOT_ADMISSION_PROOF', 'lock_use_authorized': False,
            'controls': controls, 'controls_sha256': digest(controls),
            'observations_sha256': digest(observations),
            'limitations': ['API origin and immutable creation receipt not certified',
                            'separate reads are not atomic',
                            'actual lock acquisition, contention and cryptographic use not proven',
                            'PITR readiness and expiry tags do not prove cleanup enforcement']}
