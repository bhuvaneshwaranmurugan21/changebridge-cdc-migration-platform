"""Exact S3 configuration comparison, not ownership provenance or managed storage proof."""
from __future__ import annotations

import json
import re
from typing import Any

from scripts.prepare_stage33_bootstrap import (
    ACCOUNT,
    ARTIFACT,
    KEY,
    REGION,
    STATE,
    canonical,
    compile_package,
    digest,
)
from scripts.verify_stage33_key_controls import _policy, _utc


class StorageControlsError(ValueError):
    """Unbound owner, controls, encryption, tags or readbacks cannot qualify storage."""


def verify_storage_controls(observations: dict[str, Any], bucket: str, key_arn: str,
                            execution_tags: dict[str, str], creation_date: str) -> dict[str, Any]:
    """Require exact request bindings and complete before/after controls for one owned bucket.

    Each section must bind its response to the exact Bucket and ExpectedBucketOwner request.
    Those caller-supplied bindings are structurally checked, not authenticated. HeadBucket and
    CreationDate alone cannot prove that this execution created the bucket or prevent name reuse.
    No bucket discovery, adoption, creation, deletion or object operation is performed.
    """
    if bucket not in (STATE, ARTIFACT):
        raise StorageControlsError('bucket outside exact ChangeBridge scope')
    pattern = (rf'arn:aws:kms:{REGION}:{ACCOUNT}:key/'
               r'[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}')
    if not isinstance(key_arn, str) or not re.fullmatch(pattern, key_arn):
        raise StorageControlsError('exact physical encryption key required')
    names = {'Project', 'Owner', 'Stage', 'CostCenter', 'ExpiresAt', 'ExecutionId'}
    tags = execution_tags
    if (set(tags) != names or tags['Project'] != 'ChangeBridge'
            or tags['Owner'] != 'bhuvaneshwaranmurugan21' or tags['Stage'] != 'part3-stage3'
            or tags['CostCenter'] != 'changebridge-p3s3'
            or not all(isinstance(v, str) and v and '__' not in v for v in tags.values())
            or not re.fullmatch(r'[a-z0-9-]{8,64}', tags['ExecutionId'])):
        raise StorageControlsError('exact resolved execution ownership required')
    lifetime = (_utc(tags['ExpiresAt']) - _utc(creation_date)).total_seconds()
    if not 0 < lifetime <= 48 * 3600:
        raise StorageControlsError('creation-bound expiry exceeds operational window')
    logical = 'state-bucket' if bucket == STATE else 'artifact-bucket'
    steps = [s for s in compile_package()['steps'] if s['resource'] == logical]
    by_operation = {s['operation']: s['request'] for s in steps}
    owner_request = {'Bucket': bucket, 'ExpectedBucketOwner': ACCOUNT}
    expected = {
        'location': {'LocationConstraint': REGION},
        'versioning': by_operation['put-bucket-versioning']['VersioningConfiguration'],
        'public_access': {'PublicAccessBlockConfiguration':
                          by_operation['put-public-access-block']['PublicAccessBlockConfiguration']},
        'ownership': {'OwnershipControls': {'Rules': [{'ObjectOwnership':
                     by_operation['create-bucket']['ObjectOwnership']}]}},
        'encryption': {'ServerSideEncryptionConfiguration':
                       by_operation['put-bucket-encryption']['ServerSideEncryptionConfiguration']},
    }
    # Bind the exact physical key; never accept an alias, wildcard, foreign key or unbound template.
    encryption = expected['encryption']['ServerSideEncryptionConfiguration']['Rules']
    if encryption[0]['ApplyServerSideEncryptionByDefault']['KMSMasterKeyID'] != KEY:
        raise StorageControlsError('encryption authority drift')
    encryption[0]['ApplyServerSideEncryptionByDefault']['KMSMasterKeyID'] = key_arn
    expected_policy = _policy(by_operation['put-bucket-policy']['Policy'])
    sections = {'head', 'location', 'versioning', 'public_access', 'ownership',
                'encryption', 'policy', 'tags'}
    if set(observations) != {'before', 'after'}:
        raise StorageControlsError('before and after controls required')
    for phase in ('before', 'after'):
        snapshot = observations[phase]
        if not isinstance(snapshot, dict) or set(snapshot) != sections:
            raise StorageControlsError('complete bucket controls required')
        responses = {}
        for name, row in snapshot.items():
            if (not isinstance(row, dict) or set(row) != {'request', 'response'}
                    or row['request'] != owner_request or not isinstance(row['response'], dict)):
                raise StorageControlsError('exact owner-bound readback required')
            responses[name] = row['response']
        head = responses['head']
        if head.get('BucketRegion') != REGION:
            raise StorageControlsError('head bucket region mismatch')
        # Ignore CLI transport metadata only; unsupported additional service controls are rejected.
        for name, value in expected.items():
            actual = {k: v for k, v in responses[name].items() if k != 'ResponseMetadata'}
            if actual != value:
                raise StorageControlsError(name + ' configuration mismatch')
        # Python treats 0 == False and 1 == True; security control booleans require actual bools.
        pab = responses['public_access']['PublicAccessBlockConfiguration']
        if any(type(v) is not bool for v in pab.values()):
            raise StorageControlsError('public access controls require Booleans')
        rule = responses['encryption']['ServerSideEncryptionConfiguration']['Rules'][0]
        if type(rule.get('BucketKeyEnabled')) is not bool:
            raise StorageControlsError('bucket key control requires Boolean')
        if _policy(responses['policy'].get('Policy')) != expected_policy:
            raise StorageControlsError('bucket policy widened or changed')
        rows = responses['tags'].get('TagSet')
        if not isinstance(rows, list):
            raise StorageControlsError('complete ownership tags required')
        actual_tags: dict[str, str] = {}
        for row in rows:
            if (not isinstance(row, dict) or set(row) != {'Key', 'Value'}
                    or not isinstance(row['Key'], str) or not isinstance(row['Value'], str)
                    or row['Key'] in actual_tags):
                raise StorageControlsError('duplicate or malformed bucket tags')
            actual_tags[row['Key']] = row['Value']
        if actual_tags != tags:
            raise StorageControlsError('bucket execution ownership mismatch')
    controls = json.loads(canonical({'bucket': bucket, 'expected_owner': ACCOUNT,
                                     'creation_date': creation_date, 'controls': expected,
                                     'policy': expected_policy, 'tags': tags}))
    return {'label': 'STRUCTURAL_STORAGE_MATCH_NOT_ADMISSION_PROOF',
            'storage_use_authorized': False, 'controls': controls,
            'controls_sha256': digest(controls), 'observations_sha256': digest(observations),
            'limitations': ['API origin, request provenance and creation ownership not certified',
                            'before/after reads are not atomic or bucket-name ABA protection',
                            'object version/checksum and cryptographic backend use not proven',
                            'expiry tags do not enforce deletion']}
