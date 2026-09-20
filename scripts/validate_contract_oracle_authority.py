#!/usr/bin/env python3
"""Fail-closed validation for ChangeBridge Part 1 Stage 4 authority."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
STAGE = "ChangeBridge Part 1 Stage 4"
SCHEMA_VERSION = "1.0.0"
STAGE4_REQUIREMENTS = {"CB-ORDER-001", "CB-ORDER-003", "CB-SCHEMA-001", "CB-PUBLISH-001"}
REQUIRED_INVARIANTS = {
    "boundary",
    "continuity",
    "order",
    "idempotency",
    "conflict_detection",
    "checkpoint_coupling",
    "failure_atomicity",
    "delete_correctness",
    "schema_safety",
    "generation_isolation",
    "proof_before_publication",
    "single_publisher_cas",
    "stale_writer_rejection",
    "replay_determinism",
    "rollback_safety",
    "evidence_binding",
}
REQUIRED_CONTROLS = {
    "migration_generation",
    "frontier_checkpoint",
    "applied_transaction",
    "schema_contract",
    "reconciliation_run",
    "gate_result",
    "proof_manifest",
    "active_generation",
    "publication_event",
    "rollback_event",
    "evidence_bundle",
    "stage_receipt",
}
REQUIRED_LAYERS = {
    "unit",
    "generative_property",
    "state_machine_model",
    "contract",
    "differential",
    "integration",
    "failure",
    "infrastructure_security",
    "performance_metric",
    "evidence_integrity",
}
REQUIRED_EVIDENCE = {
    "artifact-manifest.json",
    "claim-impact-review.json",
    "contract-contradiction-register.json",
    "contract-contradiction-resolution.json",
    "contract-source-inventory.json",
    "dependency-decision.json",
    "determinism-report.json",
    "execution-envelope.json",
    "failure-lab-preservation.json",
    "file-manifest.json",
    "overlap-register.json",
    "protected-baseline.json",
    "scenario-coverage.json",
    "scenario-inventory.json",
    "scope-isolation-report.json",
    "stage-receipt.json",
    "traceability-review.json",
    "validation-report.json",
}
STAGE4_PROOF_PATHS = {
    "CB-ORDER-001": {
        "contracts/cdc-envelope-v1.schema.json",
        "tests/test_contract_oracle_authority.py",
    },
    "CB-ORDER-003": {"src/changebridge/contracts.py", "tests/test_contract_oracle_authority.py"},
    "CB-SCHEMA-001": {"contracts/catalog.json", "tests/test_contract_oracle_authority.py"},
    "CB-PUBLISH-001": {"oracles/invariants.json", "tests/test_contract_oracle_authority.py"},
}
FORBIDDEN_PROJECT_TERMS = (
    "ledger" + "guard",
    "atlas" + "retail",
    "event" + "pulse",
    "feature" + "forge",
)


class Stage4Error(Exception):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


def fail(code: str, detail: str) -> NoReturn:
    raise Stage4Error(code, detail)


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail("CB4V001_INVALID_JSON", f"{path}: {exc}")


def _schema_validate(instance: Any, schema: dict[str, Any], owner: str) -> None:
    errors = sorted(
        Draft202012Validator(schema).iter_errors(instance),
        key=lambda error: (list(error.absolute_path), error.message),
    )
    if errors:
        error = errors[0]
        location = ".".join(str(item) for item in error.absolute_path) or "$"
        fail("CB4V002_SCHEMA_REJECTED", f"{owner}:{location}:{error.validator}")


def _safe_repo_path(root: Path, value: str, owner: str) -> Path:
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "\\" in value:
        fail("CB4V030_VOLATILE_OR_UNSAFE_PATH", f"{owner}:{value}")
    resolved = (root / path).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        fail("CB4V030_VOLATILE_OR_UNSAFE_PATH", f"{owner}:{value}")
    return resolved


def load_authority(root: Path) -> dict[str, Any]:
    return {
        "catalog": load_json(root / "contracts/catalog.json"),
        "canonicalization": load_json(root / "contracts/canonicalization-v1.json"),
        "invariants": load_json(root / "oracles/invariants.json"),
        "layers": load_json(root / "testing/test-layers.json"),
        "oracle_cases": load_json(
            root / "tests/fixtures/contract-oracle-authority/oracle-cases.json"
        ),
        "adversarial": load_json(
            root / "tests/fixtures/contract-oracle-authority/adversarial-cases.json"
        ),
        "event": load_json(root / "tests/fixtures/contract-oracle-authority/valid-cdc-event.json"),
        "requirements": load_json(root / "requirements/completion-requirements.json"),
        "claims": load_json(root / "claims/claims.json"),
        "adrs": load_json(root / "architecture/adr-index.json"),
        "components": load_json(root / "architecture/components.json"),
    }


def validate_schema_documents(root: Path) -> None:
    paths = sorted((root / "contracts").glob("**/*.schema.json")) + sorted(
        (root / "schemas").glob("*.schema.json")
    )
    for path in paths:
        schema = load_json(path)
        try:
            Draft202012Validator.check_schema(schema)
        except Exception as exc:
            fail("CB4V003_INVALID_META_SCHEMA", f"{path.relative_to(root)}:{exc}")


def validate_canonicalization(document: dict[str, Any], root: Path) -> None:
    schema = load_json(root / "schemas/canonicalization-profile.schema.json")
    _schema_validate(document, schema, "canonicalization")
    if document["schema_version"] != SCHEMA_VERSION:
        fail("CB4V005_INVALID_VERSION", "canonicalization")


def validate_catalog(
    catalog: dict[str, Any],
    root: Path,
    *,
    requirements: set[str],
    adrs: set[str],
    components: set[str],
    invariants: set[str],
    claims: set[str],
    orphan_paths: set[str] | None = None,
) -> set[str]:
    schema = load_json(root / "schemas/contract-catalog.schema.json")
    _schema_validate(catalog, schema, "catalog")
    if catalog["schema_version"] != SCHEMA_VERSION:
        fail("CB4V005_INVALID_VERSION", "catalog")
    rows = catalog["contracts"]
    ids = [row["id"] for row in rows]
    if set(ids) != set(catalog["required_logical_records"]) or len(ids) != len(set(ids)):
        fail("CB4V009_REQUIRED_CONTRACT_SET", repr(ids))
    if len(set(row["schema_uri"] for row in rows)) != len(rows):
        fail("CB4V008_DUPLICATE_SCHEMA_URI", "catalog")
    catalog_paths = {row["authority_path"] for row in rows}
    schema_paths = {
        path.relative_to(root).as_posix() for path in (root / "contracts").glob("**/*.schema.json")
    }
    if orphan_paths:
        schema_paths |= orphan_paths
    if schema_paths - catalog_paths:
        fail("CB4V010_ORPHAN_SCHEMA", repr(sorted(schema_paths - catalog_paths)))
    for row in rows:
        path = _safe_repo_path(root, row["authority_path"], row["id"])
        if not path.is_file():
            fail("CB4V006_MISSING_AUTHORITY", row["authority_path"])
        contract_schema = load_json(path)
        pointer = row["schema_pointer"]
        if pointer == "#":
            if contract_schema.get("$id") != row["schema_uri"]:
                fail("CB4V007_SCHEMA_URI_MISMATCH", row["id"])
        else:
            name = pointer.removeprefix("#/$defs/")
            if name not in contract_schema.get("$defs", {}):
                fail("CB4V006_MISSING_AUTHORITY", f"{row['id']}:{pointer}")
        references = {
            "requirement": set(row["requirement_ids"]) - requirements,
            "adr": set(row["adr_ids"]) - adrs,
            "component": set(row["component_ids"]) - components,
            "invariant": set(row["invariant_ids"]) - invariants,
            "claim": set(row["claim_ids"]) - claims,
        }
        unknown = {kind: sorted(values) for kind, values in references.items() if values}
        if unknown:
            fail("CB4V011_UNKNOWN_REFERENCE", f"{row['id']}:{unknown}")
        if row["authority_path"].startswith("/tmp/"):
            fail("CB4V030_VOLATILE_OR_UNSAFE_PATH", f"{row['id']}:{row['authority_path']}")
    control = load_json(root / "contracts/control/control-records-v1.schema.json")
    controls = set(control["$defs"]) & REQUIRED_CONTROLS
    if controls != REQUIRED_CONTROLS:
        fail("CB4V012_CONTROL_RECORD_SET", repr(sorted(controls)))
    return set(ids)


def validate_invariants(
    document: dict[str, Any],
    root: Path,
    *,
    requirements: set[str],
    adrs: set[str],
    components: set[str],
    contracts: set[str],
    claims: set[str],
) -> None:
    _schema_validate(
        document, load_json(root / "schemas/invariant-oracle.schema.json"), "invariants"
    )
    ids = [row["id"] for row in document["invariants"]]
    if set(ids) != REQUIRED_INVARIANTS or len(ids) != len(set(ids)):
        fail("CB4V020_INVARIANT_SET", repr(ids))
    from changebridge.oracles import ORACLES

    if set(ORACLES) != REQUIRED_INVARIANTS:
        fail("CB4V021_ORACLE_IMPLEMENTATION_SET", repr(sorted(ORACLES)))
    for row in document["invariants"]:
        references = (
            set(row["requirement_ids"]) - requirements,
            set(row["adr_ids"]) - adrs,
            set(row["component_ids"]) - components,
            set(row["contract_ids"]) - contracts,
            set(row["claim_ids"]) - claims,
        )
        if any(references):
            fail("CB4V011_UNKNOWN_REFERENCE", row["id"])
        if row["local_oracle"] != f"changebridge.oracles:{row['id']}":
            fail("CB4V022_ORACLE_BINDING", row["id"])
        if row["evidence_label"] not in {"DESIGN_ONLY", "LOCAL_VERIFIED"}:
            fail("CB4V028_CLAIM_BOUNDARY", row["id"])


def validate_scenarios(
    document: dict[str, Any], adversarial: dict[str, Any], contracts: set[str]
) -> None:
    if set(document) != {"schema_version", "seed", "cases"} or document["seed"] != 4401:
        fail("CB4V024_SCENARIO_CORPUS", "oracle cases identity")
    from changebridge.oracles import evaluate

    coverage: dict[str, set[bool]] = {item: set() for item in REQUIRED_INVARIANTS}
    scenario_ids: set[str] = set()
    for row in document["cases"]:
        if row["scenario_id"] in scenario_ids or row["invariant_id"] not in REQUIRED_INVARIANTS:
            fail("CB4V024_SCENARIO_CORPUS", str(row.get("scenario_id")))
        scenario_ids.add(row["scenario_id"])
        actual = evaluate(row["invariant_id"], row["case"])
        if actual is not row["expected"]:
            fail("CB4V023_ORACLE_VERDICT_MISMATCH", row["scenario_id"])
        coverage[row["invariant_id"]].add(actual)
    if any(values != {False, True} for values in coverage.values()):
        fail("CB4V025_ORACLE_COVERAGE", repr(coverage))
    if set(adversarial) != {"schema_version", "seed", "cases"} or adversarial["seed"] != 4402:
        fail("CB4V024_SCENARIO_CORPUS", "adversarial identity")
    required_fields = {
        "id",
        "mutation",
        "expected_verdict",
        "expected_diagnostic",
        "contract_ids",
        "requirement_ids",
        "invariant_ids",
    }
    ids: set[str] = set()
    for row in adversarial["cases"]:
        if set(row) != required_fields or row["id"] in ids:
            fail("CB4V024_SCENARIO_CORPUS", str(row.get("id")))
        ids.add(row["id"])
        if row["expected_verdict"] != "REJECT" or set(row["contract_ids"]) - contracts:
            fail("CB4V024_SCENARIO_CORPUS", row["id"])
        if set(row["invariant_ids"]) - REQUIRED_INVARIANTS:
            fail("CB4V024_SCENARIO_CORPUS", row["id"])


def validate_layers(document: dict[str, Any], root: Path) -> None:
    _schema_validate(document, load_json(root / "schemas/test-layer.schema.json"), "test-layers")
    ids = [row["id"] for row in document["layers"]]
    if set(ids) != REQUIRED_LAYERS or len(ids) != len(set(ids)):
        fail("CB4V027_TEST_LAYER_SET", repr(ids))


def validate_requirements(document: dict[str, Any]) -> None:
    rows = {row["id"]: row for row in document["requirements"]}
    for requirement_id, proof_paths in STAGE4_PROOF_PATHS.items():
        row = rows[requirement_id]
        if row["owner_stage"] != "part1-stage4" or row["current_status"] != "PARTIAL":
            fail("CB4V029_REQUIREMENT_PROMOTION", requirement_id)
        all_paths = set(row["implementation_paths"] + row["proof_paths"])
        if not proof_paths <= all_paths or any(path.startswith("future:") for path in all_paths):
            fail("CB4V029_REQUIREMENT_PROMOTION", requirement_id)


def validate_claims(document: dict[str, Any]) -> None:
    for claim in document["claims"]:
        if claim["label"] in {"AWS_VERIFIED", "MEASURED", "EXTRAPOLATED"}:
            fail("CB4V028_CLAIM_BOUNDARY", claim["id"])
        wording = (claim["approved_wording"] + " " + claim["limitations"]).lower()
        if any(term in wording for term in FORBIDDEN_PROJECT_TERMS):
            fail("CB4V032_FOREIGN_PROJECT", claim["id"])


def validate_event(event: dict[str, Any], root: Path) -> None:
    from changebridge.contracts import schema_digest, validate_cdc_event

    cdc_schema = load_json(root / "contracts/cdc-envelope-v1.schema.json")
    validate_cdc_event(event, cdc_schema)
    orders = load_json(root / "contracts/orders-v1.json")
    expected = schema_digest(orders)
    if event["source_contract_digest"] != expected:
        fail("CB4V016_SCHEMA_DIGEST_MISMATCH", event["source_contract_digest"])


def validate_failure_lab(root: Path, observed: dict[str, Any] | None = None) -> str:
    from changebridge.simulator import run_failure_lab

    committed = load_json(root / "evidence/local-simulation.json")
    actual = run_failure_lab() if observed is None else observed
    if canonical_json(actual) != canonical_json(committed) or actual.get("metrics") != {
        "checks_passed": 13,
        "checks_total": 13,
    }:
        fail("CB4V026_FAILURE_LAB_DRIFT", "simulator differs from committed evidence")
    names = [row["check"] for row in actual["checks"]]
    if len(names) != 13 or len(names) != len(set(names)):
        fail("CB4V026_FAILURE_LAB_DRIFT", repr(names))
    return hashlib.sha256(canonical_json(actual).encode()).hexdigest()


def validate_evidence(root: Path) -> None:
    stage_root = root / "evidence/part1/stage4"
    present = {path.name for path in stage_root.glob("*.json")}
    missing = REQUIRED_EVIDENCE - present
    if missing:
        fail("CB4V033_MISSING_STAGE_EVIDENCE", repr(sorted(missing)))
    from changebridge.contracts import verify_artifact_manifest

    manifest = load_json(stage_root / "artifact-manifest.json")
    verify_artifact_manifest(root, manifest)
    receipt = load_json(stage_root / "stage-receipt.json")
    if receipt["criteria_total"] != 40 or receipt["criteria_passed"] != 37:
        fail("CB4V034_INVALID_CANDIDATE_RECEIPT", "expected 37 local passes")
    if receipt["criteria_pending"] != 3 or receipt["result"] != "PENDING":
        fail("CB4V034_INVALID_CANDIDATE_RECEIPT", "external closure must remain pending")


def validate_no_contamination(root: Path) -> None:
    paths = [
        root / "contracts/catalog.json",
        root / "oracles/invariants.json",
        root / "testing/test-layers.json",
        root / "evidence/part1/stage4",
    ]
    for path in paths:
        files = sorted(path.glob("*.json")) if path.is_dir() else [path]
        for file in files:
            content = file.read_text(encoding="utf-8").lower()
            if any(term in content for term in FORBIDDEN_PROJECT_TERMS):
                fail("CB4V032_FOREIGN_PROJECT", str(file.relative_to(root)))
            if "/tmp/" in content or "file:///" in content:
                fail("CB4V030_VOLATILE_OR_UNSAFE_PATH", str(file.relative_to(root)))


def validate_authority(
    authority: dict[str, Any], root: Path, *, check_files: bool = True, check_evidence: bool = True
) -> dict[str, Any]:
    requirement_ids = {row["id"] for row in authority["requirements"]["requirements"]}
    claim_ids = {row["id"] for row in authority["claims"]["claims"]}
    adr_ids = {row["id"] for row in authority["adrs"]["decisions"]}
    component_ids = {row["id"] for row in authority["components"]["components"]}
    invariant_ids = {row["id"] for row in authority["invariants"]["invariants"]}
    if check_files:
        validate_schema_documents(root)
    validate_canonicalization(authority["canonicalization"], root)
    contract_ids = validate_catalog(
        authority["catalog"],
        root,
        requirements=requirement_ids,
        adrs=adr_ids,
        components=component_ids,
        invariants=invariant_ids,
        claims=claim_ids,
    )
    validate_invariants(
        authority["invariants"],
        root,
        requirements=requirement_ids,
        adrs=adr_ids,
        components=component_ids,
        contracts=contract_ids,
        claims=claim_ids,
    )
    validate_scenarios(authority["oracle_cases"], authority["adversarial"], contract_ids)
    validate_layers(authority["layers"], root)
    validate_requirements(authority["requirements"])
    validate_claims(authority["claims"])
    validate_event(authority["event"], root)
    simulator_digest = validate_failure_lab(root)
    if check_files:
        validate_no_contamination(root)
    if check_evidence:
        validate_evidence(root)
    report = {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "result": "PASS",
        "evidence_label": "LOCAL_VERIFIED",
        "contract_count": len(contract_ids),
        "control_record_count": len(REQUIRED_CONTROLS),
        "invariant_count": len(REQUIRED_INVARIANTS),
        "oracle_case_count": len(authority["oracle_cases"]["cases"]),
        "adversarial_case_count": len(authority["adversarial"]["cases"]),
        "test_layer_count": len(authority["layers"]["layers"]),
        "historical_failure_check_count": 13,
        "historical_failure_lab_sha256": simulator_digest,
        "stage4_requirement_count": len(STAGE4_REQUIREMENTS),
        "capability_promotion": "NONE",
        "limitations": [
            "Local schemas and reference oracles do not prove runtime adapter conformance.",
            "No AWS, performance, availability, exactly-once, or zero-downtime claim is created.",
        ],
    }
    report["canonical_sha256"] = hashlib.sha256(canonical_json(report).encode()).hexdigest()
    return report


def mutation_probe(authority: dict[str, Any], root: Path, mutation: str) -> None:
    """Apply one minimal in-memory mutation for exact-diagnostic tests."""

    mutated = copy.deepcopy(authority)
    if mutation == "delete_contract":
        mutated["catalog"]["contracts"][-1] = copy.deepcopy(mutated["catalog"]["contracts"][0])
        validate_catalog(
            mutated["catalog"],
            root,
            requirements={row["id"] for row in mutated["requirements"]["requirements"]},
            adrs={row["id"] for row in mutated["adrs"]["decisions"]},
            components={row["id"] for row in mutated["components"]["components"]},
            invariants=REQUIRED_INVARIANTS,
            claims={row["id"] for row in mutated["claims"]["claims"]},
        )
    elif mutation == "duplicate_invariant":
        mutated["invariants"]["invariants"][-1] = copy.deepcopy(
            mutated["invariants"]["invariants"][0]
        )
        validate_invariants(
            mutated["invariants"],
            root,
            requirements={row["id"] for row in mutated["requirements"]["requirements"]},
            adrs={row["id"] for row in mutated["adrs"]["decisions"]},
            components={row["id"] for row in mutated["components"]["components"]},
            contracts={row["id"] for row in mutated["catalog"]["contracts"]},
            claims={row["id"] for row in mutated["claims"]["claims"]},
        )
    elif mutation == "broken_cross_reference":
        mutated["catalog"]["contracts"][0]["requirement_ids"] = ["CB-UNKNOWN-999"]
        validate_authority(mutated, root, check_files=False, check_evidence=False)
    elif mutation == "wrong_source_contract_digest":
        mutated["event"]["source_contract_digest"] = "0" * 64
        validate_event(mutated["event"], root)
    elif mutation == "invalid_extra_field":
        mutated["canonicalization"]["unexpected"] = True
        validate_canonicalization(mutated["canonicalization"], root)
    elif mutation == "version_downgrade":
        mutated["canonicalization"]["schema_version"] = "0.9.0"
        try:
            validate_canonicalization(mutated["canonicalization"], root)
        except Stage4Error:
            fail("CB4V005_INVALID_VERSION", "canonicalization")
    elif mutation == "altered_historical_scenario":
        observed = load_json(root / "evidence/local-simulation.json")
        observed["checks"][0]["passed"] = False
        validate_failure_lab(root, observed)
    elif mutation == "missing_seed":
        mutated["oracle_cases"].pop("seed")
        validate_scenarios(
            mutated["oracle_cases"],
            mutated["adversarial"],
            {row["id"] for row in mutated["catalog"]["contracts"]},
        )
    elif mutation == "volatile_path":
        _safe_repo_path(root, "/tmp/contract.json", "cdc_envelope")
    elif mutation == "tampered_claim_label":
        mutated["claims"]["claims"][0]["label"] = "AWS_VERIFIED"
        validate_claims(mutated["claims"])
    elif mutation == "orphan_schema":
        validate_catalog(
            mutated["catalog"],
            root,
            requirements={row["id"] for row in mutated["requirements"]["requirements"]},
            adrs={row["id"] for row in mutated["adrs"]["decisions"]},
            components={row["id"] for row in mutated["components"]["components"]},
            invariants=REQUIRED_INVARIANTS,
            claims={row["id"] for row in mutated["claims"]["claims"]},
            orphan_paths={"contracts/orphan.schema.json"},
        )
    else:
        fail("CB4V099_UNKNOWN_MUTATION", mutation)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--skip-evidence", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        report = validate_authority(
            load_authority(root), root, check_files=True, check_evidence=not args.skip_evidence
        )
    except (Stage4Error, Exception) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    rendered = canonical_json(report)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
