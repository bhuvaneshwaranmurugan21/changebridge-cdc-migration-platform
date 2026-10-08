"""Bind KMS structural readbacks to a durable creation acknowledgement; never clear admission."""
from __future__ import annotations

from typing import Any

from scripts.prepare_stage33_bootstrap import canonical, compile_package, digest
from scripts.qualify_stage33_bootstrap import decode_response
from scripts.stage33_mutation_journal import MutationJournal
from scripts.verify_stage33_key_controls import verify_key_controls


class KeyAttemptError(ValueError):
    """An unresolved or unbound creation cannot authorize retry or key adoption."""


def inspect_key_attempt(journal: MutationJournal, observations: dict[str, Any],
                        execution_tags: dict[str, str]) -> dict[str, Any]:
    """Re-read the actual durable record chain rather than trusting mutable in-memory rows.

    A missing or nonzero acknowledgement stays unresolved, even if caller-supplied readbacks
    describe a matching key. This checks structural binding only. API provenance, lifecycle
    admission and operation-specific authoritative recovery still require the execution controller.
    """
    if journal.package != compile_package():
        raise KeyAttemptError('authority changed since creation intent; preserve and stop')
    rows = journal._load()
    if rows != journal.rows:
        raise KeyAttemptError('mutable memory differs from durable record chain')
    intents = [row for row in rows if row['kind'] == 'INTENT']
    acks = [row for row in rows if row['kind'] == 'ACKNOWLEDGEMENT']
    if (len(intents) != 1 or len(acks) != 1
            or intents[0]['payload']['step_id'] != 'bootstrap-01'
            or acks[0]['payload']['step_id'] != 'bootstrap-01'):
        raise KeyAttemptError('exact durable first-key creation acknowledgement required')
    expected = journal.package['steps'][0]
    if (expected['service'] != 'kms' or expected['operation'] != 'create-key'
            or intents[0]['payload']['request'] != journal._request(expected)
            or journal.creation_tags != execution_tags
            or execution_tags.get('ExecutionId') != journal.bound_execution_id):
        raise KeyAttemptError('creation request or execution ownership binding mismatch')
    acknowledgement = acks[0]['payload']
    if type(acknowledgement['returncode']) is not int or acknowledgement['returncode'] != 0:
        raise KeyAttemptError('nonzero or ambiguous CreateKey result; no adoption or retry')
    raw = bytes.fromhex(acknowledgement['stdout']['hex'])
    try:
        response = decode_response(raw)
        metadata = response['KeyMetadata']
        key_id = metadata['KeyId']
        created = metadata['CreationDate']
    except (ValueError, KeyError, TypeError) as error:
        message = 'creation acknowledgement lacks unambiguous physical identity'
        raise KeyAttemptError(message) from error
    controls = verify_key_controls(observations, key_id, execution_tags, created)
    # The acknowledgement must describe the same configured key as both readbacks. Use exactly
    # the same checker, retaining policy/tag readbacks because CreateKey does not return them.
    ack_view = {'metadata': response, 'policy': observations['before']['policy'],
                'tags': observations['before']['tags']}
    verify_key_controls({'before': ack_view, 'after': ack_view}, key_id, execution_tags, created)
    result = {
        'label': 'KEY_ATTEMPT_STRUCTURALLY_BOUND_NOT_AUTHORITATIVELY_RECOVERED',
        'package_sha256': journal.bound_package_sha256,
        'execution_id': journal.bound_execution_id,
        'intent_record_sha256': intents[0]['sha256'], 'ack_record_sha256': acks[0]['sha256'],
        'ack_stdout_sha256': acknowledgement['stdout']['sha256'],
        'controls_sha256': controls['controls_sha256'],
        'observations_sha256': controls['observations_sha256'],
        'key_id': key_id, 'key_arn': controls['controls']['key']['Arn'],
        'mutation_pending': True, 'key_use_authorized': False, 'retry_authorized': False,
        'limitations': controls['limitations'],
    }
    result['comparison_sha256'] = digest(result)
    # Store a raw comparison receipt only. The existing OBSERVATION transition explicitly cannot
    # certify configuration or clear the pending mutation; no success state is introduced.
    journal.observe('bootstrap-01', canonical(result), b'')
    return result
