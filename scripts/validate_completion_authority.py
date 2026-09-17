#!/usr/bin/env python3
"""Validate and render ChangeBridge completion and claim authority.

The validator is dependency-free, deterministic, and fail-closed. It validates
authoritative registries, proof paths, public claim wording, Stage 1 inventory
coverage, and failure-lab documentation parity. It never executes AWS operations.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS_PATH = Path("requirements/completion-requirements.json")
CLAIMS_PATH = Path("claims/claims.json")
STAGE1_INVENTORY_PATH = Path("evidence/part1/stage1/public_claims_inventory.json")

ALLOWED_LABELS = {
    "DESIGN_ONLY",
    "LOCAL_VERIFIED",
    "AWS_VERIFIED",
    "MEASURED",
    "EXTRAPOLATED",
    "UNCLAIMED",
}
ALLOWED_STATUSES = {"SATISFIED", "PARTIAL", "UNSATISFIED", "DEFERRED", "BLOCKED"}
ALLOWED_NORMATIVE = {"MUST", "MUST NOT", "SHOULD", "MAY"}
ALLOWED_DISPOSITIONS = {
    "RETAINED",
    "CORRECTED",
    "DOWNGRADED",
    "FROZEN",
    "REMOVED_DUPLICATE",
    "WITHDRAWN_UNSUPPORTED",
}
ALLOWED_REVIEW_STATUS = {"APPROVED", "UNCLAIMED", "WITHDRAWN"}
REQUIREMENT_FAMILIES = {
    "BOUNDARY",
    "ORDER",
    "APPLY",
    "CHECKPOINT",
    "SCHEMA",
    "ISOLATION",
    "RECON",
    "PUBLISH",
    "OPS",
    "SEC",
    "EVIDENCE",
    "RELEASE",
    "INTERVIEW",
}
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
REQUIREMENT_KEYS = {
    "id",
    "title",
    "normative",
    "statement",
    "rationale",
    "scope",
    "source_conditions",
    "source_invariants",
    "dependencies",
    "current_status",
    "owner_stage",
    "verification_method",
    "minimum_evidence",
    "implementation_paths",
    "proof_paths",
    "failure_condition",
    "limitations",
    "review_notes",
}
CLAIM_KEYS = {
    "id",
    "source_claim_ids",
    "approved_wording",
    "scope",
    "label",
    "requirement_ids",
    "proof_refs",
    "producing_commit",
    "producing_run",
    "limitations",
    "public_surfaces",
    "review_status",
    "owner",
    "invalidation_conditions",
    "disposition",
    "measurement",
    "extrapolation",
}
VOLATILE_KEYS = {"generated_at", "timestamp", "hostname", "temporary_path", "temp_path"}
REQUIREMENT_ID = re.compile(r"^CB-([A-Z]+)-[0-9]{3}$")
CLAIM_ID = re.compile(r"^CB-CLAIM-[0-9]{3}$")
COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
MARKER = re.compile(r"<!-- claim:(CB-CLAIM-[0-9]{3}) -->")
OPERATIONAL_NUMBER = re.compile(
    r"\b(?:p50|p95|p99|throughput|latency|recovery|cost|availability|rows?/s|seconds?|minutes?)\b.*\d",
    re.IGNORECASE,
)


class AuthorityError(ValueError):
    """A stable fail-closed validation error."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AuthorityError("CBV001_INVALID_JSON", str(path)) from exc
    if not isinstance(value, dict):
        raise AuthorityError("CBV001_INVALID_JSON", f"{path} must contain an object")
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def normalized_text(value: str) -> str:
    return " ".join(value.split())


def _walk_for_volatile_keys(value: Any, location: str = "root") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in VOLATILE_KEYS:
                raise AuthorityError("CBV021_VOLATILE_CANONICAL_FIELD", f"{location}.{key}")
            _walk_for_volatile_keys(child, f"{location}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _walk_for_volatile_keys(child, f"{location}[{index}]")


def _safe_existing_path(root: Path, value: str, code: str, owner: str) -> Path:
    supplied = Path(value)
    if supplied.is_absolute() or ".." in supplied.parts:
        raise AuthorityError(code, f"{owner}: unsafe path {value}")
    candidate = (root / supplied).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise AuthorityError(code, f"{owner}: path escapes repository: {value}") from exc
    if not candidate.exists():
        raise AuthorityError(code, f"{owner}: missing path {value}")
    return candidate


def _validate_dag(rows: list[dict[str, Any]], ids: set[str]) -> None:
    incoming = {item_id: 0 for item_id in ids}
    outgoing: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        for dependency in row["dependencies"]:
            if dependency not in ids:
                raise AuthorityError(
                    "CBV006_UNKNOWN_REQUIREMENT_DEPENDENCY",
                    f"{row['id']} -> {dependency}",
                )
            outgoing[dependency].append(row["id"])
            incoming[row["id"]] += 1
    queue = deque(sorted(item_id for item_id, count in incoming.items() if count == 0))
    visited = 0
    while queue:
        item_id = queue.popleft()
        visited += 1
        for child in sorted(outgoing[item_id]):
            incoming[child] -= 1
            if incoming[child] == 0:
                queue.append(child)
    if visited != len(ids):
        cycle = sorted(item_id for item_id, count in incoming.items() if count)
        raise AuthorityError("CBV007_REQUIREMENT_CYCLE", ", ".join(cycle))


def _forbidden_project_tokens() -> tuple[str, ...]:
    # Constructed to keep unrelated project names out of ChangeBridge public authority text.
    return ("ledger" + "guard", "atlas" + "retail", "event" + "pulse", "feature" + "forge")


def validate_requirements(document: dict[str, Any], root: Path) -> dict[str, Any]:
    _walk_for_volatile_keys(document, "requirements")
    expected_top = {"schema_version", "project", "authority", "status_values", "requirements"}
    if set(document) != expected_top:
        raise AuthorityError("CBV002_UNKNOWN_TOP_LEVEL_FIELD", "requirements registry")
    if document["schema_version"] != "1.0.0" or document["project"] != "ChangeBridge":
        raise AuthorityError("CBV003_INVALID_REGISTRY_IDENTITY", "requirements registry")
    rows = document["requirements"]
    if not isinstance(rows, list) or not rows:
        raise AuthorityError("CBV004_MISSING_REQUIREMENT_COLLECTION", "requirements")

    ids: set[str] = set()
    condition_coverage: set[int] = set()
    invariant_coverage: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != REQUIREMENT_KEYS:
            row_id = row.get("id", "unknown") if isinstance(row, dict) else "unknown"
            raise AuthorityError("CBV005_INVALID_REQUIREMENT_FIELDS", str(row_id))
        match = REQUIREMENT_ID.fullmatch(row["id"])
        if match is None or match.group(1) not in REQUIREMENT_FAMILIES:
            raise AuthorityError("CBV008_INVALID_REQUIREMENT_ID", row["id"])
        if row["id"] in ids:
            raise AuthorityError("CBV009_DUPLICATE_REQUIREMENT_ID", row["id"])
        ids.add(row["id"])
        if row["normative"] not in ALLOWED_NORMATIVE:
            raise AuthorityError("CBV010_INVALID_NORMATIVE_LEVEL", row["id"])
        if row["current_status"] not in ALLOWED_STATUSES:
            raise AuthorityError("CBV011_INVALID_REQUIREMENT_STATUS", row["id"])
        if row["minimum_evidence"] not in ALLOWED_LABELS:
            raise AuthorityError("CBV012_UNKNOWN_EVIDENCE_LABEL", row["id"])
        if row["normative"] in {"MUST", "MUST NOT"} and not row["failure_condition"].strip():
            raise AuthorityError("CBV013_MISSING_FAILURE_CONDITION", row["id"])
        if not row["owner_stage"].strip() or not row["verification_method"].strip():
            raise AuthorityError("CBV014_MISSING_OWNER_OR_VERIFICATION", row["id"])
        if not row["source_conditions"] or not all(
            isinstance(value, int) and 1 <= value <= 16 for value in row["source_conditions"]
        ):
            raise AuthorityError("CBV015_INVALID_SOURCE_CONDITION", row["id"])
        if not row["source_invariants"] or not set(row["source_invariants"]) <= REQUIRED_INVARIANTS:
            raise AuthorityError("CBV016_INVALID_SOURCE_INVARIANT", row["id"])
        condition_coverage.update(row["source_conditions"])
        invariant_coverage.update(row["source_invariants"])
        for path in row["implementation_paths"] + row["proof_paths"]:
            if path.startswith("future:"):
                if row["current_status"] == "SATISFIED":
                    raise AuthorityError("CBV017_FUTURE_PROOF_FOR_SATISFIED_REQUIREMENT", row["id"])
                continue
            _safe_existing_path(root, path, "CBV018_MISSING_OR_UNSAFE_REQUIREMENT_PATH", row["id"])

    _validate_dag(rows, ids)
    if condition_coverage != set(range(1, 17)):
        missing = sorted(set(range(1, 17)) - condition_coverage)
        raise AuthorityError("CBV019_INCOMPLETE_COMPLETION_CONDITION_COVERAGE", str(missing))
    if invariant_coverage != REQUIRED_INVARIANTS:
        missing = sorted(REQUIRED_INVARIANTS - invariant_coverage)
        raise AuthorityError("CBV020_INCOMPLETE_INVARIANT_COVERAGE", str(missing))
    return {
        "condition_coverage": sorted(condition_coverage),
        "invariant_coverage": sorted(invariant_coverage),
        "requirement_count": len(rows),
        "requirement_ids": ids,
    }


def validate_claims(
    document: dict[str, Any],
    requirement_ids: set[str],
    root: Path,
    surface_overrides: dict[str, str] | None = None,
) -> dict[str, Any]:
    _walk_for_volatile_keys(document, "claims")
    expected_top = {"schema_version", "project", "allowed_labels", "claims"}
    if set(document) != expected_top:
        raise AuthorityError("CBV002_UNKNOWN_TOP_LEVEL_FIELD", "claim registry")
    if document["schema_version"] != "1.0.0" or document["project"] != "ChangeBridge":
        raise AuthorityError("CBV003_INVALID_REGISTRY_IDENTITY", "claim registry")
    if set(document["allowed_labels"]) != ALLOWED_LABELS:
        raise AuthorityError("CBV012_UNKNOWN_EVIDENCE_LABEL", "allowed_labels")
    rows = document["claims"]
    if not isinstance(rows, list) or not rows:
        raise AuthorityError("CBV022_MISSING_CLAIM_COLLECTION", "claims")

    serialized = normalized_text(canonical_json(document)).lower()
    forbidden = [token for token in _forbidden_project_tokens() if token in serialized]
    if forbidden:
        raise AuthorityError("CBV023_CROSS_PROJECT_REFERENCE", ", ".join(sorted(forbidden)))

    ids: set[str] = set()
    source_ids: set[str] = set()
    surfaces: dict[str, str] = {}
    labels: set[str] = set()
    for claim in rows:
        if not isinstance(claim, dict) or not set(claim) <= CLAIM_KEYS or not (
            CLAIM_KEYS - {"measurement", "extrapolation"}
        ) <= set(claim):
            claim_id = claim.get("id", "unknown") if isinstance(claim, dict) else "unknown"
            raise AuthorityError("CBV024_INVALID_CLAIM_FIELDS", str(claim_id))
        if CLAIM_ID.fullmatch(claim["id"]) is None:
            raise AuthorityError("CBV025_INVALID_CLAIM_ID", claim["id"])
        if claim["id"] in ids:
            raise AuthorityError("CBV026_DUPLICATE_CLAIM_ID", claim["id"])
        ids.add(claim["id"])
        labels.add(claim["label"])
        if claim["label"] not in ALLOWED_LABELS:
            raise AuthorityError("CBV012_UNKNOWN_EVIDENCE_LABEL", claim["id"])
        if claim["review_status"] not in ALLOWED_REVIEW_STATUS:
            raise AuthorityError("CBV027_INVALID_REVIEW_STATUS", claim["id"])
        if claim["disposition"] not in ALLOWED_DISPOSITIONS:
            raise AuthorityError("CBV028_INVALID_DISPOSITION", claim["id"])
        if not set(claim["requirement_ids"]) <= requirement_ids:
            raise AuthorityError("CBV029_UNKNOWN_CLAIM_REQUIREMENT", claim["id"])
        if not claim["limitations"].strip() or not claim["invalidation_conditions"]:
            raise AuthorityError("CBV030_MISSING_CLAIM_BOUNDARY", claim["id"])
        for source_id in claim["source_claim_ids"]:
            if source_id.startswith("PC-") and source_id in source_ids:
                raise AuthorityError("CBV031_DUPLICATE_SOURCE_CLAIM", source_id)
            source_ids.add(source_id)

        label = claim["label"]
        proof_refs = claim["proof_refs"]
        commit = claim["producing_commit"]
        run = claim["producing_run"]
        if label == "UNCLAIMED":
            if proof_refs or commit is not None or run is not None:
                raise AuthorityError("CBV032_UNCLAIMED_WITH_PROOF", claim["id"])
        else:
            if not proof_refs:
                raise AuthorityError("CBV033_CURRENT_CLAIM_WITHOUT_PROOF", claim["id"])
            if not isinstance(commit, str) or COMMIT_SHA.fullmatch(commit) is None:
                raise AuthorityError("CBV034_INVALID_COMMIT_BINDING", claim["id"])
            for path in proof_refs:
                if path.startswith("future:"):
                    raise AuthorityError("CBV035_FUTURE_PROOF_FOR_CURRENT_CLAIM", claim["id"])
                _safe_existing_path(root, path, "CBV036_MISSING_OR_UNSAFE_CLAIM_PROOF", claim["id"])
        if label == "AWS_VERIFIED":
            if not run or not any(path.startswith("evidence/managed/") for path in proof_refs):
                raise AuthorityError("CBV037_UNSUPPORTED_AWS_CLAIM", claim["id"])
        if label == "MEASURED":
            measurement = claim.get("measurement")
            if not isinstance(measurement, dict) or not {
                "workload",
                "raw_observations",
                "method",
                "environment",
                "bounds",
            } <= set(measurement):
                raise AuthorityError("CBV038_UNBOUND_MEASUREMENT", claim["id"])
        if label == "EXTRAPOLATED":
            extrapolation = claim.get("extrapolation")
            if not isinstance(extrapolation, dict) or not {
                "measured_basis",
                "method",
                "assumptions",
                "range",
                "limitations",
            } <= set(extrapolation):
                raise AuthorityError("CBV039_UNBOUND_EXTRAPOLATION", claim["id"])
        if OPERATIONAL_NUMBER.search(claim["approved_wording"]) and label not in {
            "MEASURED",
            "EXTRAPOLATED",
            "UNCLAIMED",
        }:
            raise AuthorityError("CBV040_UNBOUND_NUMERIC_CLAIM", claim["id"])

        for surface in claim["public_surfaces"]:
            if set(surface) != {"path", "marker"} or surface["marker"] != claim["id"]:
                raise AuthorityError("CBV041_INVALID_PUBLIC_SURFACE", claim["id"])
            path = surface["path"]
            if path not in surfaces:
                if surface_overrides is not None and path in surface_overrides:
                    surfaces[path] = surface_overrides[path]
                else:
                    surfaces[path] = _safe_existing_path(
                        root, path, "CBV041_INVALID_PUBLIC_SURFACE", claim["id"]
                    ).read_text(encoding="utf-8")
            marker = f"<!-- claim:{claim['id']} -->"
            normalized_surface = normalized_text(surfaces[path])
            if marker not in surfaces[path] or normalized_text(claim["approved_wording"]) not in normalized_surface:
                raise AuthorityError("CBV042_PUBLIC_WORDING_DRIFT", f"{claim['id']} in {path}")

    marker_ids: set[str] = set()
    for path, content in surfaces.items():
        for marker_id in MARKER.findall(content):
            marker_ids.add(marker_id)
            if marker_id not in ids:
                raise AuthorityError("CBV043_UNREGISTERED_PUBLIC_CLAIM", f"{marker_id} in {path}")

    inventory = load_json(root / STAGE1_INVENTORY_PATH)
    inventory_ids = {row["claim_id"] for row in inventory["claims"]}
    public_inventory_ids = {item for item in source_ids if item.startswith("PC-")}
    if public_inventory_ids != inventory_ids:
        missing = sorted(inventory_ids - public_inventory_ids)
        extra = sorted(public_inventory_ids - inventory_ids)
        raise AuthorityError("CBV044_ORPHAN_STAGE1_CLAIM", f"missing={missing}, extra={extra}")
    return {
        "claim_count": len(rows),
        "claim_ids": ids,
        "labels": sorted(labels),
        "source_claim_ids": sorted(source_ids),
        "surface_count": len(surfaces),
    }


def simulator_check_names(root: Path) -> list[str]:
    tree = ast.parse((root / "src/changebridge/simulator.py").read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "record"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            names.append(node.args[0].value)
    return names


def validate_failure_lab(root: Path, documentation_override: str | None = None) -> dict[str, Any]:
    executable = simulator_check_names(root)
    documentation = (
        documentation_override
        if documentation_override is not None
        else (root / "docs/failure-lab.md").read_text(encoding="utf-8")
    )
    documented = re.findall(r"^\| `([a-z0-9_]+)` \|", documentation, flags=re.MULTILINE)
    if len(executable) != 13 or executable != documented:
        raise AuthorityError(
            "CBV045_FAILURE_LAB_PARITY",
            f"executable={executable}, documented={documented}",
        )
    return {"count": len(executable), "checks": executable}


def validate_authority(
    requirements_document: dict[str, Any],
    claims_document: dict[str, Any],
    root: Path = ROOT,
    surface_overrides: dict[str, str] | None = None,
    failure_lab_override: str | None = None,
) -> dict[str, Any]:
    requirements = validate_requirements(requirements_document, root)
    claims = validate_claims(
        claims_document,
        requirements["requirement_ids"],
        root,
        surface_overrides,
    )
    failure_lab = validate_failure_lab(root, failure_lab_override)
    return {
        "claim_count": claims["claim_count"],
        "completion_conditions": requirements["condition_coverage"],
        "failure_lab_checks": failure_lab["checks"],
        "invariants": requirements["invariant_coverage"],
        "labels_in_use": claims["labels"],
        "requirement_count": requirements["requirement_count"],
        "result": "PASS",
        "schema_version": "1.0.0",
        "stage": "ChangeBridge Part 1 Stage 2",
    }


def proof_matrix(requirements_document: dict[str, Any]) -> dict[str, Any]:
    entries = []
    for row in sorted(requirements_document["requirements"], key=lambda item: item["id"]):
        entries.append(
            {
                "current_proof_paths": sorted(
                    path for path in row["proof_paths"] if not path.startswith("future:")
                ),
                "future_proof_paths": sorted(
                    path for path in row["proof_paths"] if path.startswith("future:")
                ),
                "implementation_paths": sorted(row["implementation_paths"]),
                "minimum_evidence": row["minimum_evidence"],
                "owner_stage": row["owner_stage"],
                "requirement_id": row["id"],
                "status": row["current_status"],
                "verification_method": row["verification_method"],
            }
        )
    return {"entries": entries, "schema_version": "1.0.0"}


def render_requirements(requirements_document: dict[str, Any]) -> str:
    lines = [
        "# ChangeBridge Requirement Catalog",
        "",
        "Generated deterministically from `requirements/completion-requirements.json`.",
        "The JSON registry is authoritative.",
        "",
    ]
    for row in sorted(requirements_document["requirements"], key=lambda item: item["id"]):
        lines.extend(
            [
                f"## {row['id']} — {row['title']}",
                "",
                f"- Normative level: `{row['normative']}`",
                f"- Current status: `{row['current_status']}`",
                f"- Minimum evidence: `{row['minimum_evidence']}`",
                f"- Owner: `{row['owner_stage']}`",
                f"- Source conditions: {', '.join(map(str, row['source_conditions']))}",
                f"- Source invariants: {', '.join(row['source_invariants'])}",
                "",
                row["statement"],
                "",
                f"**Failure condition:** {row['failure_condition']}",
                "",
                f"**Current limitation:** {row['limitations']}",
                "",
            ]
        )
    return "\n".join(lines)


def render_matrix(matrix: dict[str, Any]) -> str:
    lines = [
        "# ChangeBridge Requirement-to-Proof Matrix",
        "",
        "Generated deterministically from the authoritative requirements registry.",
        "",
        "| Requirement | Status | Minimum evidence | Owner | Current proof | Future proof |",
        "|---|---|---|---|---|---|",
    ]
    for row in matrix["entries"]:
        current = "<br>".join(f"`{path}`" for path in row["current_proof_paths"]) or "None"
        future = "<br>".join(f"`{path}`" for path in row["future_proof_paths"]) or "None"
        lines.append(
            f"| `{row['requirement_id']}` | `{row['status']}` | `{row['minimum_evidence']}` "
            f"| `{row['owner_stage']}` | {current} | {future} |"
        )
    lines.append("")
    return "\n".join(lines)


def render_claims(claims_document: dict[str, Any]) -> str:
    lines = [
        "# ChangeBridge Claims",
        "",
        "Generated deterministically from `claims/claims.json`. The registry is authoritative.",
        "No claim on this page changes an evidence label by presentation alone.",
        "",
    ]
    for claim in sorted(claims_document["claims"], key=lambda item: item["id"]):
        lines.extend(
            [
                f"## {claim['id']} — {claim['label']}",
                "",
                f"<!-- claim:{claim['id']} -->",
                claim["approved_wording"],
                "",
                f"- Scope: {claim['scope']}",
                f"- Limitations: {claim['limitations']}",
                f"- Requirements: {', '.join(f'`{item}`' for item in claim['requirement_ids'])}",
                f"- Disposition: `{claim['disposition']}`",
                "",
            ]
        )
    return "\n".join(lines)


def generated_outputs(
    requirements_document: dict[str, Any], claims_document: dict[str, Any]
) -> dict[Path, str]:
    matrix = proof_matrix(requirements_document)
    return {
        Path("CLAIMS.md"): render_claims(claims_document),
        Path("requirements/REQUIREMENT_CATALOG.md"): render_requirements(requirements_document),
        Path("requirements/REQUIREMENT_PROOF_MATRIX.md"): render_matrix(matrix),
        Path("requirements/requirement-proof-matrix.json"): canonical_json(matrix),
    }


def write_generated(root: Path, outputs: dict[Path, str]) -> None:
    for relative, content in sorted(outputs.items(), key=lambda item: str(item[0])):
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")


def check_generated(root: Path, outputs: dict[Path, str]) -> None:
    for relative, expected in sorted(outputs.items(), key=lambda item: str(item[0])):
        path = root / relative
        if not path.is_file() or path.read_text(encoding="utf-8") != expected:
            raise AuthorityError("CBV046_GENERATED_OUTPUT_DRIFT", str(relative))


def run(root: Path, *, render: bool, check_rendered: bool) -> dict[str, Any]:
    requirements_document = load_json(root / REQUIREMENTS_PATH)
    claims_document = load_json(root / CLAIMS_PATH)
    outputs = generated_outputs(requirements_document, claims_document)
    if render:
        write_generated(root, outputs)
    if check_rendered:
        check_generated(root, outputs)
    report = validate_authority(requirements_document, claims_document, root)
    payload = canonical_json(report)
    report["canonical_sha256"] = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--render", action="store_true", help="write deterministic rendered files")
    parser.add_argument(
        "--check-rendered", action="store_true", help="fail when rendered files are stale"
    )
    parser.add_argument("--output", type=Path, help="write canonical validation JSON")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = run(args.root.resolve(), render=args.render, check_rendered=args.check_rendered)
    except AuthorityError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    payload = canonical_json(report)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
