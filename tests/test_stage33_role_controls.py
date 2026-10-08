"""Synthetic policy comparisons are checker tests, never managed IAM/OIDC proof."""
import copy
import json
from urllib.parse import quote

import pytest

from scripts.prepare_stage33_bootstrap import ACCOUNT, REGION, ROLE
from scripts.validate_part3_stage3 import ROOT
from scripts.verify_stage33_role_controls import (
    POLICY_NAME,
    ROLE_ARN,
    RoleControlsError,
    expected_permissions,
    policy_document,
    verify_role_controls,
)

KEY = f'arn:aws:kms:{REGION}:{ACCOUNT}:key/12345678-1234-1234-1234-123456789abc'
ROLE_ID = 'AROA' + 'A' * 17
TAGS = {'Project': 'ChangeBridge', 'Owner': 'bhuvaneshwaranmurugan21', 'Stage': 'part3-stage3',
        'CostCenter': 'changebridge-p3s3', 'ExpiresAt': '2026-10-06T00:00:00Z',
        'ExecutionId': 'synthetic-run-1234'}


def observations():
    trust = json.loads((ROOT / 'deployment/stage3/oidc-trust-policy.proposed.json').read_text())
    snapshot = {
        'role': {'Role': {'Arn': ROLE_ARN, 'RoleId': ROLE_ID, 'RoleName': ROLE, 'Path': '/',
                          'MaxSessionDuration': 3600, 'AssumeRolePolicyDocument': trust['policy'],
                          'Tags': [{'Key': k, 'Value': v} for k, v in TAGS.items()]}},
        'inline_inventory': {'PolicyNames': [POLICY_NAME], 'IsTruncated': False},
        'attached_inventory': {'AttachedPolicies': [], 'IsTruncated': False},
        'inline_document': {'RoleName': ROLE, 'PolicyName': POLICY_NAME,
                            'PolicyDocument': expected_permissions(KEY)},
    }
    return {'before': copy.deepcopy(snapshot), 'after': copy.deepcopy(snapshot)}


def test_full_comparison_cannot_authorize_role_use():
    source = observations()
    result = verify_role_controls(source, ROLE_ID, KEY, TAGS)
    assert result['label'] == 'STRUCTURAL_CONTROL_MATCH_NOT_ADMISSION_PROOF'
    assert result['role_use_authorized'] is False
    assert result['controls']['permissions'] == expected_permissions(KEY)
    source['before']['role']['Role']['Arn'] = 'changed'
    assert result['controls']['role_arn'] == ROLE_ARN


def test_rfc3986_sdk_and_duplicate_key_handling():
    raw = {'Version': '2012-10-17', 'Statement': [{'Sid': 'literal+plus'}]}
    assert policy_document(quote(json.dumps(raw), safe='')) == raw
    assert policy_document(json.dumps(raw)) == raw
    with pytest.raises(RoleControlsError):
        policy_document('{"Effect":"Deny","Effect":"Allow"}')
    with pytest.raises(RoleControlsError):
        policy_document('not-json')


@pytest.mark.parametrize('field,value', [
    ('Arn', 'foreign'), ('RoleId', 'AROA' + 'B' * 17), ('RoleName', 'another'),
    ('Path', '/foreign/'), ('MaxSessionDuration', True), ('MaxSessionDuration', 7200),
    ('PermissionsBoundary', {'PermissionsBoundaryArn': 'foreign'}),
])
def test_role_control_drift_rejected(field, value):
    source = observations()
    source['after']['role']['Role'][field] = value
    with pytest.raises(RoleControlsError):
        verify_role_controls(source, ROLE_ID, KEY, TAGS)


@pytest.mark.parametrize('field', ['inline_inventory', 'attached_inventory'])
@pytest.mark.parametrize('pagination', ['truncated', 'missing', 'marker'])
def test_incomplete_pagination_rejected(field, pagination):
    source = observations()
    value = source['before'][field]
    if pagination == 'truncated':
        value['IsTruncated'] = True
    elif pagination == 'missing':
        del value['IsTruncated']
    else:
        value['Marker'] = 'more'
    with pytest.raises(RoleControlsError, match='inventory'):
        verify_role_controls(source, ROLE_ID, KEY, TAGS)


def test_extra_permission_or_wildcard_trust_rejected():
    source = observations()
    source['after']['inline_document']['PolicyDocument']['Statement'].append({
        'Effect': 'Allow', 'Action': '*', 'Resource': '*'})
    with pytest.raises(RoleControlsError, match='permissions'):
        verify_role_controls(source, ROLE_ID, KEY, TAGS)
    source = observations()
    document = source['after']['role']['Role']['AssumeRolePolicyDocument']
    document['Statement'][0]['Condition']['StringEquals'][
        'token.actions.githubusercontent.com:sub'] = 'repo:*'
    with pytest.raises(RoleControlsError, match='trust'):
        verify_role_controls(source, ROLE_ID, KEY, TAGS)


@pytest.mark.parametrize('value', ['*', 'alias/changebridge-p3s3-state', 'foreign',
                                 KEY.replace(REGION, 'us-east-1'),
                                 KEY.replace(ACCOUNT, '123456789012')])
def test_physical_key_scope_required(value):
    with pytest.raises(RoleControlsError):
        verify_role_controls(observations(), ROLE_ID, value, TAGS)


def test_absent_role_missing_sections_tags_and_extra_policies_rejected():
    for alteration in ('absent', 'section', 'tags', 'inline', 'attached'):
        source = observations()
        if alteration == 'absent':
            source['before']['role'] = None
        elif alteration == 'section':
            del source['before']['inline_document']
        elif alteration == 'tags':
            tags = source['before']['role']['Role']['Tags']
            tags.append(copy.deepcopy(tags[0]))
        elif alteration == 'inline':
            source['before']['inline_inventory']['PolicyNames'].append('unknown')
        else:
            attached = source['before']['attached_inventory']['AttachedPolicies']
            attached.append({'PolicyArn': 'foreign'})
        with pytest.raises(RoleControlsError):
            verify_role_controls(source, ROLE_ID, KEY, TAGS)


def test_cli_truncation_token_and_invalid_binding_tags_are_rejected():
    source = observations()
    source['before']['inline_inventory']['NextToken'] = 'more'
    with pytest.raises(RoleControlsError, match='inventory'):
        verify_role_controls(source, ROLE_ID, KEY, TAGS)
    for field, value in [('ExpiresAt', 'not-a-date'), ('ExpiresAt', '2026-10-06T00:00:00'),
                         ('ExecutionId', '../foreign')]:
        tags = {**TAGS, field: value}
        with pytest.raises(RoleControlsError):
            verify_role_controls(observations(), ROLE_ID, KEY, tags)


@pytest.mark.parametrize('field,value', [
    ('kms:ViaService', 'dynamodb.us-east-1.amazonaws.com'),
    ('kms:EncryptionContext:aws:dynamodb:tableName', 'foreign-project-table'),
    ('kms:EncryptionContext:aws:dynamodb:subscriberId', '123456789012'),
])
def test_lock_table_key_decryption_cannot_escape_exact_context(field, value):
    source = observations()
    policy = source['after']['inline_document']['PolicyDocument']
    statement = next(s for s in policy['Statement']
                     if s['Sid'] == 'ExactLockTableKeyDecryptViaRegionalDynamoDBOnly')
    statement['Condition']['StringEquals'][field] = value
    with pytest.raises(RoleControlsError, match='permissions'):
        verify_role_controls(source, ROLE_ID, KEY, TAGS)


def test_lock_table_key_cannot_gain_grant_or_direct_decryption_permissions():
    for alteration in ('create_grant', 'missing_condition', 'wildcard_key'):
        source = observations()
        policy = source['after']['inline_document']['PolicyDocument']
        statement = next(s for s in policy['Statement']
                         if s['Sid'] == 'ExactLockTableKeyDecryptViaRegionalDynamoDBOnly')
        if alteration == 'create_grant':
            statement['Action'] = ['kms:Decrypt', 'kms:CreateGrant']
        elif alteration == 'missing_condition':
            del statement['Condition']
        else:
            statement['Resource'] = '*'
        with pytest.raises(RoleControlsError, match='permissions'):
            verify_role_controls(source, ROLE_ID, KEY, TAGS)


@pytest.mark.parametrize('alteration', ['context', 'actions', 'resource'])
def test_drifted_expected_template_cannot_legitimize_weaker_controls(
    tmp_path, monkeypatch, alteration
):
    from scripts import validate_part3_stage3 as authority

    source = observations()
    for name in ('role-permissions.proposed.json', 'oidc-trust-policy.proposed.json'):
        path = tmp_path / 'deployment/stage3' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((ROOT / 'deployment/stage3' / name).read_bytes())
    path = tmp_path / 'deployment/stage3/role-permissions.proposed.json'
    template = json.loads(path.read_text())
    statement = next(s for s in template['policy']['Statement']
                     if s['Sid'] == 'ExactLockTableKeyDecryptViaRegionalDynamoDBOnly')
    if alteration == 'context':
        del statement['Condition']['StringEquals']['kms:EncryptionContext:aws:dynamodb:tableName']
    elif alteration == 'actions':
        statement['Action'] = ['kms:Decrypt', 'kms:CreateGrant']
    else:
        statement['Resource'] = '*'
    path.write_text(json.dumps(template))
    monkeypatch.setattr(authority, 'ROOT', tmp_path)
    with pytest.raises(RoleControlsError, match='authority drifted'):
        verify_role_controls(source, ROLE_ID, KEY, TAGS)
