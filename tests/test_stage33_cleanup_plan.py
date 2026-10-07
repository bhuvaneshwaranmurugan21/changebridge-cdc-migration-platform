"""Offline selector tests; synthetic inventory is not observed AWS ownership."""
import copy

import pytest

from scripts.prepare_stage33_bootstrap import ACCOUNT, LOCKS, REGION, ROLE, STATE, TOPIC
from scripts.prepare_stage33_cleanup import CleanupPlanError, cleanup_plan


def inventory():
    key = '12345678-1234-1234-1234-123456789abc'
    return {'account_id': ACCOUNT, 'region': REGION, 'execution_id': 'local-test-1234',
            'resources': {
                'state_key': {'arn': f'arn:aws:kms:{REGION}:{ACCOUNT}:key/{key}', 'key_id': key},
                'state_alias': {'name': 'alias/changebridge-p3s3-state', 'target_key_id': key},
                'state_bucket': {'name': STATE, 'creation_date': 'synthetic-observation',
                                 'versions': [{'Key': 'changebridge/part3/stage3/terraform.tfstate',
                                               'VersionId': 'synthetic-version'}]},
                'alert_email': {'subscription_arn': f'{TOPIC}:{key}',
                                'pending_confirmation': False},
                'github_actions_role': {'arn': f'arn:aws:iam::{ACCOUNT}:role/{ROLE}',
                                        'role_id': 'AROA' + 'A' * 17,
                                        'inline_policy_name': 'ChangeBridgeStage33Backend'},
            }}


def test_order_identity_freezing_and_no_execution():
    source = inventory()
    plan = cleanup_plan(source)
    operations = [step['operation'] for step in plan['steps']]
    assert operations == ['update-assume-role-policy', 'delete-role-policy', 'unsubscribe',
                          'delete-object', 'delete-bucket', 'delete-alias',
                          'schedule-key-deletion', 'delete-role']
    assert plan['execution_enabled'] is False
    assert plan['steps'][-2]['request']['PendingWindowInDays'] == 7
    assert all(step['mandatory_actual_guards'] for step in plan['steps'])
    frozen = copy.deepcopy(plan)
    source['resources']['github_actions_role']['role_id'] = 'changed'
    assert plan == frozen


@pytest.mark.parametrize('field,value', [('account_id', 'foreign'), ('region', 'foreign'),
                                         ('execution_id', '../unsafe')])
def test_binding_rejection(field, value):
    source = inventory()
    source[field] = value
    with pytest.raises(CleanupPlanError):
        cleanup_plan(source)


@pytest.mark.parametrize('version', [
    {'Key': 'foreign/project', 'VersionId': 'v'},
    {'Key': 'changebridge/part3/stage3/terraform.tfstate', 'VersionId': 'null'},
    {'Key': 'changebridge/part3/stage3/terraform.tfstate', 'VersionId': ''},
    {'Key': 'changebridge/part3/stage3/terraform.tfstate'},
])
def test_unbounded_or_unrecoverable_version_rejected(version):
    source = inventory()
    source['resources']['state_bucket']['versions'] = [version]
    with pytest.raises(CleanupPlanError):
        cleanup_plan(source)


def test_duplicate_versions_rejected():
    source = inventory()
    versions = source['resources']['state_bucket']['versions']
    versions.append(copy.deepcopy(versions[0]))
    with pytest.raises(CleanupPlanError):
        cleanup_plan(source)


@pytest.mark.parametrize('logical,field,value', [
    ('state_alias', 'target_key_id', 'foreign'),
    ('state_key', 'arn', 'foreign'),
    ('github_actions_role', 'role_id', 'unknown'),
    ('alert_email', 'subscription_arn', 'PendingConfirmation'),
])
def test_unproven_resource_identity_rejected(logical, field, value):
    source = inventory()
    source['resources'][logical][field] = value
    with pytest.raises(CleanupPlanError):
        cleanup_plan(source)


def test_partial_inventory_never_proves_omitted_absence():
    source = inventory()
    source['resources'] = {'alert_email': source['resources']['alert_email']}
    plan = cleanup_plan(source)
    assert len(plan['steps']) == 1
    limitation = 'partial inventories do not establish absence of omitted resources'
    assert limitation in plan['limitations']


def test_returned_pending_arn_never_becomes_confirmed_unsubscribe():
    source = inventory()
    source['resources']['alert_email']['pending_confirmation'] = True
    with pytest.raises(CleanupPlanError, match='owned topic disposal'):
        cleanup_plan(source)
    source['resources']['alerts'] = {'arn': TOPIC}
    plan = cleanup_plan(source)
    assert all(step['operation'] != 'unsubscribe' for step in plan['steps'])
    assert any(step['operation'] == 'delete-topic' for step in plan['steps'])
    assert plan['execution_enabled'] is False
    assert 'pending subscription disposal does not satisfy confirmed alert admission' in (
        plan['limitations'])


def test_arn_without_explicit_boolean_confirmation_state_is_unknown():
    for state in (None, 0, 'false'):
        source = inventory()
        if state is None:
            del source['resources']['alert_email']['pending_confirmation']
        else:
            source['resources']['alert_email']['pending_confirmation'] = state
        with pytest.raises(CleanupPlanError, match='confirmation state'):
            cleanup_plan(source)


def test_pitr_retirement_preserves_admission_then_precedes_table_deletion():
    source = inventory()
    source['resources']['state_locks'] = {
        'arn': f'arn:aws:dynamodb:{REGION}:{ACCOUNT}:table/{LOCKS}',
        'table_id': '12345678-1234-1234-1234-123456789abc',
    }
    plan = cleanup_plan(source)
    table_steps = [s for s in plan['steps'] if s['resource'] == 'state_locks']
    assert [s['operation'] for s in table_steps] == [
        'update-continuous-backups', 'delete-table']
    assert table_steps[0]['request']['PointInTimeRecoverySpecification'] == {
        'PointInTimeRecoveryEnabled': False}
    assert table_steps[1]['depends_on'] == [table_steps[0]['id']]
    assert 'PITR admission already proven and original evidence preserved' in (
        table_steps[0]['mandatory_actual_guards'])
    assert 'final state exported and independently verified before retirement' in (
        table_steps[0]['mandatory_actual_guards'])
    assert 'fresh PITR DISABLED state; no unapproved system-backup residual' in (
        table_steps[1]['mandatory_actual_guards'])
    assert plan['execution_enabled'] is False
