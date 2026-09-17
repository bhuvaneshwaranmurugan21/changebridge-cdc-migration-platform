#!/usr/bin/env python3
"""Validate ChangeBridge Part 1 Stage 3 architecture authority fail closed."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import deque
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn

SCHEMA_VERSION = "1.0.0"
AUTHORITY = "ChangeBridge Part 1 Stage 3"
ARCHITECTURE_FREEZE_COMMIT = "0a27be6a197fa6e849958957e7df1447f2b4f797"
PLANES = {"data", "control", "evidence"}
CANONICAL_STATES = {
    "CREATED",
    "SNAPSHOT_LOADING",
    "CDC_APPLYING",
    "SEALED",
    "PROVING",
    "PROVEN",
    "PUBLISHED",
    "REJECTED",
    "ROLLED_BACK",
    "RETIRED",
}
REQUIRED_GATES = {
    "continuity",
    "schema",
    "deletes",
    "reconciliation",
    "lag",
    "pre_migration",
    "rollback_readiness",
    "evidence_integrity",
}
STAGE3_REQUIREMENTS = {
    "CB-BOUNDARY-001",
    "CB-BOUNDARY-002",
    "CB-CHECKPOINT-001",
    "CB-ISOLATION-001",
    "CB-RECON-001",
}
ALLOWED_CLAIM_LABELS = {
    "DESIGN_ONLY",
    "LOCAL_VERIFIED",
    "AWS_VERIFIED",
    "MEASURED",
    "EXTRAPOLATED",
    "UNCLAIMED",
}
FORBIDDEN_PROJECT_TERMS = (
    "ledger" + "guard",
    "atlas" + "retail",
    "event" + "pulse",
    "feature" + "forge",
)


class ArchitectureError(Exception):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


def fail(code: str, detail: str) -> NoReturn:
    raise ArchitectureError(code, detail)


def canonical_json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        fail("CBAV001_INVALID_JSON", f"{path}: {exc}")


def require_keys(
    row: dict[str, Any],
    required: set[str],
    allowed: set[str],
    code: str,
    label: str,
) -> None:
    if not required.issubset(row) or not set(row).issubset(allowed):
        missing = sorted(required - set(row))
        unknown = sorted(set(row) - allowed)
        fail(code, f"{label}: missing={missing}, unknown={unknown}")


def safe_repo_path(value: str, code: str) -> None:
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or not value or "\\" in value:
        fail(code, value)


def load_authority(root: Path) -> dict[str, Any]:
    return {
        "components": load_json(root / "architecture/components.json"),
        "adrs": load_json(root / "architecture/adr-index.json"),
        "generation": load_json(root / "architecture/generation-state-machine.json"),
        "checkpoint": load_json(root / "architecture/checkpoint-state-machine.json"),
        "proof": load_json(root / "architecture/proof-state-machine.json"),
        "publication": load_json(root / "architecture/publication-state-machine.json"),
        "requirement_map": load_json(root / "architecture/requirement-architecture-map.json"),
        "requirement_catalog": load_json(root / "requirements/completion-requirements.json"),
        "claims": load_json(root / "claims/claims.json"),
        "claim_impact": load_json(root / "evidence/part1/stage3/claim-impact-review.json"),
    }


def validate_components(
    document: dict[str, Any],
    requirement_ids: set[str],
    adr_ids: set[str],
) -> set[str]:
    require_keys(
        document,
        {"schema_version", "authority", "planes", "components"},
        {"schema_version", "authority", "planes", "components"},
        "CBAV002_INVALID_COMPONENT_DOCUMENT",
        "components",
    )
    if document["schema_version"] != SCHEMA_VERSION or document["authority"] != AUTHORITY:
        fail("CBAV002_INVALID_COMPONENT_DOCUMENT", "identity mismatch")
    if set(document["planes"]) != PLANES or len(document["planes"]) != len(PLANES):
        fail("CBAV005_INVALID_PLANE", str(document["planes"]))
    rows = document["components"]
    if not isinstance(rows, list) or not rows:
        fail("CBAV002_INVALID_COMPONENT_DOCUMENT", "components must be non-empty")
    required = {
        "id",
        "plane",
        "responsibility",
        "non_responsibilities",
        "inputs",
        "outputs",
        "owned_metadata",
        "dependencies",
        "idempotency_identity",
        "retry_boundary",
        "failure_signal",
        "quarantine_behavior",
        "evidence_emitted",
        "implementation_status",
        "future_implementation_owner",
        "proof_owner",
        "requirement_ids",
        "adr_ids",
    }
    ids: list[str] = []
    for row in rows:
        require_keys(
            row,
            required,
            required,
            "CBAV003_INVALID_COMPONENT_FIELDS",
            str(row.get("id", "unknown")),
        )
        component_id = row["id"]
        ids.append(component_id)
        if row["plane"] not in PLANES:
            fail("CBAV005_INVALID_PLANE", f"{component_id}: {row['plane']}")
        scalar_fields = (
            "responsibility",
            "idempotency_identity",
            "retry_boundary",
            "failure_signal",
            "quarantine_behavior",
            "implementation_status",
            "future_implementation_owner",
            "proof_owner",
        )
        if any(not isinstance(row[field], str) or not row[field] for field in scalar_fields):
            fail("CBAV006_MISSING_COMPONENT_OWNER", component_id)
        list_fields = (
            "non_responsibilities",
            "owned_metadata",
            "evidence_emitted",
            "requirement_ids",
            "adr_ids",
        )
        if any(not isinstance(row[field], list) or not row[field] for field in list_fields):
            fail("CBAV007_INCOMPLETE_COMPONENT_BOUNDARY", component_id)
        unknown_requirements = set(row["requirement_ids"]) - requirement_ids
        unknown_adrs = set(row["adr_ids"]) - adr_ids
        if unknown_requirements or unknown_adrs:
            fail(
                "CBAV008_INVALID_COMPONENT_REFERENCE",
                f"{component_id}: requirements={unknown_requirements}, adrs={unknown_adrs}",
            )
    if len(ids) != len(set(ids)):
        fail("CBAV004_DUPLICATE_COMPONENT_ID", str(ids))
    component_ids = set(ids)
    for row in rows:
        unknown_dependencies = set(row["dependencies"]) - component_ids
        if unknown_dependencies:
            fail(
                "CBAV009_UNKNOWN_COMPONENT_DEPENDENCY",
                f"{row['id']}: {sorted(unknown_dependencies)}",
            )
    if {row["plane"] for row in rows} != PLANES:
        fail("CBAV005_INVALID_PLANE", "one or more planes have no component")
    return component_ids


def validate_adrs(
    document: dict[str, Any],
    root: Path,
    component_ids: set[str],
    requirement_ids: set[str],
    check_files: bool,
) -> set[str]:
    required_top = {"schema_version", "authority", "required_decision_count", "decisions"}
    require_keys(
        document,
        required_top,
        required_top,
        "CBAV010_INVALID_ADR_INDEX",
        "adr index",
    )
    rows = document["decisions"]
    ids = [row.get("id") for row in rows]
    expected = {f"ADR-{index:03d}" for index in range(1, 16)}
    if len(ids) != len(set(ids)):
        fail("CBAV011_DUPLICATE_ADR_ID", str(ids))
    if set(ids) != expected or document["required_decision_count"] != 15:
        fail("CBAV012_MISSING_REQUIRED_ADR", str(sorted(expected - set(ids))))
    required = {
        "id",
        "title",
        "status",
        "evidence_label",
        "path",
        "requirements",
        "components",
    }
    for row in rows:
        require_keys(
            row,
            required,
            required,
            "CBAV010_INVALID_ADR_INDEX",
            str(row.get("id", "unknown")),
        )
        if row["status"] != "ACCEPTED" or row["evidence_label"] != "DESIGN_ONLY":
            fail("CBAV013_INVALID_ADR_STATUS", row["id"])
        safe_repo_path(row["path"], "CBAV014_MISSING_OR_UNSAFE_ADR_PATH")
        if set(row["requirements"]) - requirement_ids:
            fail("CBAV015_INVALID_ADR_REFERENCE", row["id"])
        if set(row["components"]) - component_ids:
            fail("CBAV015_INVALID_ADR_REFERENCE", row["id"])
        if check_files:
            path = root / row["path"]
            if not path.is_file():
                fail("CBAV014_MISSING_OR_UNSAFE_ADR_PATH", row["path"])
            content = path.read_text()
            headings = {
                "## Context",
                "## Decision",
                "## Alternatives considered",
                "## Consequences",
                "## Failure and recovery behavior",
                "## Traceability",
                "## Limitation",
            }
            if not headings.issubset(set(content.splitlines())):
                fail("CBAV016_INCOMPLETE_ADR", row["id"])
            alternative_block = content.split("## Alternatives considered", 1)[1]
            alternative_block = alternative_block.split("## Consequences", 1)[0]
            if len(re.findall(r"^- \*\*", alternative_block, re.MULTILINE)) < 2:
                fail("CBAV016_INCOMPLETE_ADR", f"{row['id']}: alternatives")
    return expected


def validate_machine(
    document: dict[str, Any],
    name: str,
    *,
    strict_transition_fields: set[str] | None = None,
) -> tuple[set[str], list[dict[str, Any]]]:
    required_top = {
        "schema_version",
        "authority",
        "machine_id",
        "initial_state",
        "terminal_states",
        "states",
        "transitions",
    }
    allowed_top = required_top | {"forbidden_rules", "invariants", "pointer_fields"}
    require_keys(
        document,
        required_top,
        allowed_top,
        "CBAV017_INVALID_STATE_MACHINE",
        name,
    )
    state_rows = document["states"]
    state_ids = [row.get("id") for row in state_rows]
    if len(state_ids) != len(set(state_ids)):
        fail("CBAV018_DUPLICATE_STATE_ID", name)
    states = set(state_ids)
    if document["initial_state"] not in states:
        fail("CBAV019_MISSING_INITIAL_STATE", name)
    terminal = set(document["terminal_states"])
    if not terminal or terminal - states:
        fail("CBAV020_INVALID_TERMINAL_STATE", name)
    transitions = document["transitions"]
    transition_ids = [row.get("id") for row in transitions]
    if len(transition_ids) != len(set(transition_ids)):
        fail("CBAV021_DUPLICATE_TRANSITION_ID", name)
    for row in transitions:
        if strict_transition_fields is not None and set(row) != strict_transition_fields:
            fail("CBAV025_INCOMPLETE_TRANSITION", f"{name}: {row.get('id')}")
        if row.get("source") not in states or row.get("target") not in states:
            fail("CBAV022_UNKNOWN_TRANSITION_STATE", f"{name}: {row.get('id')}")
        if row["source"] in terminal:
            fail("CBAV023_TERMINAL_STATE_ESCAPE", f"{name}: {row['source']}")
    seen = {document["initial_state"]}
    queue = deque(seen)
    while queue:
        current = queue.popleft()
        for row in transitions:
            if row["source"] == current and row["target"] not in seen:
                seen.add(row["target"])
                queue.append(row["target"])
    if seen != states:
        fail("CBAV024_UNREACHABLE_STATE", f"{name}: {sorted(states - seen)}")
    outgoing = {row["source"] for row in transitions}
    dead_ends = states - terminal - outgoing
    if dead_ends:
        fail("CBAV026_NONTERMINAL_DEAD_END", f"{name}: {sorted(dead_ends)}")
    return states, transitions


def validate_generation(document: dict[str, Any]) -> None:
    transition_fields = {
        "id",
        "source",
        "target",
        "actor",
        "preconditions",
        "required_gates",
        "expected_revision",
        "idempotency_key",
        "side_effects",
        "evidence",
        "retry",
        "ambiguity",
        "recovery",
        "failure_result",
        "requirement_ids",
        "adr_ids",
    }
    states, transitions = validate_machine(
        document,
        "generation",
        strict_transition_fields=transition_fields,
    )
    if states != CANONICAL_STATES:
        fail("CBAV027_NONCANONICAL_GENERATION_STATES", str(sorted(states)))
    required_pairs = {
        ("CREATED", "SNAPSHOT_LOADING"),
        ("SNAPSHOT_LOADING", "CDC_APPLYING"),
        ("CDC_APPLYING", "SEALED"),
        ("SEALED", "PROVING"),
        ("PROVING", "PROVEN"),
        ("PROVEN", "PUBLISHED"),
        ("PUBLISHED", "ROLLED_BACK"),
    }
    pairs = {(row["source"], row["target"]) for row in transitions}
    if not required_pairs.issubset(pairs):
        fail("CBAV028_INCOMPLETE_GENERATION_LIFECYCLE", str(required_pairs - pairs))
    if any(row["target"] == "PUBLISHED" and row["source"] != "PROVEN" for row in transitions):
        fail("CBAV029_PUBLICATION_FROM_UNPROVEN", "generation lifecycle")
    if ("SEALED", "CDC_APPLYING") in pairs:
        fail("CBAV030_CDC_AFTER_SEAL", "generation lifecycle")
    if any(row["source"] == "REJECTED" for row in transitions):
        fail("CBAV031_REJECTED_REOPEN", "generation lifecycle")
    if any(row["source"] == "RETIRED" for row in transitions):
        fail("CBAV032_RETIRED_REACTIVATION", "generation lifecycle")
    if ("ROLLED_BACK", "PUBLISHED") in pairs:
        fail("CBAV033_ROLLBACK_REPUBLISH", "generation lifecycle")


def validate_checkpoint(document: dict[str, Any]) -> None:
    transition_fields = {"id", "source", "target", "guard", "action"}
    _, transitions = validate_machine(
        document,
        "checkpoint",
        strict_transition_fields=transition_fields,
    )
    checkpoint_starts = [
        row for row in transitions if row["target"] == "CHECKPOINT_COMMIT_IN_PROGRESS"
    ]
    if len(checkpoint_starts) != 1 or checkpoint_starts[0]["source"] != "TARGET_COMMIT_DURABLE":
        fail("CBAV034_CHECKPOINT_BEFORE_TARGET_DURABILITY", "checkpoint lifecycle")
    ambiguous = [row for row in transitions if row["source"] == "ACKNOWLEDGEMENT_AMBIGUOUS"]
    if not ambiguous or any(row["target"] != "RECOVERY_RECONCILING" for row in ambiguous):
        fail("CBAV035_AMBIGUOUS_ACK_BLIND_RETRY", "checkpoint lifecycle")
    if any(
        "blind retry" in row["action"].lower() and "forbid" not in row["action"].lower()
        for row in transitions
    ):
        fail("CBAV035_AMBIGUOUS_ACK_BLIND_RETRY", "checkpoint action")
    required_invariants = {
        "checkpoint never advances before durable target receipt",
        "checkpoint writes are monotonic and expected-revision conditional",
        "ambiguous acknowledgement always enters reconciliation",
        "replay begins only after target receipt resolution",
        "restart begins from the last mutually established frontier",
        "no distributed ACID transaction is claimed",
    }
    if not required_invariants.issubset(set(document["invariants"])):
        fail("CBAV036_INCOMPLETE_CHECKPOINT_INVARIANTS", "checkpoint lifecycle")


def validate_proof(document: dict[str, Any], component_ids: set[str]) -> None:
    required_top = {
        "schema_version",
        "authority",
        "model_id",
        "required_gates",
        "gate_fields",
        "aggregation_rules",
        "rejection_reasons",
    }
    require_keys(
        document,
        required_top,
        required_top,
        "CBAV037_INVALID_PROOF_MODEL",
        "proof",
    )
    gate_ids = [row.get("id") for row in document["required_gates"]]
    if len(gate_ids) != len(set(gate_ids)):
        fail("CBAV038_DUPLICATE_PROOF_GATE", str(gate_ids))
    if set(gate_ids) != REQUIRED_GATES:
        fail("CBAV039_MISSING_PROOF_GATE", str(sorted(REQUIRED_GATES - set(gate_ids))))
    if any(row.get("owner") not in component_ids for row in document["required_gates"]):
        fail("CBAV040_UNKNOWN_PROOF_OWNER", "proof gate")
    required_fields = {
        "gate_id",
        "generation_id",
        "frontier",
        "input_digests",
        "producer",
        "producer_version",
        "result",
        "limitations",
        "invalidation_conditions",
    }
    if set(document["gate_fields"]) != required_fields:
        fail("CBAV041_INCOMPLETE_PROOF_BINDING", "gate fields")
    rule_text = " ".join(document["aggregation_rules"]).lower()
    for required in ("same generation", "same generation and frontier", "stale", "immutable"):
        if required not in rule_text:
            fail("CBAV042_INCOMPLETE_PROOF_AGGREGATION", required)


def validate_publication(document: dict[str, Any]) -> None:
    transition_fields = {"id", "source", "target", "guard", "action"}
    _, transitions = validate_machine(
        document,
        "publication",
        strict_transition_fields=transition_fields,
    )
    by_id = {row["id"]: row for row in transitions}
    required_ids = {
        "eligible",
        "ineligible",
        "cas_success",
        "cas_conflict",
        "verify",
        "verification_pass",
        "verification_fail",
    }
    if not required_ids.issubset(by_id):
        fail("CBAV043_INCOMPLETE_PUBLICATION_MODEL", str(required_ids - set(by_id)))
    if "PROVEN" not in by_id["eligible"]["guard"]:
        fail("CBAV044_PUBLICATION_WITHOUT_PROOF", "eligible guard")
    conflict = by_id["cas_conflict"]
    if conflict["target"] != "SAFE_CONFLICT" or "unchanged" not in conflict["action"]:
        fail("CBAV045_UNSAFE_STALE_WRITER", "cas conflict")
    if by_id["verification_fail"]["target"] != "INCIDENT":
        fail("CBAV046_POST_PUBLISH_FAILURE_HIDDEN", "verification failure")
    required_pointer = {
        "product_id",
        "generation_id",
        "revision",
        "table_map_digest",
        "proof_manifest_digest",
        "publication_attempt_id",
    }
    if set(document["pointer_fields"]) != required_pointer:
        fail("CBAV047_INCOMPLETE_POINTER", "pointer fields")


def validate_requirement_map(
    document: dict[str, Any],
    requirement_catalog: dict[str, Any],
    component_ids: set[str],
    adr_ids: set[str],
) -> None:
    catalog = {row["id"]: row for row in requirement_catalog["requirements"]}
    entries = document["entries"]
    ids = [row.get("requirement_id") for row in entries]
    if len(ids) != len(set(ids)):
        fail("CBAV048_DUPLICATE_REQUIREMENT_MAPPING", str(ids))
    if set(ids) != set(catalog) or document["requirement_count"] != len(catalog):
        fail("CBAV049_ORPHAN_REQUIREMENT", str(sorted(set(catalog) - set(ids))))
    if set(document["stage3_owned_requirements"]) != STAGE3_REQUIREMENTS:
        fail("CBAV050_STAGE3_REQUIREMENT_SET", "stage3-owned requirements")
    if document["capability_promotion"] != "NONE":
        fail("CBAV051_UNSUPPORTED_CAPABILITY_PROMOTION", "requirement map")
    required_fields = {
        "requirement_id",
        "owner_stage",
        "requirement_status",
        "architecture_disposition",
        "components",
        "adrs",
        "proof_owner",
        "evidence_label",
    }
    for row in entries:
        if set(row) != required_fields:
            fail("CBAV052_INVALID_REQUIREMENT_MAPPING", str(row.get("requirement_id")))
        req_id = row["requirement_id"]
        if set(row["components"]) - component_ids or set(row["adrs"]) - adr_ids:
            fail("CBAV053_UNKNOWN_REQUIREMENT_REFERENCE", req_id)
        if row["owner_stage"] != catalog[req_id]["owner_stage"]:
            fail("CBAV052_INVALID_REQUIREMENT_MAPPING", f"{req_id}: owner")
        if row["requirement_status"] != catalog[req_id]["current_status"]:
            fail("CBAV051_UNSUPPORTED_CAPABILITY_PROMOTION", req_id)
        if req_id in STAGE3_REQUIREMENTS:
            if row["architecture_disposition"] != "RESOLVED_DESIGN_ONLY":
                fail("CBAV054_UNRESOLVED_STAGE3_REQUIREMENT", req_id)
            if row["evidence_label"] != "DESIGN_ONLY":
                fail("CBAV051_UNSUPPORTED_CAPABILITY_PROMOTION", req_id)


def validate_claims(
    claims: dict[str, Any],
    claim_impact: dict[str, Any],
    requirement_ids: set[str],
) -> None:
    rows = {row["id"]: row for row in claims["claims"]}
    for row in rows.values():
        if row["label"] not in ALLOWED_CLAIM_LABELS:
            fail("CBAV055_UNKNOWN_EVIDENCE_LABEL", row["id"])
        if set(row["requirement_ids"]) - requirement_ids:
            fail("CBAV056_UNKNOWN_CLAIM_REQUIREMENT", row["id"])
    if claim_impact["architecture_freeze_commit"] != ARCHITECTURE_FREEZE_COMMIT:
        fail("CBAV057_STALE_ARCHITECTURE_BINDING", "impact review")
    reviewed = set(claim_impact["reviewed_claim_ids"])
    required_review = {"CB-CLAIM-002", "CB-CLAIM-004", "CB-CLAIM-007", "CB-CLAIM-009"}
    if not required_review.issubset(reviewed):
        fail("CBAV058_INCOMPLETE_CLAIM_REVIEW", str(required_review - reviewed))
    for claim_id in ("CB-CLAIM-002", "CB-CLAIM-009"):
        row = rows[claim_id]
        if row["label"] != "DESIGN_ONLY":
            fail("CBAV059_ARCHITECTURE_CLAIM_PROMOTION", claim_id)
        if row["producing_commit"] != ARCHITECTURE_FREEZE_COMMIT:
            fail("CBAV057_STALE_ARCHITECTURE_BINDING", claim_id)
    if rows["CB-CLAIM-007"]["label"] != "UNCLAIMED":
        fail("CBAV059_ARCHITECTURE_CLAIM_PROMOTION", "CB-CLAIM-007")
    if rows["CB-CLAIM-004"]["label"] != "LOCAL_VERIFIED":
        fail("CBAV059_ARCHITECTURE_CLAIM_PROMOTION", "CB-CLAIM-004")


def validate_files(root: Path) -> None:
    for path in sorted((root / "architecture/diagrams").glob("*.svg")):
        try:
            ET.parse(path)
        except ET.ParseError as exc:
            fail("CBAV060_INVALID_RENDERED_DIAGRAM", f"{path}: {exc}")
    required_docs = (
        "docs/architecture.md",
        "docs/architecture/RESPONSIBILITY_MODEL.md",
        "docs/architecture/GENERATION_LIFECYCLE.md",
        "docs/architecture/CHECKPOINT_RECOVERY.md",
        "docs/architecture/PROOF_AND_PUBLICATION.md",
        "docs/architecture/CONSISTENCY_AND_LIMITATIONS.md",
    )
    for value in required_docs:
        safe_repo_path(value, "CBAV061_MISSING_OR_UNSAFE_PATH")
        if not (root / value).is_file():
            fail("CBAV061_MISSING_OR_UNSAFE_PATH", value)
    scan_roots = (
        root / "architecture",
        root / "docs/adr",
        root / "docs/architecture",
    )
    for scan_root in scan_roots:
        paths = [scan_root] if scan_root.is_file() else list(scan_root.rglob("*"))
        for path in paths:
            if not path.is_file() or path.suffix.lower() not in {".json", ".md", ".py", ".svg"}:
                continue
            lowered = path.read_text().lower()
            for term in FORBIDDEN_PROJECT_TERMS:
                if term in lowered:
                    fail("CBAV062_CROSS_PROJECT_REFERENCE", f"{path}: {term}")


def validate_no_cross_project(value: Any, location: str = "authority") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            validate_no_cross_project(child, f"{location}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            validate_no_cross_project(child, f"{location}[{index}]")
    elif isinstance(value, str):
        lowered = value.lower()
        for term in FORBIDDEN_PROJECT_TERMS:
            if term in lowered:
                fail("CBAV062_CROSS_PROJECT_REFERENCE", f"{location}: {term}")


def run_renderer(root: Path, *, check: bool) -> None:
    path = root / "scripts/build_architecture_authority.py"
    spec = importlib.util.spec_from_file_location("changebridge_architecture_builder", path)
    if spec is None or spec.loader is None:
        fail("CBAV063_RENDERER_FAILURE", str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        module.build(root, check=check)
    except (OSError, ValueError, SystemExit) as exc:
        fail("CBAV063_RENDERER_FAILURE", str(exc))


def validate_authority(
    authority: dict[str, Any],
    root: Path,
    *,
    check_files: bool = True,
    check_rendered: bool = True,
) -> dict[str, Any]:
    expected_top = {
        "components",
        "adrs",
        "generation",
        "checkpoint",
        "proof",
        "publication",
        "requirement_map",
        "requirement_catalog",
        "claims",
        "claim_impact",
    }
    if set(authority) != expected_top:
        fail("CBAV064_UNKNOWN_AUTHORITY_SECTION", str(sorted(set(authority) - expected_top)))
    validate_no_cross_project(authority)
    catalog_rows = authority["requirement_catalog"]["requirements"]
    requirement_ids = {row["id"] for row in catalog_rows}
    provisional_adrs = {f"ADR-{index:03d}" for index in range(1, 16)}
    component_ids = validate_components(
        authority["components"],
        requirement_ids,
        provisional_adrs,
    )
    adr_ids = validate_adrs(
        authority["adrs"],
        root,
        component_ids,
        requirement_ids,
        check_files,
    )
    validate_generation(authority["generation"])
    validate_checkpoint(authority["checkpoint"])
    validate_proof(authority["proof"], component_ids)
    validate_publication(authority["publication"])
    validate_requirement_map(
        authority["requirement_map"],
        authority["requirement_catalog"],
        component_ids,
        adr_ids,
    )
    validate_claims(
        authority["claims"],
        authority["claim_impact"],
        requirement_ids,
    )
    if check_files:
        validate_files(root)
    if check_rendered:
        run_renderer(root, check=True)
    report = {
        "schema_version": SCHEMA_VERSION,
        "stage": AUTHORITY,
        "result": "PASS",
        "evidence_label": "LOCAL_VERIFIED",
        "component_count": len(component_ids),
        "adr_count": len(adr_ids),
        "requirement_count": len(requirement_ids),
        "stage3_requirement_count": len(STAGE3_REQUIREMENTS),
        "generation_state_count": len(authority["generation"]["states"]),
        "generation_transition_count": len(authority["generation"]["transitions"]),
        "checkpoint_state_count": len(authority["checkpoint"]["states"]),
        "proof_gate_count": len(authority["proof"]["required_gates"]),
        "claim_count": len(authority["claims"]["claims"]),
        "architecture_freeze_commit": ARCHITECTURE_FREEZE_COMMIT,
        "capability_promotion": "NONE",
        "limitations": [
            "This validates specification consistency, not managed runtime behavior.",
            "No AWS, performance, availability, exactly-once, or zero-downtime claim is created.",
        ],
    }
    digest_source = dict(report)
    report["canonical_sha256"] = hashlib.sha256(canonical_json(digest_source).encode()).hexdigest()
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--check-rendered", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        if args.render:
            run_renderer(root, check=False)
        report = validate_authority(
            load_authority(root),
            root,
            check_files=True,
            check_rendered=args.check_rendered,
        )
    except ArchitectureError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    rendered = canonical_json(report)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
