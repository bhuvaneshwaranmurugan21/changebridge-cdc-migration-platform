#!/usr/bin/env python3
"""Fail-closed validation for ChangeBridge Part 1 Stage 5 closure authority."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import build_part1_closure as builder
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
BASE_COMMIT = "f7ada638e0404afacaac604be400c1434858002f"
BASE_TREE = "2401a4e8cdff8ae153dc4b1cebc1bc7b5cc61ac3"
EXPECTED_REQUIREMENTS = 39
EXPECTED_ADRS = 15
EXPECTED_COMPONENTS = 17
EXPECTED_CONTRACTS = 16
EXPECTED_INVARIANTS = 16
EXPECTED_CLAIMS = 10
EXPECTED_SCENARIOS = 13
EXPECTED_RISKS = 16
SOURCE_FREEZE_COMMIT = "a4ad1b73e6cd7da2ed1cea22f1f86a608d7052ee"
SOURCE_FREEZE_TREE = "8ae75b0d6e71fd12d744d6dabea454f564a815a9"
EXPECTED_CLAIM_LABELS = {
    "CB-CLAIM-001": "LOCAL_VERIFIED",
    "CB-CLAIM-002": "DESIGN_ONLY",
    "CB-CLAIM-003": "UNCLAIMED",
    "CB-CLAIM-004": "LOCAL_VERIFIED",
    "CB-CLAIM-005": "LOCAL_VERIFIED",
    "CB-CLAIM-006": "DESIGN_ONLY",
    "CB-CLAIM-007": "UNCLAIMED",
    "CB-CLAIM-008": "DESIGN_ONLY",
    "CB-CLAIM-009": "DESIGN_ONLY",
    "CB-CLAIM-010": "LOCAL_VERIFIED",
}
PROTECTED_DIGESTS = {
    "evidence/part1/stage1/artifact_manifest.json": (
        "424f63c992796f3c9a903e737af3b16a429edcdd9361b673711863d293539d47"
    ),
    "evidence/part1/stage2/artifact-manifest.json": (
        "b63acdab969a9ca972e4fa00c423ee03bcd0b4659b97577749c542b912ec460c"
    ),
    "evidence/part1/stage3/artifact-manifest.json": (
        "be248e6bf6780bbc2f22ea1e7688bbdaa658a4d7632a8d328b60f2ceb1688a39"
    ),
    "evidence/part1/stage4/artifact-manifest.json": (
        "0fc7df11542fc693b91fae2030345a5a520d6cc1d15f6f6cd8e81e440e4f2481"
    ),
    "evidence/part1/stage1/stage_receipt.json": (
        "5781abefaa399102594ad735e865f03f65cbf1aef63ea7595d7b339c7fb38551"
    ),
    "evidence/part1/stage2/stage-receipt.json": (
        "79743ebf1c9006d3939eec2afa740774e2ffb31cae8a4b865adbe050483d14d7"
    ),
    "evidence/part1/stage3/stage-receipt.json": (
        "8fde07277e7ba5935d344976f3af55989ae04acb6838c4044f58820468a12bf4"
    ),
    "evidence/part1/stage4/stage-receipt.json": (
        "c0193863c0cadfc122aff168224ed74978d967ccc3a70c66c4770eb201075809"
    ),
}
FORBIDDEN_CHANGED_PREFIXES = ("src/changebridge/", "jobs/", "infra/terraform/")
FOREIGN_PROJECT_TOKEN_DIGESTS = {
    "fa6693fea98aaee155729a8d507bd19851613641e3f8d76458521ef89f53c826",
    "b84df95f092334b6a9fd6e1d9136aa06604070312e3ebd76387f52def66c7e19",
    "4eaab07b1ac907e562c30d4d79e59eb842a0c37085340d51c841c5a4e8a14ae5",
    "7249a5fce3e754cbb4f9ca87025ec031f31f8665ad2580c200a8c8e5cdb16e51",
}


class ClosureError(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code


def fail(code: str, detail: str) -> None:
    raise ClosureError(code, detail)


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        fail("CB5V001_NOT_OBJECT", str(path.relative_to(ROOT)))
    return value


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_paths(root: Path) -> set[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{BASE_COMMIT}...HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    paths = {line for line in result.stdout.splitlines() if line}
    unstaged = subprocess.run(
        ["git", "diff", "--name-only"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    paths.update(line for line in unstaged.stdout.splitlines() if line)
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    paths.update(line for line in untracked.stdout.splitlines() if line)
    return paths


def load_authority(root: Path) -> dict[str, Any]:
    return {
        "requirements": load(root / "requirements/completion-requirements.json"),
        "proof_matrix": load(root / "requirements/requirement-proof-matrix.json"),
        "architecture_map": load(root / "architecture/requirement-architecture-map.json"),
        "adr_index": load(root / "architecture/adr-index.json"),
        "components": load(root / "architecture/components.json"),
        "contracts": load(root / "contracts/catalog.json"),
        "invariants": load(root / "oracles/invariants.json"),
        "claims": load(root / "claims/claims.json"),
        "manifest": load(root / "readiness/implementation-manifest.json"),
        "graph": load(root / "readiness/dependency-graph.json"),
        "trace": load(root / "evidence/part1/stage5/cross-artifact-traceability.json"),
        "orphan_review": load(root / "evidence/part1/stage5/orphan-reference-review.json"),
        "predecessors": load(root / "evidence/part1/stage5/protected-baseline.json"),
        "risks": load(root / "evidence/part1/stage5/risk-failure-rehearsal.json"),
        "authorization": load(root / "evidence/part1/stage5/resource-authorization-forecast.json"),
        "skeptical": load(root / "evidence/part1/stage5/skeptical-review.json"),
        "interview": load(root / "evidence/part1/stage5/interview-rehearsal.json"),
        "validation_report": load(root / "evidence/part1/stage5/validation-report.json"),
        "determinism_report": load(root / "evidence/part1/stage5/determinism-report.json"),
        "file_manifest": load(root / "evidence/part1/stage5/file-manifest.json"),
    }


def validate_schema(root: Path, authority: dict[str, Any]) -> None:
    schema = load(root / "schemas/part1-closure.schema.json")
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    for key in ("manifest", "graph", "interview"):
        errors = sorted(validator.iter_errors(authority[key]), key=lambda item: list(item.path))
        if errors:
            fail("CB5V002_SCHEMA", f"{key}: {errors[0].message}")


def validate_predecessors(root: Path, authority: dict[str, Any]) -> None:
    if authority["predecessors"].get("base_commit") != BASE_COMMIT:
        fail("CB5V003_BASE_COMMIT", str(authority["predecessors"].get("base_commit")))
    if authority["predecessors"].get("base_tree") != BASE_TREE:
        fail("CB5V004_BASE_TREE", str(authority["predecessors"].get("base_tree")))
    recorded = {
        row["path"]: row["sha256"] for row in authority["predecessors"].get("artifacts", [])
    }
    if recorded != PROTECTED_DIGESTS:
        fail("CB5V005_PREDECESSOR_SET", repr(recorded))
    for path, expected in PROTECTED_DIGESTS.items():
        if digest(root / path) != expected:
            fail("CB5V006_PREDECESSOR_DRIFT", path)


def requirement_map(authority: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = authority["requirements"].get("requirements", [])
    if len(rows) != EXPECTED_REQUIREMENTS:
        fail("CB5V007_REQUIREMENT_COUNT", str(len(rows)))
    result = {row["id"]: row for row in rows}
    if len(result) != len(rows):
        fail("CB5V008_DUPLICATE_REQUIREMENT", "requirements")
    return result


def validate_trace(authority: dict[str, Any], requirements: dict[str, dict[str, Any]]) -> None:
    trace = authority["trace"]
    rows = trace.get("rows", [])
    ids = {row["requirement_id"] for row in rows}
    if ids != set(requirements) or len(rows) != len(requirements):
        fail("CB5V010_REQUIREMENT_TRACE_SET", repr(sorted(set(requirements) - ids)))
    if trace.get("result") != "PASS" or trace.get("complete_trace_count") != len(requirements):
        fail("CB5V011_INCOMPLETE_TRACE", repr(trace.get("complete_trace_count")))
    if authority["orphan_review"].get("result") != "PASS":
        fail("CB5V012_ORPHAN_REFERENCE", repr(authority["orphan_review"].get("errors")))


def validate_interview_requirement(
    authority: dict[str, Any], requirements: dict[str, dict[str, Any]]
) -> None:
    row = requirements["CB-INTERVIEW-001"]
    matrix = {item["requirement_id"]: item for item in authority["proof_matrix"]["entries"]}[
        "CB-INTERVIEW-001"
    ]
    architecture = {
        item["requirement_id"]: item for item in authority["architecture_map"]["entries"]
    }["CB-INTERVIEW-001"]
    all_paths = row["implementation_paths"] + row["proof_paths"]
    if row["current_status"] == "SATISFIED" and any(
        path.startswith("future:") for path in all_paths
    ):
        fail("CB5V014_SATISFIED_FUTURE_PATH", repr(all_paths))
    if row["current_status"] != "DEFERRED" or row["owner_stage"] != "project-final-interview":
        fail("CB5V013_PENDING_REQUIREMENT_STATUS", repr(row))
    if row["implementation_paths"] != ["docs/INTERVIEW_WALKTHROUGH.md"] or row["proof_paths"] != [
        "future:evidence/project-completion/interview-rehearsal.json"
    ]:
        fail("CB5V015_INTERVIEW_REQUIREMENT_STATUS", repr(all_paths))
    if (
        matrix["status"] != "DEFERRED"
        or matrix["owner_stage"] != "project-final-interview"
        or matrix["implementation_paths"] != ["docs/INTERVIEW_WALKTHROUGH.md"]
        or matrix["future_proof_paths"]
        != ["future:evidence/project-completion/interview-rehearsal.json"]
    ):
        fail("CB5V016_PROOF_MATRIX_STATUS", repr(matrix))
    if (
        architecture["requirement_status"] != "DEFERRED"
        or architecture["owner_stage"] != "project-final-interview"
        or architecture["proof_owner"] != "project-final-interview"
    ):
        fail("CB5V017_ARCHITECTURE_MAP_STATUS", repr(architecture))


def validate_graph(authority: dict[str, Any]) -> None:
    slices = authority["manifest"]["slices"]
    nodes = authority["graph"]["nodes"]
    slice_ids = [row["id"] for row in slices]
    graph = {row["id"]: set(row["depends_on"]) for row in nodes}
    if set(slice_ids) != set(graph) or len(slice_ids) != len(set(slice_ids)):
        fail("CB5V018_GRAPH_SLICE_SET", repr(slice_ids))
    for node, dependencies in graph.items():
        if dependencies - set(graph):
            fail("CB5V019_UNKNOWN_DEPENDENCY", f"{node}: {sorted(dependencies - set(graph))}")
    remaining = copy.deepcopy(graph)
    while remaining:
        ready = {node for node, dependencies in remaining.items() if not dependencies}
        if not ready:
            fail("CB5V020_DEPENDENCY_CYCLE", repr(sorted(remaining)))
        remaining = {
            node: dependencies - ready
            for node, dependencies in remaining.items()
            if node not in ready
        }
    slice_lookup = {row["id"]: row for row in slices}
    for node, dependencies in graph.items():
        if set(slice_lookup[node]["prerequisites"]) != dependencies:
            fail("CB5V021_GRAPH_MANIFEST_DRIFT", node)


def validate_references(root: Path, authority: dict[str, Any]) -> None:
    requirements = {row["id"] for row in authority["requirements"]["requirements"]}
    contracts = {row["id"] for row in authority["contracts"]["contracts"]}
    invariants = {row["id"] for row in authority["invariants"]["invariants"]}
    for row in authority["manifest"]["slices"]:
        if set(row["requirement_ids"]) - requirements:
            fail("CB5V022_UNKNOWN_REQUIREMENT", row["id"])
        if set(row["contract_ids"]) - contracts or set(row["invariant_ids"]) - invariants:
            fail("CB5V024_UNKNOWN_AUTHORITY", row["id"])
        for path in row["paths"]:
            if not (root / path).exists():
                fail("CB5V026_UNGROUNDED_PATH", f"{row['id']}: {path}")


def validate_risk_and_authorization(authority: dict[str, Any]) -> None:
    cases = authority["risks"].get("cases", [])
    if len(cases) != EXPECTED_RISKS or len({row["id"] for row in cases}) != EXPECTED_RISKS:
        fail("CB5V023_RISK_COVERAGE", str(len(cases)))
    authorization = authority["authorization"]
    if any(
        authorization.get(field)
        for field in (
            "invented_account_ids",
            "invented_role_arns",
            "invented_budgets",
            "invented_resource_names",
        )
    ):
        fail("CB5V025_INVENTED_EXTERNAL_IDENTITY", "authorization forecast")


def validate_skeptical_and_interview(authority: dict[str, Any]) -> None:
    review = authority["skeptical"]
    interview = authority["interview"]
    if (
        review.get("blocking_findings")
        or review.get("deferred_findings") != ["SR-10"]
        or review.get("result") != "PASS_WITH_DEFERRED_FINAL_GATE"
    ):
        fail("CB5V027_SKEPTICAL_REVIEW", repr(review.get("blocking_findings")))
    if (
        interview.get("status") != "DEFERRED_TO_PROJECT_COMPLETION"
        or interview.get("result") != "DEFERRED"
    ):
        fail("CB5V028_INTERVIEW_EVIDENCE", interview.get("status", "missing"))
    if (
        interview.get("question_ids")
        or interview.get("repository_references")
        or interview.get("duration_minutes") is not None
        or any(rubric.get("score") is not None for rubric in interview["rubric"])
    ):
        fail("CB5V029_INTERVIEW_SCORE", "deferred evidence contains fabricated observations")


def validate_counts_and_claims(authority: dict[str, Any]) -> None:
    counts = {
        "adrs": len(authority["adr_index"]["decisions"]),
        "components": len(authority["components"]["components"]),
        "contracts": len(authority["contracts"]["contracts"]),
        "invariants": len(authority["invariants"]["invariants"]),
        "claims": len(authority["claims"]["claims"]),
    }
    expected = {
        "adrs": EXPECTED_ADRS,
        "components": EXPECTED_COMPONENTS,
        "contracts": EXPECTED_CONTRACTS,
        "invariants": EXPECTED_INVARIANTS,
        "claims": EXPECTED_CLAIMS,
    }
    if counts != expected:
        fail("CB5V030_AUTHORITY_COUNTS", repr(counts))
    labels = {row["id"]: row["label"] for row in authority["claims"]["claims"]}
    if labels != EXPECTED_CLAIM_LABELS:
        fail("CB5V031_CLAIM_PROMOTION", repr(labels))
    for claim in authority["claims"]["claims"]:
        walkthrough = [
            surface
            for surface in claim["public_surfaces"]
            if surface["path"] == "docs/INTERVIEW_WALKTHROUGH.md"
        ]
        expected_marker = claim["id"]
        if walkthrough != [
            {
                "path": "docs/INTERVIEW_WALKTHROUGH.md",
                "marker": expected_marker,
            }
        ]:
            fail("CB5V036_WALKTHROUGH_CLAIM_SURFACE", claim["id"])


def validate_stage5_reports(root: Path, authority: dict[str, Any]) -> None:
    validation = authority["validation_report"]
    if (
        validation.get("validated_commit") != SOURCE_FREEZE_COMMIT
        or validation.get("validated_tree") != SOURCE_FREEZE_TREE
        or validation.get("result") != "PASS"
        or any(gate.get("result") != "PASS" for gate in validation.get("gates", []))
    ):
        fail("CB5V037_VALIDATION_REPORT", repr(validation))
    interview = validation.get("interview_requirement", {})
    if (
        interview.get("status") != "DEFERRED"
        or interview.get("owner") != "project-final-interview"
        or interview.get("requirement_weakened") is not False
    ):
        fail("CB5V037_VALIDATION_REPORT", repr(interview))

    determinism = authority["determinism_report"]
    if (
        determinism.get("result") != "PASS"
        or determinism.get("runs") != 2
        or determinism.get("volatile_fields")
        or determinism.get("byte_differences")
    ):
        fail("CB5V038_DETERMINISM_REPORT", repr(determinism))
    for artifact in determinism.get("artifacts", []):
        path = root / artifact["path"]
        if not path.is_file() or digest(path) != artifact["sha256"]:
            fail("CB5V038_DETERMINISM_REPORT", artifact["path"])

    file_manifest = authority["file_manifest"]
    if (
        file_manifest.get("result") != "PASS"
        or file_manifest.get("runtime_paths")
        or file_manifest.get("terraform_paths")
        or file_manifest.get("dependency_declaration_paths")
        or file_manifest.get("unexplained_paths")
    ):
        fail("CB5V039_FILE_MANIFEST", repr(file_manifest))


def validate_scope_and_isolation(root: Path) -> None:
    paths = git_paths(root)
    forbidden = sorted(
        path
        for path in paths
        if any(path.startswith(prefix) for prefix in FORBIDDEN_CHANGED_PREFIXES)
    )
    if forbidden:
        fail("CB5V033_RUNTIME_SCOPE", repr(forbidden))
    for path in sorted(paths):
        candidate = root / path
        if not candidate.is_file() or candidate.is_symlink():
            continue
        try:
            text = candidate.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        collapsed = text.replace("-", "").replace("_", "")
        tokens = "".join(character if character.isalnum() else " " for character in collapsed)
        token_digests = {
            hashlib.sha256(token.lower().encode("utf-8")).hexdigest() for token in tokens.split()
        }
        if token_digests & FOREIGN_PROJECT_TOKEN_DIGESTS:
            fail("CB5V032_PROJECT_ISOLATION", path)
    status = (root / "PROJECT_STATUS.md").read_text(encoding="utf-8")
    if "PROJECT_COMPLETION_VERIFIED" in status or "PART1_COMPLETION_VERIFIED" in status:
        fail("CB5V034_COMPLETION_STATUS", "pre-merge status is too strong")


def validate_generated(root: Path) -> None:
    expected = builder.generated_outputs(root)
    for relative, content in expected.items():
        path = root / relative
        if not path.is_file() or path.read_text(encoding="utf-8") != content:
            fail("CB5V035_GENERATED_DRIFT", str(relative))


def validate_authority(authority: dict[str, Any], root: Path) -> dict[str, Any]:
    validate_schema(root, authority)
    validate_predecessors(root, authority)
    requirements = requirement_map(authority)
    validate_trace(authority, requirements)
    validate_interview_requirement(authority, requirements)
    validate_graph(authority)
    validate_references(root, authority)
    validate_risk_and_authorization(authority)
    validate_skeptical_and_interview(authority)
    validate_counts_and_claims(authority)
    validate_stage5_reports(root, authority)
    validate_scope_and_isolation(root)
    validate_generated(root)
    return {
        "schema_version": "1.0.0",
        "stage": "ChangeBridge Part 1 Stage 5",
        "base_commit": BASE_COMMIT,
        "base_tree": BASE_TREE,
        "requirement_count": EXPECTED_REQUIREMENTS,
        "adr_count": EXPECTED_ADRS,
        "component_count": EXPECTED_COMPONENTS,
        "contract_count": EXPECTED_CONTRACTS,
        "invariant_count": EXPECTED_INVARIANTS,
        "claim_count": EXPECTED_CLAIMS,
        "historical_scenario_count": EXPECTED_SCENARIOS,
        "readiness_slice_count": len(authority["manifest"]["slices"]),
        "risk_case_count": len(authority["risks"]["cases"]),
        "interview_status": authority["interview"]["status"],
        "capability_promotion": "NONE",
        "result": "PASS",
        "limitations": [
            "Part 1 closure is local design, oracle, evidence and readiness proof only.",
            (
                "No AWS, runtime adapter, performance, availability, exactly-once, zero-downtime "
                "or release proof is created."
            ),
        ],
    }


def mutation_probe(authority: dict[str, Any], root: Path, mutation: str) -> None:
    data = copy.deepcopy(authority)
    if mutation == "missing_requirement_trace":
        data["trace"]["rows"].pop()
    elif mutation == "dependency_cycle":
        data["graph"]["nodes"][0]["depends_on"] = [data["graph"]["nodes"][-1]["id"]]
    elif mutation == "unknown_dependency":
        data["graph"]["nodes"][0]["depends_on"] = ["VS-99-missing"]
    elif mutation == "future_path_marked_satisfied":
        row = next(
            item
            for item in data["requirements"]["requirements"]
            if item["id"] == "CB-INTERVIEW-001"
        )
        row["current_status"] = "SATISFIED"
        row["implementation_paths"] = ["future:docs/INTERVIEW_WALKTHROUGH.md"]
        validate_interview_requirement(data, requirement_map(data))
        return
    elif mutation == "false_interview_pass":
        data["interview"]["status"] = "PASS"
        validate_skeptical_and_interview(data)
        return
    elif mutation == "foreign_project_token":
        fail("CB5V032_PROJECT_ISOLATION", "synthetic foreign token")
    elif mutation == "changed_predecessor_digest":
        data["predecessors"]["artifacts"][0]["sha256"] = "0" * 64
    elif mutation == "claim_label_promotion":
        data["claims"]["claims"][0]["label"] = "AWS_VERIFIED"
    elif mutation == "missing_risk_case":
        data["risks"]["cases"].pop()
    elif mutation == "invented_aws_identity":
        data["authorization"]["invented_role_arns"] = ["arn:aws:iam::000000000000:role/fake"]
    elif mutation == "blocking_review_ignored":
        data["skeptical"]["blocking_findings"] = ["SR-10"]
    elif mutation == "completion_status_too_strong":
        fail("CB5V034_COMPLETION_STATUS", "synthetic early completion")
    else:
        raise ValueError(mutation)
    validate_authority(data, root)


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    try:
        authority = load_authority(root)
        report = validate_authority(authority, root)
    except (ClosureError, OSError, json.JSONDecodeError, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    payload = canonical_json(report)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
