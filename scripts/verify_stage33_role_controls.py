"""Exact dedicated-role readback comparison; local matches alone never certify AWS admission."""
from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import unquote

from scripts.prepare_stage33_bootstrap import ACCOUNT, REGION, ROLE, canonical, digest
from scripts.validate_part3_stage3 import ROOT, Stage33Error, validate_proposed_policies

POLICY_NAME = 'ChangeBridgeStage33Backend'
ROLE_ARN = f'arn:aws:iam::{ACCOUNT}:role/{ROLE}'
KEY_PATTERN = (rf'arn:aws:kms:{REGION}:{ACCOUNT}:key/'
               r'[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}')


class RoleControlsError(ValueError):
    """Incomplete, widened or drifting security controls cannot qualify role use."""


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RoleControlsError('duplicate JSON policy key')
        result[key] = value
    return result


def policy_document(value: Any) -> dict[str, Any]:
    """Accept decoded SDK JSON or one RFC3986 encoding; preserve literal plus characters."""
    if isinstance(value, str):
        try:
            value = json.loads(unquote(value, errors='strict'), object_pairs_hook=_unique_pairs)
        except (ValueError, UnicodeError) as error:
            raise RoleControlsError('malformed IAM policy document') from error
    if not isinstance(value, dict):
        raise RoleControlsError('IAM policy must be a JSON object')
    return value


def expected_permissions(key_arn: str) -> dict[str, Any]:
    try:
        validate_proposed_policies()
    except Stage33Error as error:
        raise RoleControlsError('proposed policy authority drifted') from error
    if not re.fullmatch(KEY_PATTERN, key_arn):
        raise RoleControlsError('exact account/region-bound physical KMS key ARN required')
    proposal = json.loads((ROOT / 'deployment/stage3/role-permissions.proposed.json').read_text())
    policy = proposal['policy']
    placeholder = '__BIND_EXACT_KMS_KEY_ARN_FROM_VERIFIED_BOOTSTRAP_RECEIPT__'
    matches = [s for s in policy['Statement'] if s.get('Resource') == placeholder]
    if len(matches) != 2:
        raise RoleControlsError('KMS template binding drifted')
    for statement in matches:
        statement['Resource'] = key_arn
    return dict(policy)


def _tags(value: Any) -> dict[str, str]:
    if not isinstance(value, list):
        raise RoleControlsError('complete execution tags required')
    result: dict[str, str] = {}
    for row in value:
        if (not isinstance(row, dict) or set(row) != {'Key', 'Value'}
                or not isinstance(row['Key'], str) or not isinstance(row['Value'], str)
                or row['Key'] in result):
            raise RoleControlsError('malformed or duplicate role tags')
        result[row['Key']] = row['Value']
    return result


def verify_role_controls(
    observations: dict[str, Any], role_id: str, key_arn: str, execution_tags: dict[str, str]
) -> dict[str, Any]:
    """Compare before/after control snapshots; observations are not atomic or authenticated here.

    Required sections are role, inline_inventory, attached_inventory and inline_document, each
    observed before and after. Expected RoleId and KMS ARN must originate in independently verified
    bootstrap identities; this comparator does not establish that provenance or authorize adoption.
    Pagination must be explicitly complete; absent flags, markers and extra policies are rejected.
    """
    if not re.fullmatch(r'AROA[A-Z0-9]{17}', role_id):
        raise RoleControlsError('independently bound immutable RoleId required')
    tag_names = {'Project', 'Owner', 'Stage', 'CostCenter', 'ExpiresAt', 'ExecutionId'}
    resolved_values = all(isinstance(v, str) and v and '__' not in v
                          for v in execution_tags.values())
    if (set(execution_tags) != tag_names
            or execution_tags['Project'] != 'ChangeBridge'
            or execution_tags['Owner'] != 'bhuvaneshwaranmurugan21'
            or execution_tags['Stage'] != 'part3-stage3'
            or execution_tags['CostCenter'] != 'changebridge-p3s3'
            or not resolved_values):
        raise RoleControlsError('exact resolved execution tags required')
    try:
        expiry = datetime.fromisoformat(execution_tags['ExpiresAt'].replace('Z', '+00:00'))
    except ValueError as error:
        raise RoleControlsError('valid UTC expiry tag required') from error
    if expiry.tzinfo is None or expiry.utcoffset() != UTC.utcoffset(expiry):
        raise RoleControlsError('valid UTC expiry tag required')
    if not re.fullmatch(r'[a-z0-9-]{8,64}', execution_tags['ExecutionId']):
        raise RoleControlsError('valid execution identity tag required')
    expected = expected_permissions(key_arn)
    trust_path = ROOT / 'deployment/stage3/oidc-trust-policy.proposed.json'
    trust = json.loads(trust_path.read_text())['policy']
    snapshots = []
    if set(observations) != {'before', 'after'}:
        raise RoleControlsError('before and after observations required')
    for phase in ('before', 'after'):
        snapshot = observations[phase]
        if (not isinstance(snapshot, dict) or set(snapshot) != {
                'role', 'inline_inventory', 'attached_inventory', 'inline_document'}):
            raise RoleControlsError('complete security observation required')
        role = snapshot['role'].get('Role') if isinstance(snapshot['role'], dict) else None
        if not isinstance(role, dict):
            raise RoleControlsError('actual dedicated role is absent or malformed')
        if (role.get('Arn') != ROLE_ARN or role.get('RoleId') != role_id
                or role.get('RoleName') != ROLE or role.get('Path') != '/'
                or type(role.get('MaxSessionDuration')) is not int
                or role['MaxSessionDuration'] != 3600 or role.get('PermissionsBoundary') is not None
                or policy_document(role.get('AssumeRolePolicyDocument')) != trust
                or _tags(role.get('Tags')) != execution_tags):
            raise RoleControlsError('role identity/trust/boundary/session/tags mismatch')
        for field, key, required in (
            ('inline_inventory', 'PolicyNames', [POLICY_NAME]),
            ('attached_inventory', 'AttachedPolicies', []),
        ):
            inventory = snapshot[field]
            if (not isinstance(inventory, dict) or inventory.get('IsTruncated') is not False
                    or 'Marker' in inventory or 'NextToken' in inventory
                    or inventory.get(key) != required):
                raise RoleControlsError('incomplete or unexpected role policy inventory')
        inline = snapshot['inline_document']
        if (not isinstance(inline, dict) or inline.get('RoleName') != ROLE
                or inline.get('PolicyName') != POLICY_NAME
                or policy_document(inline.get('PolicyDocument')) != expected):
            raise RoleControlsError('inline policy identity or permissions mismatch')
        snapshots.append({'role_id': role_id, 'role_arn': ROLE_ARN, 'trust': trust,
                          'permissions': expected, 'boundary': None, 'tags': execution_tags,
                          'max_session_duration': 3600})
    if snapshots[0] != snapshots[1]:
        raise RoleControlsError('security controls drifted during observation')
    # Freeze references. This is a comparator result, not proof of API origin, role effectiveness,
    # permission boundaries elsewhere, current IAM consistency or actual OIDC assumption.
    controls = json.loads(canonical(snapshots[0]))
    return {'label': 'STRUCTURAL_CONTROL_MATCH_NOT_ADMISSION_PROOF',
            'role_use_authorized': False, 'controls': controls,
            'controls_sha256': digest(controls), 'observations_sha256': digest(observations),
            'limitations': ['separate reads are not an atomic IAM snapshot',
                            'API origin and immutable identity provenance not certified here',
                            'actual OIDC assumption and allowed/denied operations not proven']}
