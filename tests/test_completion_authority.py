from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_validator() -> ModuleType:
    path = ROOT / "scripts/validate_completion_authority.py"
    spec = importlib.util.spec_from_file_location("completion_authority", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VALIDATOR = load_validator()


def load_json(relative: str) -> dict[str, Any]:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def baseline() -> tuple[dict[str, Any], dict[str, Any], dict[str, str], str]:
    requirements = load_json("requirements/completion-requirements.json")
    claims = load_json("claims/claims.json")
    surfaces = {
        path: (ROOT / path).read_text(encoding="utf-8")
        for path in {surface["path"] for claim in claims["claims"] for surface in claim["public_surfaces"]}
    }
    failure_lab = (ROOT / "docs/failure-lab.md").read_text(encoding="utf-8")
    return requirements, claims, surfaces, failure_lab


def apply_mutation(
    name: str,
    requirements: dict[str, Any],
    claims: dict[str, Any],
    surfaces: dict[str, str],
    failure_lab: str,
) -> str:
    requirement_rows = requirements["requirements"]
    claim_rows = claims["claims"]
    if name == "unknown_label":
        claim_rows[0]["label"] = "PRODUCTION_READY"
    elif name == "missing_requirement_field":
        requirement_rows[0].pop("failure_condition")
    elif name == "duplicate_requirement":
        requirement_rows.append(copy.deepcopy(requirement_rows[0]))
    elif name == "duplicate_claim":
        claim_rows.append(copy.deepcopy(claim_rows[0]))
    elif name == "unknown_dependency":
        requirement_rows[0]["dependencies"] = ["CB-ORDER-999"]
    elif name == "dependency_cycle":
        requirement_rows[0]["dependencies"] = [requirement_rows[1]["id"]]
        requirement_rows[1]["dependencies"] = [requirement_rows[0]["id"]]
    elif name == "missing_failure_condition":
        requirement_rows[0]["failure_condition"] = ""
    elif name == "future_proof_for_satisfied_requirement":
        row = next(item for item in requirement_rows if item["current_status"] == "SATISFIED")
        row["proof_paths"].append("future:tests/not-current.py")
    elif name == "missing_requirement_path":
        row = next(item for item in requirement_rows if item["current_status"] == "SATISFIED")
        row["proof_paths"] = ["evidence/does-not-exist.json"]
    elif name == "unsafe_claim_path":
        claim_rows[0]["proof_refs"] = ["../outside.json"]
    elif name == "cross_project_reference":
        claim_rows[0]["limitations"] += " " + "ledger" + "guard" + " evidence"
    elif name == "malformed_commit":
        claim_rows[0]["producing_commit"] = "deadbeef"
    elif name == "unbound_numeric_claim":
        claim_rows[0]["approved_wording"] = "Observed p95 latency is 10 seconds."
    elif name == "unsupported_aws_claim":
        claim_rows[0]["label"] = "AWS_VERIFIED"
        claim_rows[0]["producing_run"] = None
    elif name == "unsupported_measured_claim":
        claim_rows[0]["label"] = "MEASURED"
    elif name == "unsupported_extrapolation":
        claim_rows[0]["label"] = "EXTRAPOLATED"
    elif name == "public_wording_drift":
        claim_rows[0]["approved_wording"] = "Stronger wording not present on the surface."
    elif name == "unregistered_public_claim":
        surfaces["README.md"] += "\n<!-- claim:CB-CLAIM-999 -->\nUnregistered.\n"
    elif name == "orphan_stage1_claim":
        claim = next(item for item in claim_rows if "PC-010" in item["source_claim_ids"])
        claim["source_claim_ids"].remove("PC-010")
    elif name == "failure_lab_mismatch":
        failure_lab = failure_lab.replace(
            "| `contiguous_batch` | Apply `(100,130]` after frontier 100 | "
            "Batch applies and frontier becomes 130 |\n",
            "",
        )
    elif name == "volatile_canonical_field":
        claim_rows[0]["generated_at"] = "2026-09-17T00:00:00Z"
    elif name == "unknown_semantic_field":
        claim_rows[0]["trust_me"] = True
    else:
        raise AssertionError(f"unknown mutation: {name}")
    return failure_lab


def test_full_authority_corpus_passes() -> None:
    requirements, claims, surfaces, failure_lab = baseline()
    report = VALIDATOR.validate_authority(
        requirements,
        claims,
        ROOT,
        surface_overrides=surfaces,
        failure_lab_override=failure_lab,
    )
    expected = load_json("tests/fixtures/completion-authority/valid-authority.json")
    assert report["result"] == "PASS"
    assert report["requirement_count"] == expected["expected_requirement_count"]
    assert report["claim_count"] == expected["expected_claim_count"]
    assert report["completion_conditions"] == expected["expected_completion_conditions"]
    assert report["invariants"] == expected["expected_invariants"]
    assert len(report["failure_lab_checks"]) == expected["expected_failure_lab_count"]


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        (case["mutation"], case["expected_code"])
        for case in load_json("tests/fixtures/completion-authority/invalid-cases.json")["cases"]
    ],
)
def test_invalid_authority_fails_for_intended_reason(mutation: str, expected_code: str) -> None:
    requirements, claims, surfaces, failure_lab = baseline()
    failure_lab = apply_mutation(mutation, requirements, claims, surfaces, failure_lab)
    with pytest.raises(VALIDATOR.AuthorityError) as failure:
        VALIDATOR.validate_authority(
            requirements,
            claims,
            ROOT,
            surface_overrides=surfaces,
            failure_lab_override=failure_lab,
        )
    assert failure.value.code == expected_code


def test_rendering_and_report_are_deterministic() -> None:
    requirements = load_json("requirements/completion-requirements.json")
    claims = load_json("claims/claims.json")
    first_outputs = VALIDATOR.generated_outputs(requirements, claims)
    second_outputs = VALIDATOR.generated_outputs(requirements, claims)
    assert first_outputs == second_outputs
    first_report = VALIDATOR.validate_authority(requirements, claims, ROOT)
    second_report = VALIDATOR.validate_authority(requirements, claims, ROOT)
    assert VALIDATOR.canonical_json(first_report) == VALIDATOR.canonical_json(second_report)
