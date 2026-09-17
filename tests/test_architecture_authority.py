from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VALIDATOR = load_module(
    ROOT / "scripts/validate_architecture_authority.py",
    "changebridge_architecture_validator",
)
BUILDER = load_module(
    ROOT / "scripts/build_architecture_authority.py",
    "changebridge_architecture_builder",
)


def load_json(path: str) -> Any:
    return json.loads((ROOT / path).read_text())


def baseline() -> dict[str, Any]:
    return cast(dict[str, Any], VALIDATOR.load_authority(ROOT))


def copied_transition(authority: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(authority["generation"]["transitions"][0])


def apply_mutation(name: str, authority: dict[str, Any]) -> None:
    components = authority["components"]["components"]
    decisions = authority["adrs"]["decisions"]
    generation = authority["generation"]
    checkpoint = authority["checkpoint"]
    proof = authority["proof"]
    publication = authority["publication"]
    mappings = authority["requirement_map"]
    claims = authority["claims"]["claims"]
    if name == "unknown_authority_section":
        authority["trust_me"] = True
    elif name == "cross_project_reference":
        components[0]["responsibility"] += " " + VALIDATOR.FORBIDDEN_PROJECT_TERMS[0]
    elif name == "invalid_component_fields":
        components[0]["trust_me"] = True
    elif name == "duplicate_component":
        components.append(copy.deepcopy(components[0]))
    elif name == "invalid_plane":
        components[0]["plane"] = "transport"
    elif name == "missing_component_owner":
        components[0]["responsibility"] = ""
    elif name == "incomplete_component_boundary":
        components[0]["non_responsibilities"] = []
    elif name == "unknown_component_dependency":
        components[0]["dependencies"].append("missing_component")
    elif name == "missing_required_adr":
        decisions.pop()
    elif name == "duplicate_adr":
        decisions.append(copy.deepcopy(decisions[0]))
    elif name == "invalid_adr_status":
        decisions[0]["status"] = "PROPOSED"
    elif name == "unsafe_adr_path":
        decisions[0]["path"] = "../ADR.md"
    elif name == "invalid_adr_component":
        decisions[0]["components"].append("missing_component")
    elif name == "duplicate_state":
        generation["states"].append(copy.deepcopy(generation["states"][0]))
    elif name == "missing_initial_state":
        generation["initial_state"] = "UNKNOWN"
    elif name == "terminal_state_escape":
        row = copied_transition(authority)
        row.update({"id": "reopen_rejected", "source": "REJECTED", "target": "CREATED"})
        generation["transitions"].append(row)
    elif name == "unknown_transition_state":
        generation["transitions"][0]["target"] = "UNKNOWN"
    elif name == "unreachable_state":
        generation["transitions"] = [
            row for row in generation["transitions"] if row["target"] != "RETIRED"
        ]
    elif name == "incomplete_transition":
        generation["transitions"][0].pop("recovery")
    elif name == "noncanonical_generation_state":
        retired = next(row for row in generation["states"] if row["id"] == "RETIRED")
        retired["id"] = "ARCHIVED"
        generation["terminal_states"] = ["REJECTED", "ARCHIVED"]
        for row in generation["transitions"]:
            if row["target"] == "RETIRED":
                row["target"] = "ARCHIVED"
    elif name == "publication_from_unproven":
        row = copied_transition(authority)
        row.update({"id": "publish_unproven", "source": "PROVING", "target": "PUBLISHED"})
        generation["transitions"].append(row)
    elif name == "cdc_after_seal":
        row = copied_transition(authority)
        row.update({"id": "reopen_apply", "source": "SEALED", "target": "CDC_APPLYING"})
        generation["transitions"].append(row)
    elif name == "checkpoint_before_target":
        start = next(row for row in checkpoint["transitions"] if row["id"] == "start_checkpoint")
        start["source"] = "FRONTIER_PROPOSED"
        checkpoint["transitions"].append(
            {
                "id": "target_to_safe_failure",
                "source": "TARGET_COMMIT_DURABLE",
                "target": "FAILED_SAFE",
                "guard": "checkpoint protocol invalid",
                "action": "halt",
            }
        )
    elif name == "ambiguous_blind_retry":
        row = next(
            item for item in checkpoint["transitions"] if item["id"] == "begin_reconciliation"
        )
        row["action"] = "blind retry request"
    elif name == "missing_checkpoint_invariant":
        checkpoint["invariants"].pop()
    elif name == "duplicate_proof_gate":
        proof["required_gates"].append(copy.deepcopy(proof["required_gates"][0]))
    elif name == "missing_proof_gate":
        proof["required_gates"].pop()
    elif name == "unknown_proof_owner":
        proof["required_gates"][0]["owner"] = "missing_component"
    elif name == "incomplete_proof_binding":
        proof["gate_fields"].pop()
    elif name == "incomplete_proof_aggregation":
        proof["aggregation_rules"] = [
            row for row in proof["aggregation_rules"] if "immutable" not in row
        ]
    elif name == "incomplete_publication_model":
        row = next(item for item in publication["transitions"] if item["id"] == "verification_fail")
        row["id"] = "unexpected_failure"
    elif name == "publication_without_proof":
        row = next(item for item in publication["transitions"] if item["id"] == "eligible")
        row["guard"] = "generation requested"
    elif name == "unsafe_stale_writer":
        row = next(item for item in publication["transitions"] if item["id"] == "cas_conflict")
        row["action"] = "overwrite pointer"
    elif name == "post_publish_failure_hidden":
        row = next(item for item in publication["transitions"] if item["id"] == "verification_fail")
        row["target"] = "FAILED_SAFE"
        publication["transitions"].append(
            {
                "id": "incident_reachable",
                "source": "ELIGIBILITY_CHECK",
                "target": "INCIDENT",
                "guard": "synthetic reachability",
                "action": "record",
            }
        )
    elif name == "incomplete_pointer":
        publication["pointer_fields"].pop()
    elif name == "duplicate_requirement_mapping":
        mappings["entries"].append(copy.deepcopy(mappings["entries"][0]))
    elif name == "orphan_requirement":
        mappings["entries"].pop()
    elif name == "stage3_requirement_set_drift":
        mappings["stage3_owned_requirements"].pop()
    elif name == "capability_promotion":
        mappings["capability_promotion"] = "SATISFIED"
    elif name == "invalid_requirement_mapping":
        mappings["entries"][0]["trust_me"] = True
    elif name == "unknown_requirement_reference":
        mappings["entries"][0]["components"].append("missing_component")
    elif name == "unresolved_stage3_requirement":
        mappings["entries"][0]["architecture_disposition"] = "BLOCKING"
    elif name == "unknown_claim_label":
        claims[0]["label"] = "TRUSTED"
    elif name == "stale_architecture_binding":
        next(row for row in claims if row["id"] == "CB-CLAIM-002")["producing_commit"] = "0" * 40
    elif name == "incomplete_claim_review":
        authority["claim_impact"]["reviewed_claim_ids"].pop()
    elif name == "architecture_claim_promotion":
        next(row for row in claims if row["id"] == "CB-CLAIM-002")["label"] = "LOCAL_VERIFIED"
    else:
        raise AssertionError(f"unknown mutation: {name}")


def test_full_authority_corpus_passes() -> None:
    report = VALIDATOR.validate_authority(
        baseline(),
        ROOT,
        check_files=True,
        check_rendered=True,
    )
    expected = load_json("tests/fixtures/architecture-authority/valid-authority.json")
    for key, value in expected.items():
        if key.startswith("expected_"):
            assert report[key.removeprefix("expected_")] == value
    assert report["result"] == "PASS"
    assert report["capability_promotion"] == "NONE"


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        (case["mutation"], case["expected_code"])
        for case in load_json("tests/fixtures/architecture-authority/invalid-cases.json")["cases"]
    ],
)
def test_invalid_authority_fails_for_exact_reason(
    mutation: str,
    expected_code: str,
) -> None:
    authority = baseline()
    apply_mutation(mutation, authority)
    with pytest.raises(VALIDATOR.ArchitectureError) as failure:
        VALIDATOR.validate_authority(
            authority,
            ROOT,
            check_files=False,
            check_rendered=False,
        )
    assert failure.value.code == expected_code


def test_report_and_rendered_views_are_deterministic() -> None:
    first = VALIDATOR.validate_authority(
        baseline(),
        ROOT,
        check_files=True,
        check_rendered=True,
    )
    second = VALIDATOR.validate_authority(
        baseline(),
        ROOT,
        check_files=True,
        check_rendered=True,
    )
    assert VALIDATOR.canonical_json(first) == VALIDATOR.canonical_json(second)
    BUILDER.build(ROOT, check=True)
