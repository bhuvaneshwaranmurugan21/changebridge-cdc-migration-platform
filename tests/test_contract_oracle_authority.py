from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from itertools import product
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from jsonschema import Draft202012Validator

from changebridge.contracts import (
    REQUIRED_PROOF_GATES,
    ContractError,
    canonical_bytes,
    classify_replay,
    compare_source_positions,
    event_order_key,
    publication_verdict,
    semantic_digest,
    source_position_key,
    validate_cdc_event,
    validate_control_record,
    validate_proof_manifest,
    verify_artifact_manifest,
)
from changebridge.oracles import ORACLES, evaluate

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/contract-oracle-authority"
DIGEST = "a" * 64

_SPEC = importlib.util.spec_from_file_location(
    "changebridge_stage4_validator", ROOT / "scripts/validate_contract_oracle_authority.py"
)
assert _SPEC is not None and _SPEC.loader is not None
VALIDATOR = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(VALIDATOR)
REQUIRED_INVARIANTS = VALIDATOR.REQUIRED_INVARIANTS
Stage4Error = VALIDATOR.Stage4Error
load_authority = VALIDATOR.load_authority
mutation_probe = VALIDATOR.mutation_probe
validate_authority = VALIDATOR.validate_authority

_BUILD_SPEC = importlib.util.spec_from_file_location(
    "changebridge_stage4_builder", ROOT / "scripts/build_contract_oracle_authority.py"
)
assert _BUILD_SPEC is not None and _BUILD_SPEC.loader is not None
BUILDER = importlib.util.module_from_spec(_BUILD_SPEC)
_BUILD_SPEC.loader.exec_module(BUILDER)


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def proof_gates(*, stale: str | None = None, failed: str | None = None) -> list[dict[str, Any]]:
    rows = []
    for gate_id in REQUIRED_PROOF_GATES:
        rows.append(
            {
                "record_type": "gate_result",
                "contract_version": "1.0.0",
                "record_id": f"gate-{gate_id}",
                "revision": 4,
                "evidence_refs": [f"evidence/{gate_id}.json"],
                "generation_id": "gen-1",
                "gate_id": gate_id,
                "frontier": {"kind": "integer", "value": "110"},
                "schema_set_digest": DIGEST,
                "input_revision": 3 if gate_id == stale else 4,
                "input_digests": [DIGEST],
                "producer": "local-oracle",
                "verdict": "FAIL" if gate_id == failed else "PASS",
                "gate_digest": DIGEST,
            }
        )
    return rows


def proof_manifest() -> dict[str, Any]:
    return {
        "record_type": "proof_manifest",
        "contract_version": "1.0.0",
        "record_id": "proof-1",
        "revision": 4,
        "evidence_refs": ["evidence/proof.json"],
        "generation_id": "gen-1",
        "frontier": {"kind": "integer", "value": "110"},
        "schema_set_digest": DIGEST,
        "input_revision": 4,
        "state": "SEALED",
        "gates": proof_gates(),
        "proof_manifest_digest": DIGEST,
    }


def control_records() -> list[dict[str, Any]]:
    base = {"contract_version": "1.0.0", "revision": 1, "evidence_refs": ["evidence/x.json"]}
    generation = {**base, "generation_id": "gen-1"}
    return [
        {
            **generation,
            "record_type": "migration_generation",
            "record_id": "gen-1",
            "snapshot_frontier": {"kind": "integer", "value": "100"},
            "schema_set_digest": DIGEST,
            "state": "CDC_APPLYING",
            "retention_state": "RETAINED",
        },
        {
            **generation,
            "record_type": "frontier_checkpoint",
            "record_id": "checkpoint-1",
            "previous_frontier": {"kind": "integer", "value": "100"},
            "current_frontier": {"kind": "integer", "value": "110"},
            "target_commit_id": "target-1",
            "target_commit_digest": DIGEST,
            "expected_revision": 0,
        },
        {
            **generation,
            "record_type": "applied_transaction",
            "record_id": "applied-1",
            "transaction_id": "tx-1",
            "transaction_digest": DIGEST,
            "source_frontier": {"kind": "integer", "value": "110"},
            "target_commit_id": "target-1",
        },
        {
            **generation,
            "record_type": "schema_contract",
            "record_id": "schema-1",
            "source_contract_id": "orders_source_contract",
            "source_contract_version": "1.0.0",
            "source_contract_digest": DIGEST,
            "compatibility_verdict": "COMPATIBLE",
            "quarantine_required": False,
        },
        {
            **generation,
            "record_type": "reconciliation_run",
            "record_id": "recon-1",
            "frontier": {"kind": "integer", "value": "110"},
            "canonicalization_version": "changebridge-canonical-json/1.0.0",
            "source_digest": DIGEST,
            "candidate_digest": DIGEST,
            "mismatch_count": 0,
            "verdict": "PASS",
        },
        proof_gates()[0],
        proof_manifest(),
        {
            **base,
            "record_type": "active_generation",
            "record_id": "active",
            "active_generation_id": "gen-1",
            "pointer_revision": 1,
            "proof_manifest_digest": DIGEST,
        },
        {
            **generation,
            "record_type": "publication_event",
            "record_id": "publication-1",
            "proof_manifest_digest": DIGEST,
            "expected_revision": 0,
            "prior_generation_id": None,
            "new_revision": 1,
            "verdict": "PUBLISHED",
            "diagnostic": "CBPUB000_ELIGIBLE",
        },
        {
            **base,
            "record_type": "rollback_event",
            "record_id": "rollback-1",
            "target_generation_id": "gen-0",
            "target_proof_manifest_digest": DIGEST,
            "target_state": "PROVEN",
            "retained": True,
            "readable": True,
            "reason": "operator-approved incident rollback",
            "authority": "incident-commander",
            "prior_revision": 1,
            "new_revision": 2,
        },
        {
            **base,
            "record_type": "evidence_bundle",
            "record_id": "evidence-1",
            "commit_sha": "a" * 40,
            "run_id": "run-1",
            "resources": ["local"],
            "artifacts": [{"path": "README.md", "sha256": DIGEST}],
            "evidence_label": "LOCAL_VERIFIED",
            "limitations": ["local only"],
            "producer_versions": {"python": "3.12"},
            "evidence_manifest_digest": DIGEST,
        },
        {
            **base,
            "record_type": "stage_receipt",
            "record_id": "stage4",
            "part": 1,
            "stage": 4,
            "base_commit": "a" * 40,
            "candidate_commit": "PENDING",
            "artifact_manifest_digest": DIGEST,
            "criteria_total": 40,
            "criteria_passed": 37,
            "criteria_pending": 3,
            "result": "PENDING",
            "limitations": ["external closure pending"],
        },
    ]


def diagnostic(call: Callable[[], Any]) -> str:
    try:
        result = call()
    except (ContractError, Stage4Error) as exc:
        return exc.code
    if result is False:
        return "CBORACLE_FALSE"
    return str(result)


def test_complete_authority_passes_without_candidate_evidence() -> None:
    report = validate_authority(load_authority(ROOT), ROOT, check_evidence=False)
    assert report["result"] == "PASS"
    assert report["contract_count"] == 16
    assert report["control_record_count"] == 12
    assert report["invariant_count"] == 16
    assert report["oracle_case_count"] == 32
    assert report["adversarial_case_count"] == 26
    assert report["test_layer_count"] == 10
    assert report["historical_failure_check_count"] == 13
    assert report["capability_promotion"] == "NONE"


def test_generated_views_are_current_and_byte_deterministic() -> None:
    first = BUILDER.generated_outputs(ROOT)
    second = BUILDER.generated_outputs(ROOT)
    assert first == second
    for relative, content in first.items():
        assert (ROOT / relative).read_text(encoding="utf-8") == content


def test_all_schema_documents_pass_draft_2020_12_meta_schema() -> None:
    paths = list((ROOT / "contracts").glob("**/*.schema.json"))
    paths += list((ROOT / "schemas").glob("*.schema.json"))
    assert paths
    for path in paths:
        Draft202012Validator.check_schema(load(path))


def test_valid_event_round_trip_and_semantic_digests() -> None:
    event = load(FIXTURES / "valid-cdc-event.json")
    schema = load(ROOT / "contracts/cdc-envelope-v1.schema.json")
    validate_cdc_event(event, schema)
    round_trip = json.loads(json.dumps(event, ensure_ascii=False, sort_keys=True))
    validate_cdc_event(round_trip, schema)
    assert canonical_bytes(event, domain="round-trip") == canonical_bytes(
        round_trip, domain="round-trip"
    )


@settings(max_examples=75, derandomize=True, database=None)
@given(st.dictionaries(st.text(min_size=1), st.integers(), max_size=12))
def test_canonicalization_is_independent_of_mapping_insertion_order(value: dict[str, int]) -> None:
    reversed_value = dict(reversed(list(value.items())))
    assert semantic_digest(value, domain="property") == semantic_digest(
        reversed_value, domain="property"
    )


def test_unicode_decimal_binary_null_and_absent_boundaries() -> None:
    composed = {"text": "é", "decimal": Decimal("1.2300"), "binary": b"\x00\xff", "null": None}
    decomposed = {
        "text": "e\u0301",
        "decimal": Decimal("1.23"),
        "binary": b"\x00\xff",
        "null": None,
    }
    assert canonical_bytes(composed, domain="boundaries") == canonical_bytes(
        decomposed, domain="boundaries"
    )
    assert semantic_digest({"x": None}, domain="null") != semantic_digest({}, domain="null")


@settings(max_examples=75, derandomize=True, database=None)
@given(st.lists(st.integers(min_value=0, max_value=10_000), min_size=1, max_size=20, unique=True))
def test_total_order_is_permutation_independent(sequences: list[int]) -> None:
    base = load(FIXTURES / "valid-cdc-event.json")
    events = []
    for sequence in sequences:
        event = copy.deepcopy(base)
        event["event_sequence"] = sequence
        event["event_id"] = f"{sequence:064x}"
        events.append(event)
    reversed_events = list(reversed(events))
    assert [event_order_key(item) for item in sorted(events, key=event_order_key)] == [
        event_order_key(item) for item in sorted(reversed_events, key=event_order_key)
    ]


@pytest.mark.parametrize("record", control_records(), ids=lambda row: row["record_type"])
def test_all_twelve_control_records_have_structural_and_semantic_validation(
    record: dict[str, Any],
) -> None:
    schema = load(ROOT / "contracts/control/control-records-v1.schema.json")
    validate_control_record(record, schema)


def test_all_sixteen_oracles_have_positive_and_minimal_negative_cases() -> None:
    document = load(FIXTURES / "oracle-cases.json")
    coverage: dict[str, set[bool]] = {item: set() for item in REQUIRED_INVARIANTS}
    for row in document["cases"]:
        actual = evaluate(row["invariant_id"], row["case"])
        assert actual is row["expected"], row["scenario_id"]
        coverage[row["invariant_id"]].add(actual)
    assert set(ORACLES) == REQUIRED_INVARIANTS
    assert all(values == {False, True} for values in coverage.values())


def test_complete_publication_truth_table_has_one_eligible_combination() -> None:
    keys = (
        "generation_proven",
        "proof_sealed",
        "proof_valid",
        "table_map_complete",
        "revision_current",
        "generation_matches",
    )
    eligible = []
    for values in product((False, True), repeat=len(keys)):
        row = dict(zip(keys, values, strict=True))
        candidate = {
            "generation_state": "PROVEN" if row["generation_proven"] else "PROVING",
            "proof_state": "SEALED" if row["proof_sealed"] else "OPEN",
            "proof_valid": row["proof_valid"],
            "table_map_complete": row["table_map_complete"],
            "expected_revision": 4,
            "current_revision": 4 if row["revision_current"] else 5,
            "generation_id": "gen-1",
            "proof_generation_id": "gen-1" if row["generation_matches"] else "gen-2",
        }
        verdict, code = publication_verdict(candidate)
        if verdict:
            eligible.append(values)
            assert code == "CBPUB000_ELIGIBLE"
    assert eligible == [(True, True, True, True, True, True)]


def test_proof_manifest_rejects_each_unsafe_gate_class_exactly() -> None:
    validate_proof_manifest(proof_manifest())
    cases: list[tuple[dict[str, Any], str]] = []
    missing = proof_manifest()
    missing["gates"].pop()
    cases.append((missing, "CBPRF001_GATE_SET_INVALID"))
    duplicate = proof_manifest()
    duplicate["gates"][-1] = copy.deepcopy(duplicate["gates"][0])
    cases.append((duplicate, "CBPRF002_DUPLICATE_GATE"))
    failed = proof_manifest()
    failed["gates"] = proof_gates(failed="schema")
    cases.append((failed, "CBPRF003_GATE_NOT_PASSING"))
    cross = proof_manifest()
    cross["gates"][0]["generation_id"] = "gen-2"
    cases.append((cross, "CBPRF004_CROSS_BOUNDARY_GATE"))
    stale = proof_manifest()
    stale["gates"] = proof_gates(stale="lag")
    cases.append((stale, "CBPRF005_STALE_GATE"))
    for manifest, expected in cases:
        with pytest.raises(ContractError) as raised:
            validate_proof_manifest(manifest)
        assert raised.value.code == expected


def test_adversarial_corpus_executes_with_exact_diagnostics(tmp_path: Path) -> None:
    rows = load(FIXTURES / "adversarial-cases.json")["cases"]
    event = load(FIXTURES / "valid-cdc-event.json")
    event_schema = load(ROOT / "contracts/cdc-envelope-v1.schema.json")
    control_schema = load(ROOT / "contracts/control/control-records-v1.schema.json")

    def run(name: str) -> str:
        mutated = copy.deepcopy(event)
        if name == "missing_contract_version":
            mutated.pop("contract_version")
            return diagnostic(lambda: validate_cdc_event(mutated, event_schema))
        if name == "unknown_contract_version":
            mutated["contract_version"] = "2.0.0"
            return diagnostic(lambda: validate_cdc_event(mutated, event_schema))
        if name == "prohibited_extra_field":
            mutated["unexpected"] = True
            return diagnostic(lambda: validate_cdc_event(mutated, event_schema))
        if name == "malformed_source_position":
            return diagnostic(lambda: source_position_key({"kind": "postgres_lsn", "value": "bad"}))
        if name == "incomparable_source_position":
            return diagnostic(
                lambda: compare_source_positions(
                    {"kind": "integer", "value": "1"}, {"kind": "oracle_scn", "value": "1"}
                )
            )
        if name == "equal_position_duplicate_sequence":
            return diagnostic(lambda: evaluate("order", {"order_keys": [[1, 0], [1, 0]]}))
        if name == "missing_primary_key":
            mutated["primary_key"] = []
            return diagnostic(lambda: validate_cdc_event(mutated, event_schema))
        if name == "invalid_operation_image":
            mutated["operation"] = "delete"
            return diagnostic(lambda: validate_cdc_event(mutated, event_schema))
        if name == "schema_identity_digest_mismatch":
            mutated["source_contract_digest"] = "0" * 64
            return diagnostic(lambda: validate_cdc_event(mutated, event_schema))
        if name == "same_event_changed_payload":
            second = copy.deepcopy(event)
            second["payload_digest"] = "f" * 64
            return "CBREPLAY_CONFLICT" if classify_replay(event, second) == "conflict" else "wrong"
        if name == "snapshot_cdc_gap":
            case = {
                "snapshot_frontier": {"kind": "integer", "value": "100"},
                "terminal_frontier": {"kind": "integer", "value": "110"},
                "cdc_positions": [{"kind": "integer", "value": "112"}],
            }
            return diagnostic(lambda: evaluate("boundary", case))
        if name == "batch_overlap":
            return diagnostic(
                lambda: evaluate("continuity", {"intervals": [[100, 110], [109, 120]]})
            )
        if name == "checkpoint_regression":
            record = copy.deepcopy(control_records()[1])
            record["current_frontier"] = {"kind": "integer", "value": "99"}
            return diagnostic(lambda: validate_control_record(record, control_schema))
        if name == "checkpoint_commit_mismatch":
            case = {
                "checkpoint_frontier": 110,
                "durable_target_frontier": 110,
                "target_commit_receipt_matches": False,
            }
            return diagnostic(lambda: evaluate("checkpoint_coupling", case))
        if name == "ambiguous_commit_acknowledgement":
            case = {
                "visible_before": "a",
                "visible_after_failure": "partial",
                "recovered": False,
                "double_applied": False,
            }
            return diagnostic(lambda: evaluate("failure_atomicity", case))
        if name in {
            "missing_proof_gate",
            "duplicate_proof_gate",
            "failed_proof_gate",
            "stale_proof_gate",
            "cross_generation_proof_gate",
        }:
            manifest = proof_manifest()
            if name == "missing_proof_gate":
                manifest["gates"].pop()
            if name == "duplicate_proof_gate":
                manifest["gates"][-1] = copy.deepcopy(manifest["gates"][0])
            if name == "failed_proof_gate":
                manifest["gates"] = proof_gates(failed="schema")
            if name == "stale_proof_gate":
                manifest["gates"] = proof_gates(stale="lag")
            if name == "cross_generation_proof_gate":
                manifest["gates"][0]["generation_id"] = "gen-2"
            return diagnostic(lambda: validate_proof_manifest(manifest))
        if name == "cross_generation_write":
            case = {
                "attempted_generation": "gen-1",
                "active_generation": "gen-1",
                "write_rejected": False,
            }
            return diagnostic(lambda: evaluate("generation_isolation", case))
        if name == "stale_publication_attempt":
            candidate = {
                "generation_state": "PROVEN",
                "proof_state": "SEALED",
                "proof_valid": True,
                "table_map_complete": True,
                "expected_revision": 1,
                "current_revision": 2,
                "generation_id": "gen-1",
                "proof_generation_id": "gen-1",
            }
            return publication_verdict(candidate)[1]
        if name == "rollback_unproven_target":
            record = copy.deepcopy(control_records()[9])
            record["target_state"] = "REJECTED"
            return diagnostic(lambda: validate_control_record(record, control_schema))
        if name == "tampered_artifact":
            target = tmp_path / "artifact.txt"
            target.write_text("actual", encoding="utf-8")
            manifest = {
                "artifacts": [
                    {"path": "artifact.txt", "sha256": hashlib.sha256(b"expected").hexdigest()}
                ]
            }
            return diagnostic(lambda: verify_artifact_manifest(tmp_path, manifest))
        if name == "floating_identity_material":
            return diagnostic(lambda: canonical_bytes({"amount": 1.2}, domain="event"))
        if name == "naive_timestamp":
            return diagnostic(
                lambda: canonical_bytes({"time": datetime(2026, 1, 1)}, domain="event")
            )
        raise AssertionError(name)

    for row in rows:
        assert run(row["mutation"]) == row["expected_diagnostic"], row["id"]


def test_validator_mutation_corpus_has_exact_non_interchangeable_diagnostics() -> None:
    authority = load_authority(ROOT)
    rows = load(FIXTURES / "validator-mutations.json")["cases"]
    for row in rows:
        if row["mutation"] == "stale_gate":
            manifest = proof_manifest()
            manifest["gates"] = proof_gates(stale="lag")
            actual = diagnostic(lambda manifest=manifest: validate_proof_manifest(manifest))
        else:
            actual = diagnostic(
                lambda mutation=row["mutation"]: mutation_probe(authority, ROOT, mutation)
            )
        assert actual == row["expected_diagnostic"], row["id"]
