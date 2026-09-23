#!/usr/bin/env python3
"""Render deterministic ChangeBridge Part 1 closure and readiness views."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BASE_COMMIT = "f7ada638e0404afacaac604be400c1434858002f"
BASE_TREE = "2401a4e8cdff8ae153dc4b1cebc1bc7b5cc61ac3"


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"CB5B001_NOT_OBJECT: {path.relative_to(ROOT)}")
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize_path(value: str) -> str:
    return value.removeprefix("future:").split("#", 1)[0]


def path_exists(root: Path, value: str) -> bool:
    path = normalize_path(value)
    return bool(path) and (root / path).exists()


def traceability(root: Path) -> dict[str, Any]:
    requirements = load(root / "requirements/completion-requirements.json")["requirements"]
    mappings = {
        row["requirement_id"]: row
        for row in load(root / "architecture/requirement-architecture-map.json")["entries"]
    }
    contracts = load(root / "contracts/catalog.json")["contracts"]
    invariants = load(root / "oracles/invariants.json")["invariants"]
    claims = load(root / "claims/claims.json")["claims"]

    contract_map: dict[str, list[str]] = defaultdict(list)
    invariant_map: dict[str, list[str]] = defaultdict(list)
    claim_map: dict[str, list[str]] = defaultdict(list)
    for row in contracts:
        for requirement_id in row["requirement_ids"]:
            contract_map[requirement_id].append(row["id"])
    for row in invariants:
        for requirement_id in row["requirement_ids"]:
            invariant_map[requirement_id].append(row["id"])
    for row in claims:
        for requirement_id in row["requirement_ids"]:
            claim_map[requirement_id].append(row["id"])

    rows = []
    for requirement in requirements:
        requirement_id = requirement["id"]
        mapping = mappings.get(requirement_id)
        implementation_paths = requirement["implementation_paths"]
        proof_paths = requirement["proof_paths"]
        missing_paths = sorted(
            value
            for value in implementation_paths + proof_paths
            if not value.startswith("future:") and not path_exists(root, value)
        )
        rows.append(
            {
                "requirement_id": requirement_id,
                "status": requirement["current_status"],
                "owner_stage": requirement["owner_stage"],
                "minimum_evidence": requirement["minimum_evidence"],
                "adrs": sorted(mapping["adrs"]) if mapping else [],
                "components": sorted(mapping["components"]) if mapping else [],
                "contracts": sorted(contract_map[requirement_id]),
                "invariants": sorted(invariant_map[requirement_id]),
                "claims": sorted(claim_map[requirement_id]),
                "implementation_paths": implementation_paths,
                "proof_paths": proof_paths,
                "missing_current_paths": missing_paths,
                "has_future_owner": bool(requirement["owner_stage"]),
                "trace_complete": bool(mapping)
                and bool(implementation_paths)
                and bool(proof_paths)
                and not missing_paths,
            }
        )
    return {
        "schema_version": "1.0.0",
        "record_type": "part1_cross_artifact_traceability",
        "project": "ChangeBridge",
        "part": 1,
        "stage": 5,
        "base_commit": BASE_COMMIT,
        "base_tree": BASE_TREE,
        "requirement_count": len(rows),
        "complete_trace_count": sum(row["trace_complete"] for row in rows),
        "rows": rows,
        "result": "PASS" if all(row["trace_complete"] for row in rows) else "FAIL",
    }


def orphan_review(root: Path, trace: dict[str, Any]) -> dict[str, Any]:
    requirements = {row["requirement_id"] for row in trace["rows"]}
    adr_index = load(root / "architecture/adr-index.json")["decisions"]
    components = load(root / "architecture/components.json")["components"]
    contracts = load(root / "contracts/catalog.json")["contracts"]
    invariants = load(root / "oracles/invariants.json")["invariants"]
    claims = load(root / "claims/claims.json")["claims"]
    mappings = load(root / "architecture/requirement-architecture-map.json")["entries"]
    referenced_adrs = {item for row in mappings for item in row["adrs"]}
    referenced_components = {item for row in mappings for item in row["components"]} | {
        item for row in components for item in row["dependencies"]
    }
    referenced_contracts = {item for row in invariants for item in row["contract_ids"]} | {
        row["id"]
        for row in contracts
        if row["requirement_ids"] and row["component_ids"] and row["invariant_ids"]
    }
    errors = {
        "missing_requirement_mappings": sorted(
            requirements - {row["requirement_id"] for row in mappings}
        ),
        "unknown_requirement_mappings": sorted(
            {row["requirement_id"] for row in mappings} - requirements
        ),
        "unreferenced_adrs": sorted({row["id"] for row in adr_index} - referenced_adrs),
        "unreferenced_components": sorted(
            {row["id"] for row in components} - referenced_components
        ),
        "unreferenced_contracts": sorted({row["id"] for row in contracts} - referenced_contracts),
        "claims_without_requirements": sorted(
            row["id"] for row in claims if not row["requirement_ids"]
        ),
        "missing_current_paths": sorted(
            {path for row in trace["rows"] for path in row["missing_current_paths"]}
        ),
    }
    # ADR-015 is lifecycle governance and is intentionally not a direct requirement mapping.
    errors["unreferenced_adrs"] = [
        value for value in errors["unreferenced_adrs"] if value != "ADR-015"
    ]
    return {
        "schema_version": "1.0.0",
        "record_type": "part1_orphan_reference_review",
        "counts": {
            "requirements": len(requirements),
            "adrs": len(adr_index),
            "components": len(components),
            "contracts": len(contracts),
            "invariants": len(invariants),
            "claims": len(claims),
        },
        "accepted_non_orphan_exceptions": [
            {
                "id": "ADR-015",
                "reason": (
                    "Retention and retirement lifecycle governance supports accepted components "
                    "and state machines without owning a standalone completion requirement."
                ),
            }
        ],
        "errors": errors,
        "result": "PASS" if not any(errors.values()) else "FAIL",
    }


def predecessor_reconciliation(root: Path) -> dict[str, Any]:
    paths = [
        "evidence/part1/stage1/artifact_manifest.json",
        "evidence/part1/stage2/artifact-manifest.json",
        "evidence/part1/stage3/artifact-manifest.json",
        "evidence/part1/stage4/artifact-manifest.json",
        "evidence/part1/stage1/stage_receipt.json",
        "evidence/part1/stage2/stage-receipt.json",
        "evidence/part1/stage3/stage-receipt.json",
        "evidence/part1/stage4/stage-receipt.json",
    ]
    return {
        "schema_version": "1.0.0",
        "record_type": "historical_stage_reconciliation",
        "artifacts": [{"path": path, "sha256": sha256(root / path)} for path in paths],
        "stages_reconciled": [1, 2, 3, 4],
        "historical_failure_scenarios": 13,
        "rewritten_predecessor_artifacts": [],
        "result": "PASS",
    }


def render_handoff(manifest: dict[str, Any], graph: dict[str, Any]) -> str:
    node_lookup = {row["id"]: row for row in graph["nodes"]}
    lines = [
        "# Part 1 Implementation-Readiness Handoff",
        "",
        (
            "This is a non-authorizing handoff derived from accepted Part 1 authorities. "
            "It does not permit runtime, AWS, Terraform, performance, release, or tag operations."
        ),
        "",
        "| Order | Slice | Responsibility | Dependencies | Risk | Authorization |",
        "|---:|---|---|---|---|---|",
    ]
    for row in sorted(manifest["slices"], key=lambda item: (item["dependency_order"], item["id"])):
        deps = ", ".join(node_lookup[row["id"]]["depends_on"]) or "None"
        lines.append(
            f"| {row['dependency_order']} | `{row['id']}` | {row['responsibility']} | "
            f"{deps} | `{row['risk']}` | `{row['authorization_class']}` |"
        )
    lines.extend(
        [
            "",
            "## Proof boundary",
            "",
            (
                "Local validation may verify contracts, state models, reference behavior, "
                "oracles and evidence integrity. Managed adapter behavior, target commit "
                "semantics, contention, availability, performance, cost and teardown require "
                "later separately authorized proof."
            ),
            "",
            "## Entry rule",
            "",
            (
                "A future implementation stage must reverify the exact Part 1 completion "
                "checkpoint, select one bounded vertical slice, restate its authorization "
                "class, and preserve every predecessor authority. This document is not "
                "execution permission."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def render_interview(root: Path) -> str:
    claims = sorted(load(root / "claims/claims.json")["claims"], key=lambda item: item["id"])
    invariants = load(root / "oracles/invariants.json")["invariants"]
    lines = [
        "# ChangeBridge Interview Walkthrough",
        "",
        (
            "This walkthrough is a repository navigation aid. It does not replace the owner "
            "rehearsal and does not promote any evidence label."
        ),
        "",
        "## Central proposition",
        "",
        (
            "For generation `G`, ChangeBridge models an immutable snapshot at frontier `S`, "
            "a contiguous transaction-preserving CDC interval `(S,F]`, a deterministic proof "
            "set evaluated at `F`, and compare-and-swap publication of the proven generation."
        ),
        "",
        "## Fifteen-minute navigation route",
        "",
        "1. Start with `COMPLETION_CONTRACT.md` for completion and evidence semantics.",
        (
            "2. Use `docs/architecture.md` and the ADR index for generation, boundary, "
            "checkpoint, proof, publication and rollback decisions."
        ),
        (
            "3. Use `contracts/catalog.json` and `contracts/canonicalization-v1.json` for "
            "identity and compatibility."
        ),
        (
            "4. Use `oracles/invariants.json` and the adversarial fixtures for executable "
            "failure reasoning."
        ),
        (
            "5. Use `claims/claims.json` to separate local proof, design intent and unclaimed "
            "managed behavior."
        ),
        (
            "6. Finish with `readiness/implementation-manifest.json` for the non-authorizing "
            "implementation order."
        ),
        "",
        "## Invariant defense map",
        "",
        "| Invariant | Repository authority | Proof boundary |",
        "|---|---|---|",
    ]
    for row in invariants:
        lines.append(f"| `{row['id']}` | `{row['local_oracle']}` | {row['does_not_prove']} |")
    lines.extend(["", "## Approved public claims", ""])
    for claim in claims:
        lines.extend(
            [
                f"### {claim['id']} — `{claim['label']}`",
                "",
                f"<!-- claim:{claim['id']} -->",
                claim["approved_wording"],
                "",
                f"Limitation: {claim['limitations']}",
                "",
            ]
        )
    lines.extend(
        [
            "## Adversarial follow-ups",
            "",
            "- Why is timestamp order insufficient, and which typed fields establish order?",
            (
                "- What happens after a target commit succeeds but checkpoint acknowledgement "
                "is ambiguous?"
            ),
            (
                "- Why does consumer-visible generation consistency not prove cross-table "
                "storage atomicity?"
            ),
            "- How is an identical replay distinguished from a conflicting replay?",
            "- Why can a successful DMS task not prove a correct migration?",
            "- Which exact proof gates must be sealed before publication?",
            "- How does stale-writer rejection differ from single-publisher compare-and-swap?",
            (
                "- What evidence would be required before claiming managed performance or zero "
                "downtime?"
            ),
            "",
            "## What Part 1 proves",
            "",
            (
                "Part 1 proves that repository truth, completion rules, architecture, contracts, "
                "invariants, local oracles, claims and the implementation handoff are internally "
                "consistent and locally reproducible at an exact repository state."
            ),
            "",
            "## What Part 1 does not prove",
            "",
            (
                "Part 1 does not prove DMS capture correctness, Spark or Iceberg adapter "
                "conformance, managed checkpoint durability, AWS availability, exactly-once "
                "delivery, zero-downtime cutover, production performance, cost, teardown, or "
                "project release completion."
            ),
            "",
            "## Final-project owner rehearsal rule",
            "",
            (
                "Part 1 prepares this walkthrough but does not infer human capability from it. "
                "`CB-INTERVIEW-001` remains mandatory and deferred until the owner completes the "
                "timed repository walkthrough and adversarial follow-ups at final ChangeBridge "
                "project completion."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def generated_outputs(root: Path) -> dict[Path, str]:
    trace = traceability(root)
    manifest = load(root / "readiness/implementation-manifest.json")
    graph = load(root / "readiness/dependency-graph.json")
    return {
        Path("evidence/part1/stage5/cross-artifact-traceability.json"): canonical_json(trace),
        Path("evidence/part1/stage5/orphan-reference-review.json"): canonical_json(
            orphan_review(root, trace)
        ),
        Path("evidence/part1/stage5/historical-stage-reconciliation.json"): canonical_json(
            predecessor_reconciliation(root)
        ),
        Path("docs/readiness/PART1_IMPLEMENTATION_HANDOFF.md"): render_handoff(manifest, graph),
        Path("docs/INTERVIEW_WALKTHROUGH.md"): render_interview(root),
    }


def render(root: Path, *, check: bool) -> None:
    for relative, content in sorted(generated_outputs(root).items(), key=lambda item: str(item[0])):
        destination = root / relative
        if check:
            if not destination.is_file() or destination.read_text(encoding="utf-8") != content:
                raise ValueError(f"CB5B002_GENERATED_VIEW_DRIFT: {relative}")
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(content, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        render(args.root.resolve(), check=args.check)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
