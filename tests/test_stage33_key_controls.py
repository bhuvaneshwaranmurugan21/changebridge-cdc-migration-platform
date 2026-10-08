"""Synthetic KMS comparisons never satisfy live admission or recovery criteria."""
import copy
import json

import pytest

from scripts.prepare_stage33_bootstrap import ACCOUNT, REGION, compile_package
from scripts.verify_stage33_key_controls import KeyControlsError, verify_key_controls

KEY = '12345678-1234-1234-1234-123456789abc'
CREATED = '2026-10-05T00:00:00Z'
TAGS = {'Project': 'ChangeBridge', 'Owner': 'bhuvaneshwaranmurugan21', 'Stage': 'part3-stage3',
        'CostCenter': 'changebridge-p3s3', 'ExpiresAt': '2026-10-07T00:00:00Z',
        'ExecutionId': 'synthetic-run-5678'}


def observations():
    request = compile_package()['steps'][0]['request']
    row = {'metadata': {'KeyMetadata': {
        'Arn': f'arn:aws:kms:{REGION}:{ACCOUNT}:key/{KEY}', 'AWSAccountId': ACCOUNT,
        'KeyId': KEY, 'CreationDate': CREATED, 'KeyManager': 'CUSTOMER',
        'KeySpec': 'SYMMETRIC_DEFAULT', 'KeyUsage': 'ENCRYPT_DECRYPT', 'Origin': 'AWS_KMS',
        'KeyState': 'Enabled', 'Enabled': True, 'MultiRegion': False,
        'Description': request['Description'], 'EncryptionAlgorithms': ['SYMMETRIC_DEFAULT']}},
        'policy': {'PolicyName': 'default', 'Policy': request['Policy']},
        'tags': {'Truncated': False, 'Tags': [{'TagKey': k, 'TagValue': v}
                                             for k, v in TAGS.items()]}}
    return {'before': copy.deepcopy(row), 'after': copy.deepcopy(row)}


def test_match_never_authorizes_key_use():
    source = observations()
    result = verify_key_controls(source, KEY, TAGS, CREATED)
    assert result['key_use_authorized'] is False
    assert result['label'] == 'STRUCTURAL_KEY_MATCH_NOT_ADMISSION_PROOF'
    source['before']['metadata']['KeyMetadata']['KeyId'] = 'foreign'
    assert result['controls']['key']['KeyId'] == KEY


@pytest.mark.parametrize('field,value', [
    ('Arn', 'foreign'), ('AWSAccountId', 'foreign'), ('KeyId', 'foreign'),
    ('CreationDate', '2026-10-05T00:00:01Z'), ('KeyManager', 'AWS'),
    ('KeySpec', 'RSA_2048'), ('KeyUsage', 'SIGN_VERIFY'), ('Origin', 'EXTERNAL'),
    ('KeyState', 'PendingDeletion'), ('Enabled', 1), ('MultiRegion', 0),
    ('Description', 'foreign'), ('EncryptionAlgorithms', []),
    ('DeletionDate', None), ('MultiRegionConfiguration', {}), ('CustomKeyStoreId', 'foreign'),
])
def test_key_identity_and_state_rejected(field, value):
    source = observations()
    source['after']['metadata']['KeyMetadata'][field] = value
    with pytest.raises(KeyControlsError):
        verify_key_controls(source, KEY, TAGS, CREATED)


@pytest.mark.parametrize('change', ['missing', 'truncated', 'marker', 'duplicate', 'foreign'])
def test_complete_exact_tags_required(change):
    source = observations()
    tags = source['before']['tags']
    if change == 'missing':
        del tags['Truncated']
    elif change == 'truncated':
        tags['Truncated'] = True
    elif change == 'marker':
        tags['NextMarker'] = 'continuation'
    elif change == 'duplicate':
        tags['Tags'].append(tags['Tags'][0])
    else:
        tags['Tags'][0]['TagValue'] = 'foreign'
    with pytest.raises(KeyControlsError):
        verify_key_controls(source, KEY, TAGS, CREATED)


@pytest.mark.parametrize('expiry', ['2026-10-07T00:00:01Z', CREATED,
                                    '2026-10-06T00:00:00', '__UNRESOLVED__'])
def test_creation_bound_lifetime_required(expiry):
    with pytest.raises(KeyControlsError):
        verify_key_controls(observations(), KEY, {**TAGS, 'ExpiresAt': expiry}, CREATED)


@pytest.mark.parametrize('policy', ['{"Statement":[],"Statement":{}}', '{}', 'not-json'])
def test_policy_cannot_be_weakened_or_ambiguous(policy):
    source = observations()
    source['after']['policy']['Policy'] = policy
    with pytest.raises(KeyControlsError):
        verify_key_controls(source, KEY, TAGS, CREATED)


def test_no_discovery_or_partial_readback_adoption():
    source = observations()
    del source['after']['policy']
    with pytest.raises(KeyControlsError):
        verify_key_controls(source, KEY, TAGS, CREATED)
    with pytest.raises(KeyControlsError):
        verify_key_controls(observations(), 'alias/changebridge-p3s3-state', TAGS, CREATED)
    source = observations()
    source['after']['policy']['Policy'] = json.loads(source['after']['policy']['Policy'])
    assert verify_key_controls(source, KEY, TAGS, CREATED)['key_use_authorized'] is False
