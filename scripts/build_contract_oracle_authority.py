#!/usr/bin/env python3
"""Render deterministic Stage 4 contract, oracle, and test-authority views."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def render_catalog(catalog: dict[str, Any]) -> str:
    lines = [
        "# Contract Catalog",
        "",
        "Generated from `contracts/catalog.json`; the JSON registry is authoritative.",
        "",
        "| Contract | Version | Owner | Authority | Local validator |",
        "|---|---:|---|---|---|",
    ]
    for row in sorted(catalog["contracts"], key=lambda item: item["id"]):
        authority = row["authority_path"] + row["schema_pointer"]
        lines.append(
            f"| `{row['id']}` | `{row['version']}` | {row['owner']} | "
            f"`{authority}` | `{row['local_validator']}` |"
        )
    lines.extend(
        [
            "",
            "All v1 contracts reject unknown fields and unknown versions. Contract presence is "
            "specification authority, not runtime-conformance proof.",
            "",
        ]
    )
    return "\n".join(lines)


def render_invariants(document: dict[str, Any]) -> str:
    lines = [
        "# Invariant Oracles",
        "",
        "Generated from `oracles/invariants.json`; the JSON registry and referenced Python "
        "predicates are authoritative.",
        "",
    ]
    for row in document["invariants"]:
        lines.extend(
            [
                f"## `{row['id']}` — {row['title']}",
                "",
                row["normative_statement"],
                "",
                f"- Predicate: {row['predicate']}",
                f"- Local oracle: `{row['local_oracle']}`",
                f"- Proves: {row['proves']}",
                f"- Does not prove: {row['does_not_prove']}",
                f"- Evidence label: `{row['evidence_label']}`",
                "",
            ]
        )
    return "\n".join(lines)


def render_layers(document: dict[str, Any]) -> str:
    lines = [
        "# Test Architecture",
        "",
        "Generated from `testing/test-layers.json`; each layer has an explicit proof boundary.",
        "",
        "| Layer | Proves | Does not prove | CI | Future owner |",
        "|---|---|---|---|---|",
    ]
    for row in document["layers"]:
        lines.append(
            f"| `{row['id']}` | {row['proof_target']} | {row['non_proof_boundary']} | "
            f"{row['ci_placement']} | `{row['future_owner']}` |"
        )
    lines.append("")
    return "\n".join(lines)


def render_requirement_matrix(document: dict[str, Any]) -> str:
    rows: list[tuple[str, str, str, str, str]] = []
    for invariant in document["invariants"]:
        for requirement in invariant["requirement_ids"]:
            rows.append(
                (
                    requirement,
                    ", ".join(invariant["adr_ids"]),
                    ", ".join(invariant["component_ids"]),
                    ", ".join(invariant["contract_ids"]),
                    invariant["id"],
                )
            )
    lines = [
        "# Requirement-to-Oracle Matrix",
        "",
        "Generated from `oracles/invariants.json`.",
        "",
        "| Requirement | ADR | Component | Contract | Invariant/oracle |",
        "|---|---|---|---|---|",
    ]
    for requirement, adrs, components, contracts, invariant in sorted(rows):
        lines.append(f"| `{requirement}` | {adrs} | {components} | {contracts} | `{invariant}` |")
    lines.append("")
    return "\n".join(lines)


def render_scenario_matrix(
    invariants: dict[str, Any], cases: dict[str, Any], adversarial: dict[str, Any]
) -> str:
    titles = {row["id"]: row["title"] for row in invariants["invariants"]}
    lines = [
        "# Scenario-to-Oracle Matrix",
        "",
        "Generated from the deterministic oracle and adversarial fixture corpora.",
        "",
        "## Positive and minimal counterexample cases",
        "",
        "| Scenario | Invariant | Expected |",
        "|---|---|---:|",
    ]
    for row in cases["cases"]:
        expected = "PASS" if row["expected"] else "FAIL"
        lines.append(
            f"| `{row['scenario_id']}` | `{row['invariant_id']}` — "
            f"{titles[row['invariant_id']]} | {expected} |"
        )
    lines.extend(
        [
            "",
            "## Adversarial cases",
            "",
            "| Scenario | Mutation | Exact diagnostic | Invariants |",
            "|---|---|---|---|",
        ]
    )
    for row in adversarial["cases"]:
        lines.append(
            f"| `{row['id']}` | `{row['mutation']}` | `{row['expected_diagnostic']}` | "
            f"{', '.join(row['invariant_ids'])} |"
        )
    lines.append("")
    return "\n".join(lines)


def generated_outputs(root: Path) -> dict[Path, str]:
    catalog = load(root / "contracts/catalog.json")
    invariants = load(root / "oracles/invariants.json")
    layers = load(root / "testing/test-layers.json")
    cases = load(root / "tests/fixtures/contract-oracle-authority/oracle-cases.json")
    adversarial = load(root / "tests/fixtures/contract-oracle-authority/adversarial-cases.json")
    return {
        Path("docs/contracts/CONTRACT_CATALOG.md"): render_catalog(catalog),
        Path("docs/testing/INVARIANT_ORACLES.md"): render_invariants(invariants),
        Path("docs/testing/TEST_ARCHITECTURE.md"): render_layers(layers),
        Path("docs/testing/REQUIREMENT_ORACLE_MATRIX.md"): render_requirement_matrix(invariants),
        Path("docs/testing/SCENARIO_ORACLE_MATRIX.md"): render_scenario_matrix(
            invariants, cases, adversarial
        ),
    }


def render(root: Path, *, check: bool) -> None:
    for relative, content in sorted(generated_outputs(root).items(), key=lambda item: str(item[0])):
        path = root / relative
        if check:
            if not path.is_file() or path.read_text(encoding="utf-8") != content:
                raise ValueError(f"CB4B001_GENERATED_VIEW_DRIFT: {relative}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")


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
