"""Synthetic storage comparisons do not certify AWS bucket ownership or backend operations."""
import copy
import json

import pytest

from scripts.prepare_stage33_bootstrap import ACCOUNT, ARTIFACT, KEY, REGION, STATE, compile_package
from scripts.verify_stage33_storage_controls import StorageControlsError, verify_storage_controls
from tests.test_stage33_key_controls import CREATED, TAGS

ARN = f'arn:aws:kms:{REGION}:{ACCOUNT}:key/12345678-1234-1234-1234-123456789abc'


def observations(bucket=STATE):
    logical = 'state-bucket' if bucket == STATE else 'artifact-bucket'
    ops = {s['operation']: s['request'] for s in compile_package()['steps']
           if s['resource'] == logical}
    responses = {
        'head': {'BucketRegion': REGION}, 'location': {'LocationConstraint': REGION},
        'versioning': ops['put-bucket-versioning']['VersioningConfiguration'],
        'public_access': {'PublicAccessBlockConfiguration':
                          ops['put-public-access-block']['PublicAccessBlockConfiguration']},
        'ownership': {'OwnershipControls': {'Rules': [{'ObjectOwnership': 'BucketOwnerEnforced'}]}},
        'encryption': {'ServerSideEncryptionConfiguration':
                       ops['put-bucket-encryption']['ServerSideEncryptionConfiguration']},
        'policy': {'Policy': ops['put-bucket-policy']['Policy']},
        'tags': {'TagSet': [{'Key': k, 'Value': v} for k, v in TAGS.items()]},
    }
    enc = responses['encryption']['ServerSideEncryptionConfiguration']['Rules'][0]
    assert enc['ApplyServerSideEncryptionByDefault']['KMSMasterKeyID'] == KEY
    enc['ApplyServerSideEncryptionByDefault']['KMSMasterKeyID'] = ARN
    snapshot = {k: {'request': {'Bucket': bucket, 'ExpectedBucketOwner': ACCOUNT}, 'response': v}
                for k, v in responses.items()}
    return {'before': copy.deepcopy(snapshot), 'after': copy.deepcopy(snapshot)}


@pytest.mark.parametrize('bucket', [STATE, ARTIFACT])
def test_exact_controls_never_authorize_storage(bucket):
    result = verify_storage_controls(observations(bucket), bucket, ARN, TAGS, CREATED)
    assert result['storage_use_authorized'] is False


@pytest.mark.parametrize('section', ['head', 'location', 'versioning', 'public_access',
                                     'ownership', 'encryption', 'policy', 'tags'])
def test_missing_or_unbound_response_rejected(section):
    source = observations()
    source['after'][section]['request']['ExpectedBucketOwner'] = 'foreign'
    with pytest.raises(StorageControlsError):
        verify_storage_controls(source, STATE, ARN, TAGS, CREATED)
    source = observations()
    del source['after'][section]
    with pytest.raises(StorageControlsError):
        verify_storage_controls(source, STATE, ARN, TAGS, CREATED)


@pytest.mark.parametrize('section,response', [
    ('head', {'BucketRegion': 'us-east-1'}), ('location', {'LocationConstraint': None}),
    ('versioning', {'Status': 'Suspended'}),
    ('ownership', {'OwnershipControls': {'Rules': [{'ObjectOwnership': 'ObjectWriter'}]}}),
    ('policy', {'Policy': '{"Statement":[],"Statement":{}}'}),
    ('policy', {'Policy': '{}'}), ('tags', {'TagSet': []}),
])
def test_changed_security_controls_rejected(section, response):
    source = observations()
    source['after'][section]['response'] = response
    with pytest.raises(ValueError):
        verify_storage_controls(source, STATE, ARN, TAGS, CREATED)


@pytest.mark.parametrize('value', [False, 1])
def test_public_access_flags_require_true_boolean(value):
    source = observations()
    source['before']['public_access']['response']['PublicAccessBlockConfiguration'][
        'BlockPublicPolicy'] = value
    with pytest.raises(StorageControlsError):
        verify_storage_controls(source, STATE, ARN, TAGS, CREATED)


@pytest.mark.parametrize('value', ['alias/changebridge-p3s3-state', KEY, 'foreign'])
def test_encryption_requires_exact_physical_key(value):
    source = observations()
    config = source['after']['encryption']['response']['ServerSideEncryptionConfiguration']
    rule = config['Rules'][0]
    rule['ApplyServerSideEncryptionByDefault']['KMSMasterKeyID'] = value
    with pytest.raises(StorageControlsError):
        verify_storage_controls(source, STATE, ARN, TAGS, CREATED)


def test_duplicate_tags_and_non_boolean_bucket_key_rejected():
    source = observations()
    rows = source['after']['tags']['response']['TagSet']
    rows.append(rows[0])
    with pytest.raises(StorageControlsError):
        verify_storage_controls(source, STATE, ARN, TAGS, CREATED)
    source = observations()
    config = source['after']['encryption']['response']['ServerSideEncryptionConfiguration']
    rule = config['Rules'][0]
    rule['BucketKeyEnabled'] = 0
    with pytest.raises(StorageControlsError):
        verify_storage_controls(source, STATE, ARN, TAGS, CREATED)


def test_foreign_bucket_and_unresolved_creation_rejected():
    with pytest.raises(StorageControlsError):
        verify_storage_controls(observations(), 'another-project', ARN, TAGS, CREATED)
    with pytest.raises(ValueError):
        verify_storage_controls(observations(), STATE, ARN, TAGS, 'unknown')
    source = observations()
    source['after']['policy']['response']['Policy'] = json.loads(
        source['after']['policy']['response']['Policy'])
    result = verify_storage_controls(source, STATE, ARN, TAGS, CREATED)
    assert result['storage_use_authorized'] is False
