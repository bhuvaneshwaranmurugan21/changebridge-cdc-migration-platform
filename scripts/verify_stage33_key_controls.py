"""Compare exact KMS readbacks; this component cannot discover, adopt or authorize a key."""
from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

from scripts.prepare_stage33_bootstrap import ACCOUNT, REGION, canonical, compile_package, digest


class KeyControlsError(ValueError):
    """Ambiguous identity, policy, ownership or pagination remains blocked."""


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise KeyControlsError('duplicate policy key')
        result[key] = value
    return result


def _policy(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value, object_pairs_hook=_pairs)
        except ValueError as error:
            raise KeyControlsError('malformed key policy') from error
    if not isinstance(value, dict):
        raise KeyControlsError('key policy object required')
    return value


def _utc(value: Any) -> datetime:
    if not isinstance(value, str):
        raise KeyControlsError('explicit UTC timestamp required')
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as error:
        raise KeyControlsError('explicit UTC timestamp required') from error
    if result.tzinfo is None or result.utcoffset() != UTC.utcoffset(result):
        raise KeyControlsError('explicit UTC timestamp required')
    return result


def verify_key_controls(observations: dict[str, Any], key_id: str,
                        execution_tags: dict[str, str], creation_date: str) -> dict[str, Any]:
    """Compare two complete snapshots against an independently bound creation receipt.

    A key ID supplied by a caller is not evidence of ownership. A missing creation receipt,
    lost CreateKey acknowledgement or ambiguous candidate search cannot be resolved here.
    Separate reads do not form an atomic snapshot and no mutation is executed.
    """
    if not isinstance(key_id, str) or not re.fullmatch(
            r'[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}', key_id):
        raise KeyControlsError('exact physical key UUID required')
    arn = f'arn:aws:kms:{REGION}:{ACCOUNT}:key/{key_id}'
    tags = execution_tags
    names = {'Project', 'Owner', 'Stage', 'CostCenter', 'ExpiresAt', 'ExecutionId'}
    if (set(tags) != names or tags['Project'] != 'ChangeBridge'
            or tags['Owner'] != 'bhuvaneshwaranmurugan21' or tags['Stage'] != 'part3-stage3'
            or tags['CostCenter'] != 'changebridge-p3s3'
            or not all(isinstance(v, str) and v and '__' not in v for v in tags.values())
            or not re.fullmatch(r'[a-z0-9-]{8,64}', tags['ExecutionId'])):
        raise KeyControlsError('exact resolved execution tags required')
    created = _utc(creation_date)
    lifetime = (_utc(tags['ExpiresAt']) - created).total_seconds()
    if not 0 < lifetime <= 48 * 3600:
        raise KeyControlsError('expiry must be within 48 hours of actual creation')
    package = compile_package()
    first = package['steps'][0]
    if first['operation'] != 'create-key' or first['resource'] != 'state-key':
        raise KeyControlsError('key creation authority drift')
    request = first['request']
    expected_policy = _policy(request['Policy'])
    expected = {'Arn': arn, 'AWSAccountId': ACCOUNT, 'KeyId': key_id,
                'KeyManager': 'CUSTOMER', 'KeySpec': 'SYMMETRIC_DEFAULT',
                'KeyUsage': 'ENCRYPT_DECRYPT', 'Origin': 'AWS_KMS',
                'KeyState': 'Enabled', 'Enabled': True, 'MultiRegion': False,
                'Description': request['Description'],
                'EncryptionAlgorithms': ['SYMMETRIC_DEFAULT']}
    if set(observations) != {'before', 'after'}:
        raise KeyControlsError('before and after readbacks required')
    for phase in ('before', 'after'):
        snapshot = observations[phase]
        if not isinstance(snapshot, dict) or set(snapshot) != {'metadata', 'policy', 'tags'}:
            raise KeyControlsError('complete key readbacks required')
        metadata_response = snapshot['metadata']
        metadata = (metadata_response.get('KeyMetadata')
                    if isinstance(metadata_response, dict) else None)
        if (not isinstance(metadata, dict)
                or any(metadata.get(k) != v for k, v in expected.items())
                or type(metadata.get('Enabled')) is not bool
                or type(metadata.get('MultiRegion')) is not bool
                or _utc(metadata.get('CreationDate')) != created
                or any(k in metadata for k in ('DeletionDate', 'PendingDeletionWindowInDays',
                                              'CustomKeyStoreId', 'MultiRegionConfiguration',
                                              'XksKeyConfiguration', 'ValidTo'))):
            raise KeyControlsError('key identity/state/origin/creation mismatch')
        policy = snapshot['policy']
        if (not isinstance(policy, dict) or policy.get('PolicyName') != 'default'
                or _policy(policy.get('Policy')) != expected_policy):
            raise KeyControlsError('key policy mismatch')
        inventory = snapshot['tags']
        if (not isinstance(inventory, dict) or inventory.get('Truncated') is not False
                or 'NextMarker' in inventory or 'Marker' in inventory
                or 'NextToken' in inventory or not isinstance(inventory.get('Tags'), list)):
            raise KeyControlsError('complete tag inventory required')
        actual: dict[str, str] = {}
        for tag in inventory['Tags']:
            if (not isinstance(tag, dict) or set(tag) != {'TagKey', 'TagValue'}
                    or not isinstance(tag['TagKey'], str)
                    or not isinstance(tag['TagValue'], str) or tag['TagKey'] in actual):
                raise KeyControlsError('duplicate or malformed ownership tags')
            actual[tag['TagKey']] = tag['TagValue']
        if actual != tags:
            raise KeyControlsError('execution ownership mismatch')
    controls = json.loads(canonical({'key': expected, 'creation_date': creation_date,
                                      'policy': expected_policy, 'tags': tags}))
    return {'label': 'STRUCTURAL_KEY_MATCH_NOT_ADMISSION_PROOF', 'key_use_authorized': False,
            'controls': controls, 'controls_sha256': digest(controls),
            'observations_sha256': digest(observations),
            'limitations': ['API origin and creation receipt provenance not certified here',
                            'separate KMS reads are not atomic',
                            'lost CreateKey acknowledgement is unresolved; no blind retry',
                            'actual backend cryptographic use and cleanup not proven']}
