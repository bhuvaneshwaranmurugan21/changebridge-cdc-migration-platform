"""Real durable journal integration using explicitly synthetic AWS-shaped receipts."""
import json

import pytest

from scripts.prepare_stage33_bootstrap import canonical, compile_package
from scripts.reconcile_stage33_key_attempt import KeyAttemptError, inspect_key_attempt
from scripts.stage33_mutation_journal import MutationJournal, MutationJournalError
from tests.test_stage33_key_controls import TAGS, observations


def opened(tmp_path):
    journal = MutationJournal(tmp_path / 'key-attempt', compile_package(),
                              TAGS['ExecutionId'], creation_tags=TAGS)
    journal.intent('bootstrap-01')
    return journal


def test_durable_ack_readbacks_cannot_clear_mutation(tmp_path):
    source = observations()
    with opened(tmp_path) as journal:
        journal.acknowledge('bootstrap-01', 0, canonical(source['before']['metadata']), b'')
        result = inspect_key_attempt(journal, source, TAGS)
        assert result['mutation_pending'] is True
        assert result['key_use_authorized'] is False
        assert result['retry_authorized'] is False
        with pytest.raises(MutationJournalError):
            journal.intent('bootstrap-01')
    with MutationJournal(
            tmp_path / 'key-attempt', compile_package(),
            TAGS['ExecutionId'], creation_tags=TAGS) as journal:
        assert journal.pending is not None
        assert journal.rows[-1]['payload']['configuration_verified'] is False
        stored = bytes.fromhex(journal.rows[-1]['payload']['stdout']['hex'])
        assert json.loads(stored)['comparison_sha256'] == result['comparison_sha256']


def test_missing_ack_matching_tags_does_not_adopt_key(tmp_path):
    with opened(tmp_path) as journal:
        with pytest.raises(KeyAttemptError):
            inspect_key_attempt(journal, observations(), TAGS)
        assert journal.pending is not None


@pytest.mark.parametrize('returncode', [1, 124, 127])
def test_nonzero_create_result_cannot_be_inferred_success(tmp_path, returncode):
    with opened(tmp_path) as journal:
        raw = canonical(observations()['before']['metadata'])
        journal.acknowledge('bootstrap-01', returncode, raw,
                            b'unknown outcome')
        with pytest.raises(KeyAttemptError):
            inspect_key_attempt(journal, observations(), TAGS)


@pytest.mark.parametrize('raw', [b'{}', b'{"KeyMetadata":null}',
                                b'{"KeyMetadata":{},"KeyMetadata":{}}', b'not-json'])
def test_ambiguous_creation_identity_rejected(tmp_path, raw):
    with opened(tmp_path) as journal:
        journal.acknowledge('bootstrap-01', 0, raw, b'')
        with pytest.raises(KeyAttemptError):
            inspect_key_attempt(journal, observations(), TAGS)


def test_foreign_execution_tags_and_ack_state_rejected(tmp_path):
    with opened(tmp_path) as journal:
        source = observations()
        source['before']['metadata']['KeyMetadata']['Enabled'] = False
        journal.acknowledge('bootstrap-01', 0, canonical(source['before']['metadata']), b'')
        with pytest.raises(KeyAttemptError):
            inspect_key_attempt(journal, observations(), {**TAGS, 'ExecutionId': 'foreign-run-123'})
        with pytest.raises(ValueError):
            inspect_key_attempt(journal, observations(), TAGS)


def test_mutable_memory_cannot_substitute_durable_ack(tmp_path):
    with opened(tmp_path) as journal:
        journal.rows.append({'kind': 'ACKNOWLEDGEMENT', 'payload': {}})
        with pytest.raises(KeyAttemptError):
            inspect_key_attempt(journal, observations(), TAGS)


def test_creation_tags_are_exactly_frozen_in_intent(tmp_path):
    with opened(tmp_path) as journal:
        assert journal.pending['request']['Tags'] == [
            {'TagKey': row['TagKey'], 'TagValue': TAGS[row['TagKey']]}
            for row in journal.package['steps'][0]['request']['Tags']]
        journal.creation_tags['Project'] = 'foreign'
        with pytest.raises(MutationJournalError):
            journal.observe('bootstrap-01', b'changed', b'')


def test_placeholder_intent_cannot_establish_creation_binding(tmp_path):
    with MutationJournal(tmp_path / 'unbound', compile_package(), TAGS['ExecutionId']) as journal:
        journal.intent('bootstrap-01')
        journal.acknowledge('bootstrap-01', 0, canonical(observations()['before']['metadata']), b'')
        with pytest.raises(KeyAttemptError):
            inspect_key_attempt(journal, observations(), TAGS)


def test_reopening_cannot_change_creation_tags(tmp_path):
    with opened(tmp_path):
        pass
    with pytest.raises(MutationJournalError):
        MutationJournal(tmp_path / 'key-attempt', compile_package(), TAGS['ExecutionId'],
                        creation_tags={**TAGS, 'ExpiresAt': '2026-10-06T00:00:00Z'})
