from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_part1_closure as builder  # noqa: E402
import build_stage5_evidence as evidence_builder  # noqa: E402
import validate_part1_closure as validator  # noqa: E402


def load(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def test_final_project_interview_deferral_is_explicit_and_non_blocking_for_part1() -> None:
    report = validator.validate_authority(validator.load_authority(ROOT), ROOT)

    assert report["result"] == "PASS"
    assert report["interview_status"] == "DEFERRED_TO_PROJECT_COMPLETION"
    assert report["requirement_count"] == 39
    assert report["capability_promotion"] == "NONE"


def test_deferred_interview_contains_no_fabricated_human_observations() -> None:
    interview = load("evidence/part1/stage5/interview-rehearsal.json")

    assert interview["result"] == "DEFERRED"
    assert interview["question_ids"] == []
    assert interview["repository_references"] == []
    assert interview["duration_minutes"] is None
    assert all(row["score"] is None for row in interview["rubric"])


def test_closure_schema_is_valid_and_governs_all_three_authorities() -> None:
    schema = load("schemas/part1-closure.schema.json")
    Draft202012Validator.check_schema(schema)
    schema_validator = Draft202012Validator(schema)

    for relative in (
        "readiness/implementation-manifest.json",
        "readiness/dependency-graph.json",
        "evidence/part1/stage5/interview-rehearsal.json",
    ):
        assert list(schema_validator.iter_errors(load(relative))) == []


def test_generated_outputs_are_byte_deterministic() -> None:
    first = builder.generated_outputs(ROOT)
    second = builder.generated_outputs(ROOT)

    assert first == second
    for relative, expected in first.items():
        assert (ROOT / relative).read_text(encoding="utf-8") == expected


def test_traceability_and_dependency_graph_are_complete() -> None:
    trace = load("evidence/part1/stage5/cross-artifact-traceability.json")
    graph = load("readiness/dependency-graph.json")
    manifest = load("readiness/implementation-manifest.json")

    assert trace["result"] == "PASS"
    assert trace["requirement_count"] == trace["complete_trace_count"] == 39
    assert {row["id"] for row in graph["nodes"]} == {row["id"] for row in manifest["slices"]}


def test_every_declared_validator_mutation_fails_with_exact_diagnostic() -> None:
    authority = validator.load_authority(ROOT)
    cases = load("tests/fixtures/part1-closure/validator-mutations.json")["cases"]

    assert len(cases) == 12
    for case in cases:
        with pytest.raises(validator.ClosureError) as exc_info:
            validator.mutation_probe(copy.deepcopy(authority), ROOT, case["mutation"])
        assert exc_info.value.code == case["expected_diagnostic"], case["id"]


def test_scope_allowlist_excludes_runtime_and_infrastructure_paths() -> None:
    changed = validator.git_paths(ROOT)

    assert not {path for path in changed if path.startswith(validator.FORBIDDEN_CHANGED_PREFIXES)}


def test_predecessor_receipts_remain_byte_identical() -> None:
    for relative, expected_digest in validator.PROTECTED_DIGESTS.items():
        assert validator.digest(ROOT / relative) == expected_digest


def test_stage5_receipt_has_complete_acceptance_criterion_partition() -> None:
    evidence = evidence_builder.criterion_evidence()
    receipt = evidence_builder.build_receipt({"result": "PASS"})

    assert set(evidence) == set(range(1, 45))
    assert receipt["criteria_total"] == 44
    assert receipt["criteria_passed"] == 40
    assert receipt["criteria_pending"] == 4
    assert [row["id"] for row in receipt["criteria"]] == [
        f"ST5-AC-{index:02d}" for index in range(1, 45)
    ]
    assert all(row["result"] == "PASS" for row in receipt["criteria"][:40])
    assert all(row["result"] == "PENDING" for row in receipt["criteria"][40:])
