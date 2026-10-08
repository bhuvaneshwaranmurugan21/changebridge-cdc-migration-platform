"""Synthetic lock-table readbacks test comparisons, never real backend locks."""
import copy

import pytest

from scripts.prepare_stage33_bootstrap import ACCOUNT, LOCKS, REGION, compile_package
from scripts.verify_stage33_lock_controls import LockControlsError, verify_lock_controls
from tests.test_stage33_key_controls import CREATED, KEY, TAGS

ARN = f'arn:aws:kms:{REGION}:{ACCOUNT}:key/{KEY}'
TABLE_ARN = f'arn:aws:dynamodb:{REGION}:{ACCOUNT}:table/{LOCKS}'


def observations():
    request = next(s['request'] for s in compile_package()['steps']
                   if s['operation'] == 'create-table')
    table = {'TableArn': TABLE_ARN, 'TableName': LOCKS, 'TableId': KEY, 'TableStatus': 'ACTIVE',
             'CreationDateTime': CREATED, 'KeySchema': request['KeySchema'],
             'AttributeDefinitions': request['AttributeDefinitions'],
             'BillingModeSummary': {'BillingMode': 'PAY_PER_REQUEST'},
             'DeletionProtectionEnabled': False,
             'SSEDescription': {'Status': 'ENABLED', 'SSEType': 'KMS', 'KMSMasterKeyArn': ARN}}
    responses = {'table': {'Table': table}, 'backups': {'ContinuousBackupsDescription': {
        'ContinuousBackupsStatus': 'ENABLED', 'PointInTimeRecoveryDescription': {
            'PointInTimeRecoveryStatus': 'ENABLED'}}},
        'tags': {'Tags': [{'Key': k, 'Value': v} for k, v in TAGS.items()]}}
    snapshot = {k: {'request': {'ResourceArn': TABLE_ARN} if k == 'tags' else {'TableName': LOCKS},
                    'response': v} for k, v in responses.items()}
    return {'before': copy.deepcopy(snapshot), 'after': copy.deepcopy(snapshot)}


def test_controls_cannot_authorize_locks():
    result = verify_lock_controls(observations(), KEY, ARN, TAGS, CREATED)
    assert result['lock_use_authorized'] is False


@pytest.mark.parametrize('field,value', [
    ('TableArn', 'foreign'), ('TableId', 'foreign'), ('TableName', 'foreign'),
    ('TableStatus', 'UPDATING'), ('CreationDateTime', '2026-10-05T00:00:01Z'),
    ('KeySchema', []), ('AttributeDefinitions', []),
    ('BillingModeSummary', {'BillingMode': 'PROVISIONED'}),
    ('DeletionProtectionEnabled', True), ('DeletionProtectionEnabled', 0),
    ('SSEDescription', {'Status': 'UPDATING', 'SSEType': 'KMS', 'KMSMasterKeyArn': ARN}),
    ('Replicas', [{}]), ('GlobalSecondaryIndexes', [{}]),
    ('StreamSpecification', {'StreamEnabled': True}),
])
def test_table_control_drift_rejected(field, value):
    source = observations()
    source['after']['table']['response']['Table'][field] = value
    with pytest.raises(LockControlsError):
        verify_lock_controls(source, KEY, ARN, TAGS, CREATED)


@pytest.mark.parametrize('section', ['table', 'backups', 'tags'])
def test_unbound_readback_rejected(section):
    source = observations()
    source['before'][section]['request'] = {'TableName': 'foreign'}
    with pytest.raises(LockControlsError):
        verify_lock_controls(source, KEY, ARN, TAGS, CREATED)


def test_pitr_incomplete_tags_and_duplicates_rejected():
    source = observations()
    source['after']['backups']['response']['ContinuousBackupsDescription'][
        'PointInTimeRecoveryDescription']['PointInTimeRecoveryStatus'] = 'DISABLED'
    with pytest.raises(LockControlsError):
        verify_lock_controls(source, KEY, ARN, TAGS, CREATED)
    source = observations()
    source['after']['tags']['response']['NextToken'] = ''
    with pytest.raises(LockControlsError):
        verify_lock_controls(source, KEY, ARN, TAGS, CREATED)
    source = observations()
    tags = source['before']['tags']['response']['Tags']
    tags.append(tags[0])
    with pytest.raises(LockControlsError):
        verify_lock_controls(source, KEY, ARN, TAGS, CREATED)


@pytest.mark.parametrize('field', ['BillingModeSummary', 'StreamSpecification'])
def test_malformed_nested_controls_rejected(field):
    source = observations()
    source['before']['table']['response']['Table'][field] = None
    with pytest.raises(LockControlsError):
        verify_lock_controls(source, KEY, ARN, TAGS, CREATED)


def test_malformed_backup_controls_rejected():
    source = observations()
    source['after']['backups']['response']['ContinuousBackupsDescription'][
        'PointInTimeRecoveryDescription'] = None
    with pytest.raises(LockControlsError):
        verify_lock_controls(source, KEY, ARN, TAGS, CREATED)
